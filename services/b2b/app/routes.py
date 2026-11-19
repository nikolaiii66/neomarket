from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.auth import require_seller, require_service_key
from app.db import get_db
from app.schemas import (
    ModerationEventRequest,
    ProductCreate,
    ProductOut,
    ProductPublicOut,
    PublicProductsBatchRequest,
    ReserveRequest,
    SKUCreate,
    SKUOut,
    UnreserveRequest,
)
from app import services
from app.serializers import serialize_product, serialize_public_product, serialize_sku

router = APIRouter()


def service_any(x_service_key: Annotated[str | None, Header(alias="X-Service-Key")] = None) -> str:
    return require_service_key(x_service_key)


def service_b2c(x_service_key: Annotated[str | None, Header(alias="X-Service-Key")] = None) -> str:
    return require_service_key(x_service_key, {"b2c"})


def service_moderation(x_service_key: Annotated[str | None, Header(alias="X-Service-Key")] = None) -> str:
    return require_service_key(x_service_key, {"moderation"})


@router.post("/api/v1/products", status_code=201, response_model=ProductOut)
def create_product(
    payload: ProductCreate,
    seller_id: Annotated[str, Depends(require_seller)],
    db: Annotated[Session, Depends(get_db)],
):
    product = services.create_product(db, seller_id, payload)
    return serialize_product(product)


@router.get("/api/v1/products/{product_id}", response_model=ProductOut)
def get_product(
    product_id: UUID,
    seller_id: Annotated[str, Depends(require_seller)],
    db: Annotated[Session, Depends(get_db)],
):
    product = services.get_product_for_seller(db, seller_id, str(product_id))
    return serialize_product(product)


@router.post("/api/v1/skus", status_code=201, response_model=SKUOut)
def create_sku(
    payload: SKUCreate,
    seller_id: Annotated[str, Depends(require_seller)],
    db: Annotated[Session, Depends(get_db)],
):
    sku, _ = services.create_sku(db, seller_id, payload)
    return serialize_sku(sku)


@router.get("/api/v1/public/products", response_model=list[ProductPublicOut])
def public_products(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(service_any)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    ids: str | None = Query(
        None,
        description="Comma-separated product UUIDs; returns only visible subset (no 404 for hidden).",
    ),
):
    id_list: list[str] | None = None
    if ids is not None and ids.strip():
        id_list = [part.strip() for part in ids.split(",") if part.strip()]
    products = services.list_public_products(db, limit=limit, offset=offset, ids=id_list)
    return [serialize_public_product(p) for p in products]


@router.post("/api/v1/public/products/batch", response_model=list[ProductPublicOut])
def public_products_batch(
    payload: PublicProductsBatchRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(service_any)],
):
    id_list = [str(x) for x in payload.product_ids][:100]
    products = services.batch_public_products(db, id_list)
    return [serialize_public_product(p) for p in products]

@router.get("/api/v1/public/products/{product_id}", response_model=ProductPublicOut)
def public_product(
    product_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(service_any)],
):
    product = services.get_public_product(db, str(product_id))
    return serialize_public_product(product)


@router.post("/api/v1/inventory/reserve")
def inventory_reserve(
    payload: ReserveRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(service_b2c)],
):
    return services.reserve(db, payload)


@router.post("/api/v1/inventory/unreserve")
def inventory_unreserve(
    payload: UnreserveRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(service_b2c)],
):
    return services.unreserve(db, payload)


@router.post("/api/v1/moderation/events")
def moderation_events(
    payload: ModerationEventRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(service_moderation)],
):
    return services.apply_moderation_event(db, payload)
