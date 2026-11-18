from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.b2b_client import B2BClient
from app.models import (
    Address,
    CartItem,
    Category,
    CategoryFilter,
    Order,
    OrderItem,
    PaymentMethod,
    Product,
    SKU,
)
from app.schemas import ALLOWED_SORTS
from app.serializers import (
    append_status_history,
    is_visible,
    serialize_order,
    serialize_product_card,
    serialize_product_detail,
)


def _err(status: int, code: str, message: str, details: Any = None) -> HTTPException:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return HTTPException(status_code=status, detail=body)


def _load_products_query(category_id: str | None = None):
    q = (
        select(Product)
        .where(Product.deleted.is_(False), Product.status == "MODERATED")
        .options(
            selectinload(Product.images),
            selectinload(Product.category),
            selectinload(Product.skus),
            selectinload(Product.filter_links),
        )
    )
    if category_id:
        q = q.where(Product.category_id == category_id)
    return q


def _visible_products(db: Session, category_id: str | None = None) -> list[Product]:
    products = list(db.scalars(_load_products_query(category_id)).unique().all())
    return [p for p in products if is_visible(p)]


def list_catalog_products(
    db: Session,
    *,
    category_id: str | None,
    sort: str | None,
    search: str | None,
    limit: int,
    offset: int,
    filters: dict[str, Any] | None = None,
) -> dict:
    if sort and sort not in ALLOWED_SORTS:
        raise _err(
            400,
            "INVALID_REQUEST",
            "Invalid sort parameter. Allowed: rating, popularity, price_asc, price_desc, date_desc, discount_desc",
        )
    if search is not None:
        trimmed = search.strip()
        if len(trimmed) < 4:
            raise _err(400, "INVALID_REQUEST", "Search query must be at least 3 characters")
        search = trimmed

    products = _visible_products(db, category_id)

    if search:
        needle = search.lower()
        products = [
            p
            for p in products
            if needle in p.title.lower() or needle in (p.description or "").lower()
        ]

    if filters:
        attr_filters = {k: v for k, v in filters.items() if k not in {"price_min", "price_max", "category_id", "seller_id"}}
        price_min = filters.get("price_min")
        price_max = filters.get("price_max")
        if price_min is not None:
            products = [p for p in products if min((s.price for s in p.skus if not s.deleted), default=0) >= int(price_min)]
        if price_max is not None:
            products = [p for p in products if min((s.price for s in p.skus if not s.deleted), default=0) <= int(price_max)]
        for key, value in attr_filters.items():
            wanted = value if isinstance(value, list) else [value]
            products = [
                p
                for p in products
                if any(link.value in wanted and (link.filter_id == key or True) for link in p.filter_links)
                or any(
                    c.name.lower() == key.lower() and c.value in wanted
                    for c in p.characteristics
                )
            ]

    sort_key = sort or "rating"
    if sort_key == "price_asc":
        products.sort(key=lambda p: min((s.price for s in p.skus if not s.deleted), default=0))
    elif sort_key == "price_desc":
        products.sort(key=lambda p: min((s.price for s in p.skus if not s.deleted), default=0), reverse=True)
    elif sort_key in {"date_desc", "new"}:
        products.sort(key=lambda p: p.created_at, reverse=True)
    elif sort_key == "discount_desc":
        products.sort(key=lambda p: p.discount, reverse=True)
    elif sort_key == "popularity":
        products.sort(key=lambda p: p.popularity, reverse=True)
    else:
        products.sort(key=lambda p: p.rating, reverse=True)

    total = len(products)
    page = products[offset : offset + limit]
    return {
        "items": [serialize_product_card(p) for p in page],
        "total_count": total,
        "limit": limit,
        "offset": offset,
    }


def get_product_card(db: Session, product_id: str) -> dict:
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.images),
            selectinload(Product.characteristics),
            selectinload(Product.category),
            selectinload(Product.skus).selectinload(SKU.images),
            selectinload(Product.skus).selectinload(SKU.characteristics),
        )
    )
    if not product or product.deleted or product.status in {"BLOCKED", "HARD_BLOCKED"}:
        raise _err(404, "NOT_FOUND", "Product not found")
    if product.status != "MODERATED":
        raise _err(404, "NOT_FOUND", "Product not found")
    return serialize_product_detail(product)


