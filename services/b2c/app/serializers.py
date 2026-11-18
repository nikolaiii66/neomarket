from __future__ import annotations

import json
from datetime import datetime, timezone

from app.models import Address, Order, PaymentMethod, Product, SKU


def product_min_price(product: Product) -> int:
    prices = [s.price for s in product.skus if not s.deleted]
    return min(prices) if prices else 0


def product_has_stock(product: Product) -> bool:
    return any(not s.deleted and s.active_quantity > 0 for s in product.skus)


def is_visible(product: Product) -> bool:
    return (
        product.status == "MODERATED"
        and not product.deleted
        and product_has_stock(product)
    )


def serialize_product_card(product: Product, *, is_in_cart: bool = False) -> dict:
    images = sorted(product.images, key=lambda i: i.ordering)
    image_objs = [
        {
            "id": img.id,
            "url": img.url,
            "alt": img.alt,
            "ordering": img.ordering,
            "is_main": img.is_main,
        }
        for img in images
    ]
    min_price = product_min_price(product)
    main_image = image_objs[0]["url"] if image_objs else ""
    return {
        "id": product.id,
        "name": product.title,
        "title": product.title,
        "slug": product.slug,
        "min_price": min_price,
        "price": min_price,
        "old_price": None,
        "has_stock": product_has_stock(product),
        "in_stock": product_has_stock(product),
        "is_in_cart": is_in_cart,
        "rating": product.rating,
        "reviews_count": 0,
        "images": image_objs,
        "image": main_image,
        "category": {
            "id": product.category_id,
            "name": product.category.name if product.category else "",
            "parent_id": product.category.parent_id if product.category else None,
            "level": 0,
            "path": [product.category.name] if product.category else [],
        },
        "seller": {"id": product.seller_id, "display_name": "Seller"},
    }


def serialize_product_detail(product: Product) -> dict:
    card = serialize_product_card(product)
    skus = []
    for sku in sorted(product.skus, key=lambda s: s.created_at):
        if sku.deleted:
            continue
        skus.append(serialize_sku(sku))
    return {
        **card,
        "description": product.description,
        "status": product.status,
        "attributes": {c.name: c.value for c in product.characteristics},
        "characteristics": [{"name": c.name, "value": c.value} for c in product.characteristics],
        "skus": skus,
        "images": [img.url for img in sorted(product.images, key=lambda i: i.ordering)],
    }


def serialize_sku(sku: SKU) -> dict:
    images = [
        {
            "id": img.id,
            "url": img.url,
            "alt": img.alt,
            "ordering": img.ordering,
            "is_main": img.is_main,
        }
        for img in sorted(sku.images, key=lambda i: i.ordering)
    ]
    return {
        "id": sku.id,
        "name": sku.name,
        "sku_code": sku.sku_code or sku.id,
        "price": sku.price,
        "old_price": sku.old_price,
        "available_quantity": sku.active_quantity,
        "active_quantity": sku.active_quantity,
        "in_stock": sku.active_quantity > 0,
        "attributes": {c.name: c.value for c in sku.characteristics},
        "characteristics": [{"name": c.name, "value": c.value} for c in sku.characteristics],
        "images": images,
        "image": images[0]["url"] if images else None,
    }


def serialize_address(address: Address) -> dict:
    return {
        "id": address.id,
        "country": address.country,
        "region": address.region,
        "city": address.city,
        "street": address.street,
        "building": address.building,
        "apartment": address.apartment,
        "postal_code": address.postal_code,
        "recipient_name": address.recipient_name,
        "recipient_phone": address.recipient_phone,
        "is_default": address.is_default,
        "comment": address.comment,
        "created_at": address.created_at,
    }


def serialize_payment_method(method: PaymentMethod) -> dict:
    return {
        "id": method.id,
        "type": method.type,
        "card_last4": method.card_last4,
        "card_brand": method.card_brand,
        "is_default": method.is_default,
        "created_at": method.created_at,
    }


def serialize_order(order: Order) -> dict:
    history = json.loads(order.status_history_json or "[]")
    return {
        "id": order.id,
        "number": order.number or None,
        "buyer_id": order.buyer_id,
        "status": order.status,
        "status_history": history,
        "items": [
            {
                "sku_id": item.sku_id,
                "product_id": item.product_id,
                "name": item.name,
                "sku_code": item.sku_code,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.line_total,
                "image_url": item.image_url,
            }
            for item in order.items
        ],
        "subtotal": order.subtotal,
        "delivery_cost": order.delivery_cost,
        "total": order.total,
        "address": serialize_address(order.address) if order.address else {
            "id": order.address_id or order.id,
            "country": "RU",
            "city": "",
            "street": "",
            "building": "",
        },
        "payment_method": serialize_payment_method(order.payment_method) if order.payment_method else None,
        "comment": order.comment,
        "cancel_reason": order.cancel_reason,
        "created_at": order.created_at,
        "paid_at": order.paid_at,
        "delivered_at": order.delivered_at,
    }


def append_status_history(order: Order, status: str, reason: str | None = None) -> None:
    history = json.loads(order.status_history_json or "[]")
    history.append(
        {
            "status": status,
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }
    )
    order.status_history_json = json.dumps(history)
