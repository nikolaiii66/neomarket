from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_moderator, require_service_key
from app.db import get_db
from app.models import BlockingReason
from app.schemas import ApproveRequest, ClaimRequest, DeclineRequest
from app.serializers import serialize_reason, serialize_ticket
from app import services

router = APIRouter()


def _decline_payload(body: DeclineRequest) -> dict[str, Any]:
    return body.model_dump(mode="json")


@router.post("/api/v1/queue/claim")
def claim_ticket(
    moderator_id: Annotated[str, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    body: ClaimRequest | None = None,
):
    body = body or ClaimRequest()
    card = services.claim_next(db, moderator_id=moderator_id, queue_priority=body.queue_priority)
    if card is None:
        return Response(status_code=204)
    return serialize_ticket(card, protocol=True)


@router.get("/api/v1/tickets/{ticket_id}")
def get_ticket(
    ticket_id: UUID,
    _: Annotated[str, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
):
    return services.get_ticket_detail(db, str(ticket_id))


@router.post("/api/v1/tickets/{ticket_id}/approve")
def approve_ticket(
    ticket_id: UUID,
    moderator_id: Annotated[str, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    body: ApproveRequest | None = None,
):
    body = body or ApproveRequest()
    comment = body.moderator_comment or body.comment
    return services.approve_card(
        db,
        moderator_id=moderator_id,
        ticket_id=str(ticket_id),
        comment=comment,
        protocol_response=True,
    )


@router.post("/api/v1/products/{product_id}/approve")
def approve_product(
    product_id: UUID,
    moderator_id: Annotated[str, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    body: ApproveRequest | None = None,
):
    body = body or ApproveRequest()
    comment = body.moderator_comment or body.comment
    return services.approve_card(
        db,
        moderator_id=moderator_id,
        product_id=str(product_id),
        comment=comment,
        protocol_response=False,
    )


@router.post("/api/v1/tickets/{ticket_id}/block")
def block_ticket(
    ticket_id: UUID,
    moderator_id: Annotated[str, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    body: DeclineRequest,
):
    return services.decline_card(
        db,
        moderator_id=moderator_id,
        ticket_id=str(ticket_id),
        payload=_decline_payload(body),
        protocol_response=True,
    )


@router.post("/api/v1/tickets/{ticket_id}/decline")
def decline_ticket(
    ticket_id: UUID,
    moderator_id: Annotated[str, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    body: DeclineRequest,
):
    return services.decline_card(
        db,
        moderator_id=moderator_id,
        ticket_id=str(ticket_id),
        payload=_decline_payload(body),
        protocol_response=True,
    )


@router.post("/api/v1/products/{product_id}/decline")
def decline_product(
    product_id: UUID,
    moderator_id: Annotated[str, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    body: DeclineRequest,
):
    return services.decline_card(
        db,
        moderator_id=moderator_id,
        product_id=str(product_id),
        payload=_decline_payload(body),
        protocol_response=False,
    )


@router.get("/api/v1/blocking-reasons")
@router.get("/api/v1/product-blocking-reasons")
def list_blocking_reasons(
    db: Annotated[Session, Depends(get_db)],
    hard_block: bool | None = None,
    is_active: bool | None = True,
):
    stmt = select(BlockingReason)
    if hard_block is not None:
        stmt = stmt.where(BlockingReason.hard_block.is_(hard_block))
    if is_active is not None:
        stmt = stmt.where(BlockingReason.is_active.is_(is_active))
    stmt = stmt.order_by(BlockingReason.hard_block.asc(), BlockingReason.title.asc())
    return [serialize_reason(reason) for reason in db.scalars(stmt).all()]


@router.post("/api/v1/events/product", status_code=202)
@router.post("/api/v1/b2b/events", status_code=202)
def receive_product_event(
    payload: dict[str, Any],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(require_service_key)],
):
    return services.handle_product_event(db, payload)
