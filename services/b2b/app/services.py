from __future__ import annotations

import hashlib
import json
import re
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Category,
    FieldReport,
    IdempotencyRecord,
    OutboxEvent,
    Product,
    ProductCharacteristic,
    ProductImage,
    Reservation,
    SKU,
    SKUCharacteristic,
    SKUImage,
)
from app.schemas import (
    InventoryItem,
    ModerationEventRequest,
    ProductCreate,
    ReserveRequest,
    SKUCreate,
    UnreserveRequest,
)
from app.serializers import is_visible_for_b2c, serialize_product, serialize_public_product


def _slugify(title: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-") or "product"
    return f"{base}-{uuid4().hex[:8]}"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _load_product(db: Session, product_id: str) -> Product | None:
    return db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.images),
            selectinload(Product.characteristics),
            selectinload(Product.field_reports),
            selectinload(Product.skus).selectinload(SKU.images),
            selectinload(Product.skus).selectinload(SKU.characteristics),
        )
    )


def ensure_category(db: Session, category_id: str) -> Category:
    cat = db.get(Category, category_id)
    if not cat:
        raise _err(400, "INVALID_REQUEST", "Category not found")
    return cat


def create_product(db: Session, seller_id: str, payload: ProductCreate) -> Product:
    if payload.category_id is None:
        raise _err(400, "INVALID_REQUEST", "category_id is required")
    if payload.images is None or len(payload.images) < 1:
        raise _err(400, "INVALID_REQUEST", "At least one image is required")

    ensure_category(db, str(payload.category_id))
    product = Product(
        seller_id=seller_id,
        category_id=str(payload.category_id),
        title=payload.title,
        description=payload.description,
        slug=payload.slug or _slugify(payload.title),
        status="CREATED",
    )
    for img in payload.images:
        product.images.append(ProductImage(url=img.url, ordering=img.ordering))
    for ch in payload.characteristics:
        product.characteristics.append(ProductCharacteristic(name=ch.name, value=ch.value))
    db.add(product)
    db.commit()
    return _load_product(db, product.id)  # type: ignore[return-value]


def create_sku(db: Session, seller_id: str, payload: SKUCreate) -> tuple[SKU, Product]:
    product = _load_product(db, str(payload.product_id))
    if not product or product.deleted:
        raise _err(404, "not_found", "Product not found")
    if product.seller_id != seller_id:
        raise _err(403, "forbidden", "Not your product")
    if product.status == "HARD_BLOCKED":
        raise _err(403, "hard_blocked", "Product is hard-blocked")
    if payload.images is None or len(payload.images) < 1:
        raise _err(400, "INVALID_REQUEST", "At least one image is required")

    # Canon US-B2B-02: only the first SKU on a CREATED product transitions + emits CREATED.
    # Subsequent SKUs do not change status and do not emit moderation events.
    was_first = not any(not s.deleted for s in product.skus)
    sku = SKU(
        product_id=product.id,
        title=payload.title,
        price=payload.price,
        cost_price=payload.cost_price,
        stock_quantity=payload.stock_quantity,
    )
    for img in payload.images:
        sku.images.append(SKUImage(url=img.url, ordering=img.ordering))
    for ch in payload.characteristics:
        sku.characteristics.append(SKUCharacteristic(name=ch.name, value=ch.value))
    db.add(sku)

    if was_first and product.status == "CREATED":
        product.status = "ON_MODERATION"
        product.blocking_reason_id = None
        product.moderator_comment = None
        product.field_reports.clear()
        idempotency_key = str(uuid4())
        db.add(
            OutboxEvent(
                topic="moderation",
                payload_json=json.dumps(
                    {
                        "event_type": "CREATED",
                        "product_id": product.id,
                        "seller_id": product.seller_id,
                        "idempotency_key": idempotency_key,
                        "headers": {"X-Service-Key": "b2b-service-key"},
                    }
                ),
            )
        )
    db.commit()
    product = _load_product(db, product.id)  # type: ignore[assignment]
    sku = next(s for s in product.skus if s.id == sku.id)
    return sku, product


def get_product_for_seller(db: Session, seller_id: str, product_id: str) -> Product:
    product = _load_product(db, product_id)
    if not product:
        raise _err(404, "not_found", "Product not found")
    if product.seller_id != seller_id:
        raise _err(404, "not_found", "Product not found")
    return product


def list_public_products(db: Session, *, limit: int = 20, offset: int = 0) -> list[Product]:
    products = db.scalars(
        select(Product).options(
            selectinload(Product.images),
            selectinload(Product.characteristics),
            selectinload(Product.skus).selectinload(SKU.images),
            selectinload(Product.skus).selectinload(SKU.characteristics),
        )
    ).all()
    visible = [p for p in products if is_visible_for_b2c(p)]
    return visible[offset : offset + limit]


def get_public_product(db: Session, product_id: str) -> Product:
    product = _load_product(db, product_id)
    if not product or not is_visible_for_b2c(product):
        raise _err(404, "not_found", "Product not found")
    return product


