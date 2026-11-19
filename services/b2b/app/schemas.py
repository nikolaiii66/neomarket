from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


ProductStatus = Literal["CREATED", "ON_MODERATION", "MODERATED", "BLOCKED", "HARD_BLOCKED"]


class ErrorBody(BaseModel):
    code: str
    message: str


class CharacteristicIn(BaseModel):
    name: str
    value: str


class ImageIn(BaseModel):
    url: str
    ordering: int = 0


class ProductCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    # Optional at schema level so missing fields become canon 400 in service, not FastAPI 422.
    category_id: UUID | None = None
    images: list[ImageIn] | None = None
    characteristics: list[CharacteristicIn] = Field(default_factory=list)
    slug: str | None = None


class CharacteristicOut(BaseModel):
    name: str
    value: str


class ImageOut(BaseModel):
    id: UUID | None = None
    url: str
    ordering: int


class SKUCreate(BaseModel):
    product_id: UUID
    title: str = Field(min_length=1, max_length=255)
    price: int = Field(ge=0)
    cost_price: int = Field(default=0, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    # Optional at schema so empty/missing images become canon 400 in service, not FastAPI 422.
    images: list[ImageIn] | None = None
    characteristics: list[CharacteristicIn] = Field(default_factory=list)


class SKUOut(BaseModel):
    id: UUID
    product_id: UUID
    title: str
    price: int
    cost_price: int
    stock_quantity: int
    reserved_quantity: int
    deleted: bool
    images: list[ImageOut]
    characteristics: list[CharacteristicOut]


class FieldReportIn(BaseModel):
    field_name: str
    message: str | None = None
    comment: str | None = None
    sku_id: UUID | None = None
    reason_id: UUID | None = None


class FieldReportOut(BaseModel):
    field_name: str
    # OpenAPI uses `comment`; keep `message` for backward-compatible assertions.
    comment: str
    message: str
    sku_id: UUID | None = None
    reason_id: UUID | None = None


class BlockingReasonOut(BaseModel):
    id: UUID
    title: str
    comment: str


class ProductOut(BaseModel):
    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    slug: str
    description: str
    status: ProductStatus
    deleted: bool
    blocked: bool
    blocking_reason_id: UUID | None
    blocking_reason: BlockingReasonOut | None = None
    moderator_comment: str | None
    images: list[ImageOut]
    characteristics: list[CharacteristicOut]
    skus: list[SKUOut]
    field_reports: list[FieldReportOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class InventoryItem(BaseModel):
    sku_id: UUID
    quantity: int = Field(ge=1)


class ReserveRequest(BaseModel):
    idempotency_key: UUID
    order_id: UUID
    items: list[InventoryItem] = Field(min_length=1)


class UnreserveRequest(BaseModel):
    order_id: UUID
    items: list[InventoryItem] = Field(min_length=1)


class InventoryOrderResponse(BaseModel):
    order_id: UUID
    items: list[InventoryItem]


class ModerationEventRequest(BaseModel):
    idempotency_key: UUID
    product_id: UUID
    event_type: Literal["MODERATED", "BLOCKED"]
    occurred_at: datetime
    hard_block: bool = False
    blocking_reason_id: UUID | None = None
    moderator_comment: str | None = None
    moderator_id: UUID | None = None
    field_reports: list[FieldReportIn] | None = None


class ProductPublicOut(BaseModel):
    id: UUID
    title: str
    slug: str
    description: str
    category_id: UUID
    images: list[ImageOut]
    characteristics: list[CharacteristicOut]
    skus: list[dict]
    min_price: int | None = None
