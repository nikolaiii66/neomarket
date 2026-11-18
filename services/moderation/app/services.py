from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    BlockingReason,
    IncomingProductEvent,
    ModerationCard,
    OutgoingModerationEvent,
)
from app.serializers import serialize_product_decision, serialize_ticket, serialize_ticket_detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _http_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def has_skus(snapshot: dict) -> bool:
    skus = snapshot.get("skus")
    if isinstance(skus, list):
        return len(skus) > 0
    product = snapshot.get("product")
    if isinstance(product, dict) and isinstance(product.get("skus"), list):
        return len(product["skus"]) > 0
    return False


def get_card_by_product(db: Session, product_id: str) -> ModerationCard | None:
    return db.scalar(select(ModerationCard).where(ModerationCard.product_id == product_id))


def get_card_by_id(db: Session, ticket_id: str) -> ModerationCard | None:
    return db.get(ModerationCard, ticket_id)


def _require_card(card: ModerationCard | None) -> ModerationCard:
    if card is None:
        raise _http_error(404, "NOT_FOUND", "Product not found in moderation queue")
    return card


def _assert_decision_preconditions(card: ModerationCard, moderator_id: str) -> None:
    if card.status == ModerationCard.Status.HARD_BLOCKED:
        raise _http_error(403, "HARD_BLOCKED", "Product is permanently blocked")
    if card.status != ModerationCard.Status.IN_REVIEW:
        raise _http_error(409, "INVALID_STATUS", "Product is not in review status")
    if card.assigned_moderator_id != moderator_id:
        raise _http_error(403, "NOT_ASSIGNED", "This moderation card is not assigned to you")


def normalize_field_reports(raw: list[Any] | None) -> list[dict]:
    if raw is None:
        return []
    normalized: list[dict] = []
    for item in raw:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            raise _http_error(400, "INVALID_FIELD_REPORTS", "field_reports must contain field_path and message")
        field_path = item.get("field_path") or item.get("field_name")
        message = item.get("message") or item.get("comment")
        if not field_path or not message:
            raise _http_error(400, "INVALID_FIELD_REPORTS", "field_reports must contain field_path and message")
        severity = item.get("severity") or "ERROR"
        if severity not in {"INFO", "WARNING", "ERROR"}:
            raise _http_error(400, "INVALID_FIELD_REPORTS", "field_reports must contain field_path and message")
        entry = {"field_path": str(field_path), "message": str(message), "severity": severity}
        sku_id = item.get("sku_id")
        if sku_id:
            entry["sku_id"] = str(sku_id)
        normalized.append(entry)
    return normalized


def b2b_field_reports(field_reports: list[dict]) -> list[dict]:
    result = []
    for report in field_reports:
        entry = {
            "field_name": report["field_path"],
            "comment": report["message"],
        }
        if report.get("sku_id"):
            entry["sku_id"] = report["sku_id"]
        result.append(entry)
    return result


def deliver_moderation_event(event: OutgoingModerationEvent, payload: dict) -> None:
    """POST decision to B2B; used by tests via monkeypatch."""
    if not settings.b2b_base_url:
        return
    url = f"{settings.b2b_base_url.rstrip('/')}/api/v1/moderation/events"
    response = httpx.post(
        url,
        json=payload,
        headers={"X-Service-Key": settings.b2b_service_key},
        timeout=settings.b2b_timeout_seconds,
    )
    if response.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"B2B moderation event failed: {response.status_code}",
            request=response.request,
            response=response,
        )


def send_moderation_event(db: Session, card: ModerationCard, payload: dict, event_type: str) -> OutgoingModerationEvent:
    event = OutgoingModerationEvent(card_id=card.id, event_type=event_type, payload={})
    db.add(event)
    db.flush()

    request_payload = {
        **payload,
        "idempotency_key": event.idempotency_key,
        "occurred_at": _now().isoformat(),
    }
    event.payload = request_payload
    db.flush()

    try:
        deliver_moderation_event(event, request_payload)
    except Exception:
        db.rollback()
        raise _http_error(500, "B2B_EVENT_FAILED", "Could not deliver moderation decision to B2B") from None

    if settings.b2b_base_url:
        event.delivered = True
        event.delivered_at = _now()
    db.commit()
    db.refresh(event)
    db.refresh(card)
    return event