def get_facets(db: Session, category_id: str) -> dict:
    category = db.get(Category, category_id)
    if not category:
        raise _err(404, "NOT_FOUND", f"Category with id {category_id} not found")

    filters = list(
        db.scalars(
            select(CategoryFilter)
            .where(CategoryFilter.category_id == category_id)
            .options(selectinload(CategoryFilter.values))
        ).all()
    )
    products = _visible_products(db, category_id)
    facets: list[dict] = []
    filter_meta: list[dict] = []

    for filt in filters:
        values = [v.value for v in filt.values]
        filter_meta.append(
            {
                "id": filt.id,
                "name": filt.name,
                "type": filt.filter_type,
                "value": values,
            }
        )
        facet_values = []
        for value in values:
            count = sum(
                1
                for p in products
                if any(link.filter_id == filt.id and link.value == value for link in p.filter_links)
            )
            facet_values.append({"value": value, "count": count})
        facets.append({"name": filt.slug or filt.name, "values": facet_values})

    return {"category_id": category_id, "filters": filter_meta, "facets": facets}


def resolve_cart_identity(
    buyer_id: str | None,
    session_id: str | None,
    *,
    require_any: bool = True,
) -> tuple[str | None, str | None]:
    if buyer_id:
        return buyer_id, None
    if session_id:
        return None, session_id
    if require_any:
        raise _err(400, "MISSING_CART_IDENTITY", "Provide Authorization or X-Session-Id")
    return None, None


def _cart_query(user_id: str | None, session_id: str | None):
    q = select(CartItem).options(
        selectinload(CartItem.sku).selectinload(SKU.images),
        selectinload(CartItem.sku).selectinload(SKU.product).selectinload(Product.images),
    )
    if user_id:
        return q.where(CartItem.user_id == user_id)
    return q.where(CartItem.session_id == session_id)


def _build_cart_response(
    db: Session,
    b2b: B2BClient,
    items: list[CartItem],
    *,
    cart_id: str | None = None,
) -> dict:
    enrichment = b2b.enrich_skus(db, [i.sku_id for i in items])
    out_items = []
    subtotal = 0
    items_count = 0
    all_valid = True
    latest = None
    for item in items:
        data = enrichment.get(item.sku_id)
        if not data:
            available = False
            unit_price = item.unit_price_at_add
            available_qty = 0
            product_id = ""
            name = "Unavailable"
            sku_code = item.sku_id
            image = None
        else:
            available_qty = int(data["active_quantity"])
            blocked = data["product_status"] in {"BLOCKED", "HARD_BLOCKED"} or data["product_deleted"]
            available = (not blocked) and available_qty > 0 and available_qty >= item.quantity
            unit_price = int(data["price"])
            product_id = data["product_id"]
            name = f"{data['product_title']} — {data['sku_name']}"
            sku_code = data["sku_code"]
            image = data["image"]
        line_total = unit_price * item.quantity if available else 0
        if not available:
            all_valid = False
        subtotal += line_total
        items_count += item.quantity
        if latest is None or (item.updated_at and item.updated_at > latest):
            latest = item.updated_at
        out_items.append(
            {
                "sku_id": item.sku_id,
                "product_id": product_id,
                "name": name,
                "sku_code": sku_code,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "unit_price_at_add": item.unit_price_at_add,
                "line_total": line_total,
                "available_quantity": available_qty if data else 0,
                "is_available": available,
                "image": image,
            }
        )
    return {
        "id": cart_id or (items[0].user_id or items[0].session_id if items else None),
        "items": out_items,
        "items_count": items_count,
        "subtotal": subtotal,
        "is_valid": all_valid if items else True,
        "updated_at": latest,
    }


