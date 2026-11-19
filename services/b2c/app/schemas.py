from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# OpenAPI enum: price_asc, price_desc, popularity, new — plus canon extras.
ALLOWED_SORTS = {
    "rating",
    "popularity",
    "price_asc",
    "price_desc",
    "date_desc",
    "discount_desc",
    "new",
}

ALLOWED_SORTS_MESSAGE = (
    "Invalid sort parameter. Allowed: "
    + ", ".join(sorted(ALLOWED_SORTS))
)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ImageRef(BaseModel):
    id: UUID | str
    url: str
    alt: str = ""
    ordering: int = 0
    is_main: bool = False


class CategoryRef(BaseModel):
    id: UUID | str
    name: str
    parent_id: UUID | str | None = None
    level: int = 0
    path: list[str] = Field(default_factory=list)


class CatalogProductSeller(BaseModel):
    id: UUID | str
    display_name: str


class CatalogProductCard(BaseModel):
    id: UUID | str
    name: str
    title: str | None = None
    slug: str | None = None
    min_price: int
    price: int | None = None
    old_price: int | None = None
    category: CategoryRef | None = None
    has_stock: bool
    in_stock: bool | None = None
    is_in_cart: bool = False
    rating: float | None = None
    reviews_count: int = 0
    images: list[ImageRef] | list[str]
    image: str | None = None
    seller: CatalogProductSeller | None = None


class CatalogSku(BaseModel):
    id: UUID | str
    name: str
    sku_code: str | None = None
    price: int
    old_price: int | None = None
    available_quantity: int
    active_quantity: int | None = None
    in_stock: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)
    characteristics: list[dict[str, str]] = Field(default_factory=list)
    images: list[ImageRef] = Field(default_factory=list)
    image: str | None = None


class CatalogProductDetail(BaseModel):
    id: UUID | str
    name: str
    title: str | None = None
    slug: str | None = None
    description: str
    status: str | None = None
    min_price: int
    old_price: int | None = None
    has_stock: bool
    images: list[ImageRef] | list[str]
    attributes: dict[str, Any] = Field(default_factory=dict)
    characteristics: list[dict[str, str]] = Field(default_factory=list)
    skus: list[CatalogSku]
    category: CategoryRef | None = None
    rating: float | None = None
    reviews_count: int = 0
    seller: CatalogProductSeller | None = None


class PaginatedCatalogProducts(BaseModel):
    items: list[CatalogProductCard]
    total_count: int
    limit: int
    offset: int


class FacetValue(BaseModel):
    value: str
    count: int


class Facet(BaseModel):
    name: str
    values: list[FacetValue] = Field(default_factory=list)


class FilterMeta(BaseModel):
    id: UUID | str
    name: str
    type: str = "list"
    value: list[str] | None = None
    min: int | None = None
    max: int | None = None


class FacetsResponse(BaseModel):
    category_id: UUID | str
    filters: list[FilterMeta] = Field(default_factory=list)
    facets: list[Facet] = Field(default_factory=list)


class CartItemAddRequest(BaseModel):
    sku_id: UUID
    quantity: int = Field(ge=1)


class CartItemQuantityUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    sku_id: UUID | str
    product_id: UUID | str
    name: str
    sku_code: str | None = None
    quantity: int
    unit_price: int
    unit_price_at_add: int | None = None
    line_total: int
    available_quantity: int
    is_available: bool
    # Computed on each enrich from B2B — never persisted in DB.
    unavailable_reason: str | None = None
    image: ImageRef | None = None


class CartResponse(BaseModel):
    id: UUID | str | None = None
    items: list[CartItemOut]
    items_count: int
    subtotal: int
    # Alias for quest wording «total_amount»; equals subtotal of available lines only.
    total_amount: int | None = None
    is_valid: bool
    updated_at: datetime | None = None


class CartValidationIssue(BaseModel):
    sku_id: UUID | str
    type: Literal[
        "PRICE_CHANGED",
        "OUT_OF_STOCK",
        "QUANTITY_REDUCED",
        "PRODUCT_BLOCKED",
        "PRODUCT_DELETED",
    ]
    message: str
    old_value: str | int | None = None
    new_value: str | int | None = None


class CartValidationResponse(BaseModel):
    is_valid: bool
    cart: CartResponse
    issues: list[CartValidationIssue]


class OrderItemSnapshot(BaseModel):
    sku_id: UUID
    quantity: int = Field(ge=1)
    unit_price: int = Field(ge=0)


class OrderCreateRequest(BaseModel):
    address_id: UUID
    payment_method_id: UUID
    comment: str | None = Field(default=None, max_length=1000)
    items_snapshot: list[OrderItemSnapshot] | None = None


class OrderCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    restore_cart: bool = False


class AddressResponse(BaseModel):
    id: UUID | str
    country: str
    city: str
    street: str
    building: str
    region: str | None = None
    apartment: str | None = None
    postal_code: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    is_default: bool = False
    comment: str | None = None
    created_at: datetime | None = None


class PaymentMethodResponse(BaseModel):
    id: UUID | str
    type: str
    card_last4: str | None = None
    card_brand: str | None = None
    is_default: bool = False
    created_at: datetime | None = None


class OrderItemOut(BaseModel):
    sku_id: UUID | str
    product_id: UUID | str
    name: str
    sku_code: str | None = None
    quantity: int
    unit_price: int
    line_total: int
    image_url: str | None = None


class OrderResponse(BaseModel):
    id: UUID | str
    number: str | None = None
    buyer_id: UUID | str
    status: str
    status_history: list[dict[str, Any]] | None = None
    items: list[OrderItemOut]
    subtotal: int
    delivery_cost: int = 0
    total: int
    address: AddressResponse
    payment_method: PaymentMethodResponse | None = None
    comment: str | None = None
    cancel_reason: str | None = None
    created_at: datetime
    paid_at: datetime | None = None
    delivered_at: datetime | None = None


class PaginatedOrders(BaseModel):
    items: list[OrderResponse]
    total_count: int
    limit: int
    offset: int
