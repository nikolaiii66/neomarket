from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str


class ApproveRequest(BaseModel):
    moderator_comment: str | None = None
    comment: str | None = None


class FieldReportIn(BaseModel):
    field_path: str | None = None
    field_name: str | None = None
    message: str | None = None
    comment: str | None = None
    severity: Literal["INFO", "WARNING", "ERROR"] = "ERROR"
    sku_id: UUID | None = None


class DeclineRequest(BaseModel):
    blocking_reason_id: UUID | None = None
    blocking_reason_ids: list[UUID] | None = None
    moderator_comment: str | None = None
    comment: str | None = None
    field_reports: list[FieldReportIn] = Field(default_factory=list)


class ClaimRequest(BaseModel):
    queue_priority: int | None = Field(default=None, ge=1, le=4)
    category_ids: list[UUID] | None = None


class BlockingReasonOut(BaseModel):
    id: UUID
    code: str
    title: str
    description: str | None = None
    hard_block: bool
    is_active: bool


class TicketResponse(BaseModel):
    id: UUID
    product_id: UUID
    seller_id: UUID
    category_id: UUID | None = None
    kind: str
    status: str
    queue_priority: int
    assigned_moderator_id: UUID | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    decision_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class TicketDetailResponse(TicketResponse):
    json_before: dict[str, Any] | None = None
    json_after: dict[str, Any]
    field_reports: list[dict[str, Any]] = Field(default_factory=list)
    decision_comment: str | None = None


class ProductDecisionResponse(BaseModel):
    product_id: UUID
    status: str


class IncomingCanonEvent(BaseModel):
    idempotency_key: str
    event: str | None = None
    event_type: str | None = None
    product_id: UUID | None = None
    seller_id: UUID | None = None
    json_after: dict[str, Any] | None = None
    json_before: dict[str, Any] | None = None
    date: datetime | None = None
    payload: dict[str, Any] | None = None


class IncomingProtocolEvent(BaseModel):
    event_type: Literal["PRODUCT_CREATED", "PRODUCT_EDITED", "PRODUCT_DELETED"]
    idempotency_key: UUID | str
    occurred_at: datetime
    payload: dict[str, Any]