def _hash_payload(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _idempotent(
    db: Session, scope: str, key: str, request_hash: str, compute
):
    existing = db.scalar(
        select(IdempotencyRecord).where(IdempotencyRecord.scope == scope, IdempotencyRecord.key == key)
    )
    if existing:
        if existing.request_hash != request_hash:
            raise _err(409, "idempotency_conflict", "Idempotency key reused with different payload")
        return json.loads(existing.response_json), existing.status_code

    body, status = compute()
    db.add(
        IdempotencyRecord(
            scope=scope,
            key=key,
            request_hash=request_hash,
            response_json=json.dumps(body, default=str),
            status_code=status,
        )
    )
    db.commit()
    return body, status


def reserve(db: Session, payload: ReserveRequest) -> dict:
    req_hash = _hash_payload(payload.model_dump(mode="json"))

    def compute():
        skus: list[tuple[SKU, int]] = []
        for item in payload.items:
            sku = db.get(SKU, str(item.sku_id))
            if not sku or sku.deleted:
                raise _err(404, "sku_not_found", f"SKU {item.sku_id} not found")
            available = sku.stock_quantity - sku.reserved_quantity
            if available < item.quantity:
                raise _err(409, "insufficient_stock", "Not enough stock for one or more SKUs")
            skus.append((sku, item.quantity))

        for sku, qty in skus:
            sku.reserved_quantity += qty
            existing = db.scalar(
                select(Reservation).where(
                    Reservation.order_id == str(payload.order_id),
                    Reservation.sku_id == sku.id,
                )
            )
            if existing:
                existing.quantity += qty
                existing.active = True
            else:
                db.add(Reservation(order_id=str(payload.order_id), sku_id=sku.id, quantity=qty, active=True))
            if sku.stock_quantity - sku.reserved_quantity <= 0:
                db.add(
                    OutboxEvent(
                        topic="b2c",
                        payload_json=json.dumps({"event_type": "SKU_OUT_OF_STOCK", "sku_id": sku.id}),
                    )
                )
        db.flush()
        body = {
            "order_id": str(payload.order_id),
            "items": [{"sku_id": str(i.sku_id), "quantity": i.quantity} for i in payload.items],
        }
        return body, 200

    body, status = _idempotent(db, "reserve", str(payload.idempotency_key), req_hash, compute)
    if status != 200:
        raise _err(status, "reserve_failed", "Reserve failed")
    return body


def unreserve(db: Session, payload: UnreserveRequest) -> dict:
    # Use order_id as idempotency scope key
    req_hash = _hash_payload(payload.model_dump(mode="json"))

    def compute():
        for item in payload.items:
            reservation = db.scalar(
                select(Reservation).where(
                    Reservation.order_id == str(payload.order_id),
                    Reservation.sku_id == str(item.sku_id),
                    Reservation.active.is_(True),
                )
            )
            sku = db.get(SKU, str(item.sku_id))
            if not reservation or not sku:
                raise _err(409, "unreserve_conflict", "Active reservation not found")
            if reservation.quantity < item.quantity:
                raise _err(409, "unreserve_conflict", "Cannot unreserve more than reserved")
            sku.reserved_quantity = max(sku.reserved_quantity - item.quantity, 0)
            reservation.quantity -= item.quantity
            if reservation.quantity == 0:
                reservation.active = False
        db.flush()
        return {
            "order_id": str(payload.order_id),
            "items": [{"sku_id": str(i.sku_id), "quantity": i.quantity} for i in payload.items],
        }, 200

    body, status = _idempotent(db, "unreserve", str(payload.order_id), req_hash, compute)
    return body


def apply_moderation_event(db: Session, payload: ModerationEventRequest) -> dict:
    req_hash = _hash_payload(payload.model_dump(mode="json"))

    def compute():
        product = _load_product(db, str(payload.product_id))
        if not product:
            raise _err(404, "not_found", "Product not found")
        if product.status == "HARD_BLOCKED" and payload.event_type != "BLOCKED":
            # ignore edits conceptually; still accept idempotent write
            return {"status": product.status}, 200

        if payload.event_type == "MODERATED":
            product.status = "MODERATED"
            product.blocking_reason_id = None
            product.moderator_comment = payload.moderator_comment
            product.field_reports.clear()
        elif payload.event_type == "BLOCKED":
            if not payload.blocking_reason_id:
                raise _err(400, "validation_error", "blocking_reason_id is required for BLOCKED")
            if payload.hard_block:
                product.status = "HARD_BLOCKED"
            else:
                product.status = "BLOCKED"
            product.blocking_reason_id = str(payload.blocking_reason_id)
            product.moderator_comment = payload.moderator_comment
            product.field_reports.clear()
            for fr in payload.field_reports or []:
                product.field_reports.append(
                    FieldReport(
                        field_name=fr.field_name,
                        message=fr.message,
                        reason_id=str(fr.reason_id) if fr.reason_id else None,
                    )
                )
            if payload.hard_block:
                db.add(
                    OutboxEvent(
                        topic="b2c",
                        payload_json=json.dumps(
                            {"event_type": "PRODUCT_BLOCKED", "product_id": product.id, "hard_block": True}
                        ),
                    )
                )
        db.flush()
        return {"status": product.status, "product_id": product.id}, 200

    body, status = _idempotent(db, "moderation_event", str(payload.idempotency_key), req_hash, compute)
    return body


# re-export serializers used by routes
__all__ = [
    "create_product",
    "create_sku",
    "get_product_for_seller",
    "list_public_products",
    "get_public_product",
    "reserve",
    "unreserve",
    "apply_moderation_event",
    "serialize_product",
    "serialize_public_product",
    "ensure_category",
]