def get_cart(db: Session, b2b: B2BClient, user_id: str | None, session_id: str | None) -> dict:
    user_id, session_id = resolve_cart_identity(user_id, session_id)
    items = list(db.scalars(_cart_query(user_id, session_id)).all())
    return _build_cart_response(db, b2b, items, cart_id=user_id or session_id)


def clear_cart(db: Session, user_id: str | None, session_id: str | None) -> None:
    user_id, session_id = resolve_cart_identity(user_id, session_id)
    items = list(db.scalars(_cart_query(user_id, session_id)).all())
    for item in items:
        db.delete(item)
    db.commit()


def add_cart_item(
    db: Session,
    b2b: B2BClient,
    user_id: str | None,
    session_id: str | None,
    sku_id: str,
    quantity: int,
) -> dict:
    user_id, session_id = resolve_cart_identity(user_id, session_id)
    enrichment = b2b.enrich_skus(db, [sku_id])
    data = enrichment.get(sku_id)
    if not data:
        raise _err(404, "NOT_FOUND", "SKU not found or unavailable")
    if data["product_deleted"] or data["product_status"] in {"BLOCKED", "HARD_BLOCKED"}:
        raise _err(404, "NOT_FOUND", "SKU not found or unavailable")
    if data["active_quantity"] < quantity:
        raise _err(409, "INSUFFICIENT_STOCK", "Not enough stock")

    existing = db.scalar(
        select(CartItem).where(
            CartItem.sku_id == sku_id,
            CartItem.user_id == user_id if user_id else CartItem.session_id == session_id,
        )
    )
    if existing:
        existing.quantity += quantity
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            CartItem(
                user_id=user_id,
                session_id=session_id,
                sku_id=sku_id,
                quantity=quantity,
                unit_price_at_add=int(data["price"]),
            )
        )
    db.commit()
    return get_cart(db, b2b, user_id, session_id)


def update_cart_item(
    db: Session,
    b2b: B2BClient,
    user_id: str | None,
    session_id: str | None,
    sku_id: str,
    quantity: int,
) -> dict:
    user_id, session_id = resolve_cart_identity(user_id, session_id)
    item = db.scalar(
        select(CartItem).where(
            CartItem.sku_id == sku_id,
            CartItem.user_id == user_id if user_id else CartItem.session_id == session_id,
        )
    )
    if not item:
        raise _err(404, "NOT_FOUND", "Cart item not found")
    enrichment = b2b.enrich_skus(db, [sku_id])
    data = enrichment.get(sku_id)
    if not data:
        raise _err(404, "NOT_FOUND", "SKU not found or unavailable")
    if data["active_quantity"] < quantity:
        raise _err(409, "INSUFFICIENT_STOCK", "Not enough stock")
    item.quantity = quantity
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_cart(db, b2b, user_id, session_id)


def delete_cart_item(
    db: Session,
    b2b: B2BClient,
    user_id: str | None,
    session_id: str | None,
    sku_id: str,
) -> dict:
    user_id, session_id = resolve_cart_identity(user_id, session_id)
    item = db.scalar(
        select(CartItem).where(
            CartItem.sku_id == sku_id,
            CartItem.user_id == user_id if user_id else CartItem.session_id == session_id,
        )
    )
    if item:
        db.delete(item)
        db.commit()
    return get_cart(db, b2b, user_id, session_id)