def approve_card(
    db: Session,
    *,
    moderator_id: str,
    ticket_id: str | None = None,
    product_id: str | None = None,
    comment: str | None = None,
    protocol_response: bool,
) -> dict:
    card = _require_card(
        get_card_by_id(db, ticket_id) if ticket_id else get_card_by_product(db, product_id or "")
    )
    _assert_decision_preconditions(card, moderator_id)
    if not has_skus(card.json_after or {}):
        raise _http_error(409, "NO_SKUS", "Product has no SKUs, cannot approve")

    card.status = ModerationCard.Status.MODERATED
    card.decision_at = _now()
    card.decision_comment = (comment or "").strip()
    card.blocking_reason_id = None
    card.field_reports = []
    card.updated_at = _now()
    db.flush()

    event_payload = {
        "product_id": card.product_id,
        "event_type": "MODERATED",
        "moderator_id": card.assigned_moderator_id,
        "moderator_comment": card.decision_comment or None,
    }
    send_moderation_event(db, card, event_payload, "MODERATED")

    if protocol_response:
        return serialize_ticket(card, protocol=True)
    return serialize_product_decision(card)


def resolve_blocking_reason(db: Session, payload: dict) -> BlockingReason:
    reason_ids = payload.get("blocking_reason_ids")
    if isinstance(reason_ids, list) and reason_ids:
        reason_id = str(reason_ids[0])
    elif payload.get("blocking_reason_id"):
        reason_id = str(payload["blocking_reason_id"])
    else:
        raise _http_error(400, "UNKNOWN_REASON", "Blocking reason not found")

    reason = db.scalar(
        select(BlockingReason).where(BlockingReason.id == reason_id, BlockingReason.is_active.is_(True))
    )
    if reason is None:
        raise _http_error(400, "UNKNOWN_REASON", "Blocking reason not found")
    return reason


def decline_card(
    db: Session,
    *,
    moderator_id: str,
    ticket_id: str | None = None,
    product_id: str | None = None,
    payload: dict,
    protocol_response: bool,
) -> dict:
    card = _require_card(
        get_card_by_id(db, ticket_id) if ticket_id else get_card_by_product(db, product_id or "")
    )
    _assert_decision_preconditions(card, moderator_id)

    reason = resolve_blocking_reason(db, payload)
    field_reports = normalize_field_reports(payload.get("field_reports"))

    card.status = ModerationCard.Status.HARD_BLOCKED if reason.hard_block else ModerationCard.Status.BLOCKED
    card.decision_at = _now()
    card.decision_comment = str(payload.get("moderator_comment") or payload.get("comment") or "").strip()
    card.blocking_reason_id = reason.id
    card.field_reports = field_reports
    card.updated_at = _now()
    db.flush()

    event_payload = {
        "product_id": card.product_id,
        "event_type": "BLOCKED",
        "moderator_id": card.assigned_moderator_id,
        "moderator_comment": card.decision_comment or None,
        "blocking_reason_id": reason.id,
        "hard_block": reason.hard_block,
        "field_reports": b2b_field_reports(field_reports),
    }
    send_moderation_event(db, card, event_payload, "BLOCKED")

    if protocol_response:
        return serialize_ticket(card, protocol=True)
    return serialize_product_decision(card)


