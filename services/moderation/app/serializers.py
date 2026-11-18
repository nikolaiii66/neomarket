from __future__ import annotations

from app.models import BlockingReason, ModerationCard


ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def status_for_protocol(card: ModerationCard) -> str:
    if card.status == ModerationCard.Status.MODERATED:
        return "APPROVED"
    return card.status


def serialize_reason(reason: BlockingReason) -> dict:
    return {
        "id": reason.id,
        "code": reason.code,
        "title": reason.title,
        "description": reason.description or None,
        "hard_block": reason.hard_block,
        "is_active": reason.is_active,
    }


def serialize_ticket(card: ModerationCard, *, protocol: bool = True) -> dict:
    return {
        "id": card.id,
        "product_id": card.product_id,
        "seller_id": card.seller_id or ZERO_UUID,
        "category_id": card.category_id,
        "kind": card.kind,
        "status": status_for_protocol(card) if protocol else card.status,
        "queue_priority": card.queue_priority,
        "assigned_moderator_id": card.assigned_moderator_id,
        "claimed_at": card.claimed_at,
        "claim_expires_at": card.claim_expires_at,
        "decision_at": card.decision_at,
        "created_at": card.created_at,
        "updated_at": card.updated_at,
    }


def serialize_ticket_detail(card: ModerationCard) -> dict:
    payload = serialize_ticket(card, protocol=True)
    payload.update(
        {
            "json_before": card.json_before,
            "json_after": card.json_after,
            "field_reports": card.field_reports,
            "decision_comment": card.decision_comment or None,
        }
    )
    return payload


def serialize_product_decision(card: ModerationCard) -> dict:
    return {"product_id": card.product_id, "status": card.status}