def validate_cart(db: Session, b2b: B2BClient, user_id: str | None, session_id: str | None) -> dict:
    user_id, session_id = resolve_cart_identity(user_id, session_id)
    items = list(db.scalars(_cart_query(user_id, session_id)).all())
    cart = _build_cart_response(db, b2b, items, cart_id=user_id or session_id)
    enrichment = b2b.enrich_skus(db, [i.sku_id for i in items])
    issues: list[dict] = []
    for item in items:
        data = enrichment.get(item.sku_id)
        if not data or data["product_deleted"]:
            issues.append(
                {
                    "sku_id": item.sku_id,
                    "type": "PRODUCT_DELETED",
                    "message": "Product deleted",
                }
            )
            continue
        if data["product_status"] in {"BLOCKED", "HARD_BLOCKED"}:
            issues.append(
                {
                    "sku_id": item.sku_id,
                    "type": "PRODUCT_BLOCKED",
                    "message": "Product blocked",
                }
            )
            continue
        if data["active_quantity"] <= 0:
            issues.append(
                {
                    "sku_id": item.sku_id,
                    "type": "OUT_OF_STOCK",
                    "message": "Out of stock",
                }
            )
            continue
        if data["active_quantity"] < item.quantity:
            issues.append(
                {
                    "sku_id": item.sku_id,
                    "type": "QUANTITY_REDUCED",
                    "message": "Available quantity reduced",
                    "old_value": item.quantity,
                    "new_value": data["active_quantity"],
                }
            )
        if int(data["price"]) != item.unit_price_at_add:
            issues.append(
                {
                    "sku_id": item.sku_id,
                    "type": "PRICE_CHANGED",
                    "message": "Price changed",
                    "old_value": item.unit_price_at_add,
                    "new_value": int(data["price"]),
                }
            )
    return {"is_valid": len(issues) == 0 and bool(items), "cart": cart, "issues": issues}


def merge_carts(db: Session, b2b: B2BClient, user_id: str, session_id: str) -> dict:
    guest_items = list(db.scalars(select(CartItem).where(CartItem.session_id == session_id)).all())
    for guest in guest_items:
        existing = db.scalar(
            select(CartItem).where(CartItem.user_id == user_id, CartItem.sku_id == guest.sku_id)
        )
        if existing:
            existing.quantity = max(existing.quantity, guest.quantity)
            db.delete(guest)
        else:
            guest.user_id = user_id
            guest.session_id = None
    db.commit()
    return get_cart(db, b2b, user_id, None)


def _request_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def create_order(
    db: Session,
    b2b: B2BClient,
    buyer_id: str,
    payload: dict,
    idempotency_key: str,
) -> tuple[dict, int]:
    existing = db.scalar(select(Order).where(Order.idempotency_key == idempotency_key))
    req_hash = _request_hash(payload)
    if existing:
        if existing.idempotency_request_hash and existing.idempotency_request_hash != req_hash:
            raise _err(409, "IDEMPOTENCY_CONFLICT", "Idempotency key already used with different body")
        order = db.scalar(
            select(Order)
            .where(Order.id == existing.id)
            .options(
                selectinload(Order.items),
                selectinload(Order.address),
                selectinload(Order.payment_method),
            )
        )
        return serialize_order(order), 201  # type: ignore[arg-type]

    address = db.scalar(select(Address).where(Address.id == str(payload["address_id"]), Address.buyer_id == buyer_id))
    if not address:
        raise _err(404, "NOT_FOUND", "Address not found")
    payment = db.scalar(
        select(PaymentMethod).where(
            PaymentMethod.id == str(payload["payment_method_id"]),
            PaymentMethod.buyer_id == buyer_id,
        )
    )
    if not payment:
        raise _err(404, "NOT_FOUND", "Payment method not found")

    cart_items = list(db.scalars(_cart_query(buyer_id, None)).all())
    if not cart_items:
        raise _err(400, "INVALID_REQUEST", "Cart is empty")

    validation = validate_cart(db, b2b, buyer_id, None)
    if not validation["is_valid"]:
        raise HTTPException(status_code=422, detail=validation)

    enrichment = b2b.enrich_skus(db, [i.sku_id for i in cart_items])
    reserve_items = [{"sku_id": i.sku_id, "quantity": i.quantity} for i in cart_items]
    order_id = str(uuid4())
    reserve_result = b2b.reserve(
        db,
        order_id=order_id,
        idempotency_key=idempotency_key,
        items=reserve_items,
    )
    if not reserve_result.get("reserved"):
        raise _err(
            409,
            "RESERVE_FAILED",
            "Partial reserve failed",
            details=reserve_result.get("failed_items", []),
        )

    now = datetime.now(timezone.utc)
    order = Order(
        id=order_id,
        buyer_id=buyer_id,
        status="PAID",
        number=f"NM-{now.strftime('%Y%m%d')}-{order_id[:8]}",
        address_id=address.id,
        payment_method_id=payment.id,
        comment=payload.get("comment"),
        idempotency_key=idempotency_key,
        idempotency_request_hash=req_hash,
        paid_at=now,
        delivery_cost=0,
    )
    append_status_history(order, "PAID")
    subtotal = 0
    for item in cart_items:
        data = enrichment[item.sku_id]
        unit_price = int(data["price"])
        line_total = unit_price * item.quantity
        subtotal += line_total
        order.items.append(
            OrderItem(
                sku_id=item.sku_id,
                product_id=data["product_id"],
                name=f"{data['product_title']} — {data['sku_name']}",
                sku_code=data["sku_code"],
                quantity=item.quantity,
                unit_price=unit_price,
                line_total=line_total,
                image_url=(data["image"] or {}).get("url") if data.get("image") else None,
            )
        )
        db.delete(item)
    order.subtotal = subtotal
    order.total = subtotal
    db.add(order)
    db.commit()
    order = db.scalar(
        select(Order)
        .where(Order.id == order.id)
        .options(
            selectinload(Order.items),
            selectinload(Order.address),
            selectinload(Order.payment_method),
        )
    )
    return serialize_order(order), 201  # type: ignore[arg-type]