def claim_next(
    db: Session,
    *,
    moderator_id: str,
    queue_priority: int | None = None,
) -> ModerationCard | None:
    stmt = select(ModerationCard).where(ModerationCard.status == ModerationCard.Status.PENDING)
    if queue_priority is not None:
        stmt = stmt.where(ModerationCard.queue_priority == queue_priority)
    else:
        stmt = stmt.order_by(ModerationCard.queue_priority.asc(), ModerationCard.created_at.asc())
    if queue_priority is not None:
        stmt = stmt.order_by(ModerationCard.created_at.asc())
    card = db.scalars(stmt.limit(1)).first()
    if card is None:
        return None

    now = _now()
    card.status = ModerationCard.Status.IN_REVIEW
    card.assigned_moderator_id = moderator_id
    card.claimed_at = now
    card.claim_expires_at = now + timedelta(minutes=30)
    card.updated_at = now
    db.commit()
    db.refresh(card)
    return card


def get_ticket_detail(db: Session, ticket_id: str) -> dict:
    card = _require_card(get_card_by_id(db, ticket_id))
    return serialize_ticket_detail(card)


def normalize_incoming_event(payload: dict) -> tuple[str, str, str | None, dict]:
    event_type = str(
        payload.get("event_type") or payload.get("event") or payload.get("type") or payload.get("status") or ""
    ).upper()
    event_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    product_id_raw = event_payload.get("product_id") or payload.get("product_id")
    product_id = str(product_id_raw) if product_id_raw else None
    try:
        if product_id:
            product_id = str(UUID(product_id))
    except ValueError:
        product_id = None
    idempotency_key = str(payload.get("idempotency_key") or payload.get("event_id") or "").strip()
    aliases = {
        "PRODUCT_CREATED": "CREATED",
        "PRODUCT_EDITED": "EDITED",
        "PRODUCT_DELETED": "DELETED",
    }
    return aliases.get(event_type, event_type), idempotency_key, product_id, event_payload


def handle_product_event(db: Session, payload: dict) -> dict:
    event_type, idempotency_key, product_id, event_payload = normalize_incoming_event(payload)
    if product_id is None or not event_type or not idempotency_key:
        raise _http_error(400, "INVALID_REQUEST", "product_id, event and idempotency_key are required")

    existing = db.scalar(
        select(IncomingProductEvent).where(IncomingProductEvent.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return {"status": "duplicate_ignored"}

    incoming = IncomingProductEvent(
        idempotency_key=idempotency_key,
        event_type=event_type,
        product_id=product_id,
    )
    incoming.payload = payload
    db.add(incoming)
    db.flush()

    card = get_card_by_product(db, product_id)

    if event_type == "DELETED":
        if card is not None:
            db.delete(card)
        db.commit()
        return {"status": "archived"}

    if card is not None and card.status == ModerationCard.Status.HARD_BLOCKED and event_type == "EDITED":
        db.commit()
        return {"status": "ignored_hard_blocked"}

    if event_type == "CREATED":
        if card is not None and card.status == ModerationCard.Status.HARD_BLOCKED:
            db.commit()
            return {"status": "ignored_hard_blocked"}
        if card is not None:
            raise _http_error(400, "DUPLICATE_CREATED", "Product already exists in moderation")
        card = ModerationCard(
            product_id=product_id,
            seller_id=str(event_payload.get("seller_id")) if event_payload.get("seller_id") else None,
            category_id=str(event_payload.get("category_id")) if event_payload.get("category_id") else None,
            kind=ModerationCard.Kind.CREATE,
            status=ModerationCard.Status.PENDING,
            queue_priority=int(event_payload.get("queue_priority") or 1),
        )
        card.json_before = None
        card.json_after = event_payload.get("json_after") or event_payload.get("product") or {}
        db.add(card)
        db.commit()
        return {"status": "accepted"}

    if event_type == "EDITED" and card is not None:
        card.status = ModerationCard.Status.PENDING
        card.assigned_moderator_id = None
        card.claimed_at = None
        card.claim_expires_at = None
        card.json_before = card.json_after
        card.json_after = event_payload.get("json_after") or event_payload.get("product") or card.json_after
        card.kind = ModerationCard.Kind.EDIT
        card.updated_at = _now()
        db.commit()
        return {"status": "accepted"}

    if event_type == "EDITED" and card is None:
        raise _http_error(400, "NOT_FOUND", "Product not found for EDITED event")

    db.commit()
    return {"status": "accepted"}
