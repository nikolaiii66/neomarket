from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.auth import optional_buyer, require_buyer
from app.b2b_client import B2BClient, get_b2b_client
from app.db import get_db
from app import services
from app.schemas import (
    CartItemAddRequest,
    CartItemQuantityUpdate,
    OrderCancelRequest,
    OrderCreateRequest,
)

router = APIRouter()


def b2b_dep() -> B2BClient:
    return get_b2b_client()


@router.get("/api/v1/catalog/products")
@router.get("/api/v1/products")
def catalog_products(
    db: Annotated[Session, Depends(get_db)],
    category_id: str | None = None,
    sort: str | None = None,
    search: str | None = Query(default=None),
    q: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return services.list_catalog_products(
        db,
        category_id=category_id,
        sort=sort,
        search=search or q,
        limit=limit,
        offset=offset,
        filters=None,
    )


@router.get("/api/v1/catalog/products/{product_id}")
@router.get("/api/v1/products/{product_id}")
def product_card(product_id: UUID, db: Annotated[Session, Depends(get_db)]):
    return services.get_product_card(db, str(product_id))


@router.get("/api/v1/catalog/facets")
@router.get("/api/v1/catalog/facets/")
def catalog_facets(category_id: UUID, db: Annotated[Session, Depends(get_db)]):
    return services.get_facets(db, str(category_id))


@router.get("/api/v1/cart")
def get_cart(
    db: Annotated[Session, Depends(get_db)],
    b2b: Annotated[B2BClient, Depends(b2b_dep)],
    buyer_id: Annotated[str | None, Depends(optional_buyer)] = None,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
):
    return services.get_cart(db, b2b, buyer_id, x_session_id)


@router.delete("/api/v1/cart", status_code=204)
def delete_cart(
    db: Annotated[Session, Depends(get_db)],
    buyer_id: Annotated[str | None, Depends(optional_buyer)] = None,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
):
    services.clear_cart(db, buyer_id, x_session_id)
    return Response(status_code=204)


@router.post("/api/v1/cart/items")
def add_item(
    payload: CartItemAddRequest,
    db: Annotated[Session, Depends(get_db)],
    b2b: Annotated[B2BClient, Depends(b2b_dep)],
    buyer_id: Annotated[str | None, Depends(optional_buyer)] = None,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
):
    return services.add_cart_item(db, b2b, buyer_id, x_session_id, str(payload.sku_id), payload.quantity)


@router.patch("/api/v1/cart/items/{sku_id}")
def patch_item(
    sku_id: UUID,
    payload: CartItemQuantityUpdate,
    db: Annotated[Session, Depends(get_db)],
    b2b: Annotated[B2BClient, Depends(b2b_dep)],
    buyer_id: Annotated[str | None, Depends(optional_buyer)] = None,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
):
    return services.update_cart_item(db, b2b, buyer_id, x_session_id, str(sku_id), payload.quantity)


@router.delete("/api/v1/cart/items/{sku_id}")
def remove_item(
    sku_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    b2b: Annotated[B2BClient, Depends(b2b_dep)],
    buyer_id: Annotated[str | None, Depends(optional_buyer)] = None,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
):
    return services.delete_cart_item(db, b2b, buyer_id, x_session_id, str(sku_id))


@router.post("/api/v1/cart/validate")
def cart_validate(
    db: Annotated[Session, Depends(get_db)],
    b2b: Annotated[B2BClient, Depends(b2b_dep)],
    buyer_id: Annotated[str | None, Depends(optional_buyer)] = None,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
):
    return services.validate_cart(db, b2b, buyer_id, x_session_id)


@router.post("/api/v1/cart/merge")
def cart_merge(
    db: Annotated[Session, Depends(get_db)],
    b2b: Annotated[B2BClient, Depends(b2b_dep)],
    buyer_id: Annotated[str, Depends(require_buyer)],
    x_session_id: Annotated[str, Header(alias="X-Session-Id")],
):
    return services.merge_carts(db, b2b, buyer_id, x_session_id)


@router.post("/api/v1/orders", status_code=201)
def create_order(
    payload: OrderCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    b2b: Annotated[B2BClient, Depends(b2b_dep)],
    buyer_id: Annotated[str, Depends(require_buyer)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if not idempotency_key:
        from app.services import _err

        raise _err(400, "INVALID_REQUEST", "Idempotency-Key header is required")
    body = payload.model_dump(mode="json")
    result, _ = services.create_order(db, b2b, buyer_id, body, idempotency_key)
    return result


@router.get("/api/v1/orders")
def list_orders(
    db: Annotated[Session, Depends(get_db)],
    buyer_id: Annotated[str, Depends(require_buyer)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = None,
):
    return services.list_orders(db, buyer_id, limit=limit, offset=offset, status=status)


@router.get("/api/v1/orders/{order_id}")
def get_order(
    order_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    buyer_id: Annotated[str, Depends(require_buyer)],
):
    return services.get_order(db, buyer_id, str(order_id))


@router.post("/api/v1/orders/{order_id}/cancel")
def cancel_order(
    order_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    b2b: Annotated[B2BClient, Depends(b2b_dep)],
    buyer_id: Annotated[str, Depends(require_buyer)],
    payload: OrderCancelRequest | None = None,
):
    body = payload or OrderCancelRequest()
    return services.cancel_order(
        db,
        b2b,
        buyer_id,
        str(order_id),
        reason=body.reason,
        restore_cart=body.restore_cart,
    )
