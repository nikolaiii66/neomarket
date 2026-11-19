"""US-ORD-01: checkout — fixed prices, all-or-nothing reserve, idempotency."""

import uuid

from app.b2b_client import ReserveFailure
from app.models import CartItem


def test_checkout_creates_paid_order_with_fixed_prices(
    client, auth_headers, cart_with_item, address, payment_method, db_session
):
    sku = cart_with_item["sku"]
    product = cart_with_item["product"]
    qty = cart_with_item["item"].quantity
    price_at_checkout = sku.price

    response = client.post(
        "/api/v1/orders",
        headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "address_id": address.id,
            "payment_method_id": payment_method.id,
            "comment": "Test comment",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PAID"
    expected_total = qty * price_at_checkout
    assert body["subtotal"] == expected_total
    assert body["delivery_cost"] == 0
    assert body["total"] == expected_total
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["sku_id"] == sku.id
    assert item["unit_price"] == price_at_checkout
    assert item["line_total"] == expected_total
    assert item["product_title"] == product.title
    assert item["sku_name"] == sku.name

    # Price snapshot stays fixed even if seller changes SKU price afterwards.
    sku.price = price_at_checkout + 9999
    db_session.commit()
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models import Order

    order = db_session.scalar(
        select(Order).where(Order.id == body["id"]).options(selectinload(Order.items))
    )
    assert order is not None
    assert order.items[0].unit_price == price_at_checkout
    assert order.items[0].product_title == product.title

    cart = client.get("/api/v1/cart", headers=auth_headers)
    assert cart.json()["items"] == []


def test_partial_reserve_failure_returns_409(
    client, auth_headers, cart_with_item, address, payment_method, b2b_client
):
    sku = cart_with_item["sku"]
    b2b_client.force_reserve_failures = [
        ReserveFailure(sku_id=sku.id, requested=2, reason="PRODUCT_BLOCKED")
    ]
    response = client.post(
        "/api/v1/orders",
        headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"address_id": address.id, "payment_method_id": payment_method.id},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "RESERVE_FAILED"
    assert body["details"][0]["sku_id"] == sku.id
    assert body["details"][0]["reason"] == "PRODUCT_BLOCKED"
    # Cart must remain (all-or-nothing — no order, no clear).
    cart = client.get("/api/v1/cart", headers=auth_headers)
    assert len(cart.json()["items"]) == 1


def test_idempotency_returns_existing_order(
    client, auth_headers, cart_with_item, address, payment_method, db_session, buyer_id
):
    key = str(uuid.uuid4())
    payload = {
        "address_id": address.id,
        "payment_method_id": payment_method.id,
        "comment": None,
        "items_snapshot": None,
    }
    first = client.post(
        "/api/v1/orders",
        headers={**auth_headers, "Idempotency-Key": key},
        json=payload,
    )
    assert first.status_code == 201
    order_id = first.json()["id"]

    db_session.add(
        CartItem(
            user_id=buyer_id,
            sku_id=cart_with_item["sku"].id,
            quantity=1,
            unit_price_at_add=cart_with_item["sku"].price,
        )
    )
    db_session.commit()

    second = client.post(
        "/api/v1/orders",
        headers={**auth_headers, "Idempotency-Key": key},
        json=payload,
    )
    assert second.status_code == 201
    assert second.json()["id"] == order_id


def test_b2b_unavailable_returns_503(
    client, auth_headers, cart_with_item, address, payment_method, b2b_client
):
    b2b_client.unavailable = True
    response = client.post(
        "/api/v1/orders",
        headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"address_id": address.id, "payment_method_id": payment_method.id},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "B2B_UNAVAILABLE"


def test_cart_validation_error_returns_422(
    client, auth_headers, cart_with_item, address, payment_method, db_session
):
    cart_with_item["sku"].active_quantity = 0
    db_session.commit()
    response = client.post(
        "/api/v1/orders",
        headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"address_id": address.id, "payment_method_id": payment_method.id},
    )
    assert response.status_code == 422


def test_order_not_authorized_returns_401(client, address, payment_method):
    response = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"address_id": address.id, "payment_method_id": payment_method.id},
    )
    assert response.status_code == 401