CANCELLABLE = {"CREATED", "PAID", "ASSEMBLING", "DELIVERING"}


def cancel_order(
    db: Session,
    b2b: B2BClient,
    buyer_id: str,
    order_id: str,
    *,
    reason: str | None = None,
    restore_cart: bool = False,
) -> dict:
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.address),
            selectinload(Order.payment_method),
        )
    )
    if not order or order.buyer_id != buyer_id:
        raise _err(404, "NOT_FOUND", "Order not found")
    if order.status not in CANCELLABLE:
        raise _err(
            409,
            "CANCEL_NOT_ALLOWED",
            "Can't cancel order in this state",
            details={"current_status": order.status},
        )

    items = [{"sku_id": i.sku_id, "quantity": i.quantity} for i in order.items]
    try:
        b2b.unreserve(db, order_id=order.id, items=items)
        order.status = "CANCELLED"
    except HTTPException:
        order.status = "CANCEL_PENDING"
    order.cancel_reason = reason
    order.updated_at = datetime.now(timezone.utc)
    append_status_history(order, order.status, reason=reason)

    if restore_cart and order.status == "CANCELLED":
        for item in order.items:
            existing = db.scalar(
                select(CartItem).where(CartItem.user_id == buyer_id, CartItem.sku_id == item.sku_id)
            )
            if existing:
                existing.quantity += item.quantity
            else:
                db.add(
                    CartItem(
                        user_id=buyer_id,
                        sku_id=item.sku_id,
                        quantity=item.quantity,
                        unit_price_at_add=item.unit_price,
                    )
                )
    db.commit()
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.address),
            selectinload(Order.payment_method),
        )
    )
    return serialize_order(order)  # type: ignore[arg-type]


def list_orders(db: Session, buyer_id: str, *, limit: int, offset: int, status: str | None) -> dict:
    q = (
        select(Order)
        .where(Order.buyer_id == buyer_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.address),
            selectinload(Order.payment_method),
        )
        .order_by(Order.created_at.desc())
    )
    if status:
        q = q.where(Order.status == status)
    orders = list(db.scalars(q).all())
    total = len(orders)
    page = orders[offset : offset + limit]
    return {
        "items": [serialize_order(o) for o in page],
        "total_count": total,
        "limit": limit,
        "offset": offset,
    }


def get_order(db: Session, buyer_id: str, order_id: str) -> dict:
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.address),
            selectinload(Order.payment_method),
        )
    )
    if not order or order.buyer_id != buyer_id:
        raise _err(404, "NOT_FOUND", "Order not found")
    return serialize_order(order)
