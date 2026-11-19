from __future__ import annotations

from uuid import UUID

from app.models import Product, SKU
from app.schemas import (
    BlockingReasonOut,
    CharacteristicOut,
    FieldReportOut,
    ImageOut,
    ProductOut,
    ProductPublicOut,
    SKUOut,
)


def serialize_sku(sku: SKU, *, include_cost: bool = True) -> SKUOut | dict:
    images = [ImageOut(id=UUID(i.id), url=i.url, ordering=i.ordering) for i in sorted(sku.images, key=lambda x: x.ordering)]
    chars = [CharacteristicOut(name=c.name, value=c.value) for c in sku.characteristics]
    if include_cost:
        return SKUOut(
            id=UUID(sku.id),
            product_id=UUID(sku.product_id),
            title=sku.title,
            price=sku.price,
            cost_price=sku.cost_price,
            stock_quantity=sku.stock_quantity,
            reserved_quantity=sku.reserved_quantity,
            deleted=sku.deleted,
            images=images,
            characteristics=chars,
        )
    return {
        "id": sku.id,
        "product_id": sku.product_id,
        "title": sku.title,
        "price": sku.price,
        "stock_quantity": max(sku.stock_quantity - sku.reserved_quantity, 0),
        "available_quantity": max(sku.stock_quantity - sku.reserved_quantity, 0),
        "deleted": sku.deleted,
        "images": [i.model_dump(mode="json") for i in images],
        "characteristics": [c.model_dump() for c in chars],
    }


def serialize_product(product: Product) -> ProductOut:
    blocked = product.status in {"BLOCKED", "HARD_BLOCKED"}
    reason_out = None
    if product.blocking_reason is not None:
        reason_out = BlockingReasonOut(
            id=UUID(product.blocking_reason.id),
            title=product.blocking_reason.title,
            comment=product.blocking_reason.comment,
        )
    elif product.blocking_reason_id:
        # Fallback if reason row missing but FK id present.
        reason_out = BlockingReasonOut(
            id=UUID(product.blocking_reason_id),
            title=product.moderator_comment or "Product blocked",
            comment=product.moderator_comment or "",
        )
    return ProductOut(
        id=UUID(product.id),
        seller_id=UUID(product.seller_id),
        category_id=UUID(product.category_id),
        title=product.title,
        slug=product.slug,
        description=product.description,
        status=product.status,  # type: ignore[arg-type]
        deleted=product.deleted,
        blocked=blocked,
        blocking_reason_id=UUID(product.blocking_reason_id) if product.blocking_reason_id else None,
        blocking_reason=reason_out,
        moderator_comment=product.moderator_comment,
        images=[
            ImageOut(id=UUID(i.id), url=i.url, ordering=i.ordering)
            for i in sorted(product.images, key=lambda x: x.ordering)
        ],
        characteristics=[CharacteristicOut(name=c.name, value=c.value) for c in product.characteristics],
        skus=[serialize_sku(s) for s in product.skus if not s.deleted],  # type: ignore[misc]
        field_reports=[
            FieldReportOut(
                field_name=fr.field_name,
                comment=fr.message,
                message=fr.message,
                reason_id=UUID(fr.reason_id) if fr.reason_id else None,
            )
            for fr in product.field_reports
        ],
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def serialize_public_product(product: Product) -> ProductPublicOut:
    visible_skus = [s for s in product.skus if not s.deleted]
    public_skus = [serialize_sku(s, include_cost=False) for s in visible_skus]
    prices = [s.price for s in visible_skus]
    return ProductPublicOut(
        id=UUID(product.id),
        title=product.title,
        slug=product.slug,
        description=product.description,
        category_id=UUID(product.category_id),
        images=[
            ImageOut(id=UUID(i.id), url=i.url, ordering=i.ordering)
            for i in sorted(product.images, key=lambda x: x.ordering)
        ],
        characteristics=[CharacteristicOut(name=c.name, value=c.value) for c in product.characteristics],
        skus=public_skus,  # type: ignore[arg-type]
        min_price=min(prices) if prices else None,
    )


def is_visible_for_b2c(product: Product) -> bool:
    if product.deleted or product.status != "MODERATED":
        return False
    if product.status == "HARD_BLOCKED":
        return False
    return any((not s.deleted) and (s.stock_quantity - s.reserved_quantity) > 0 for s in product.skus)
