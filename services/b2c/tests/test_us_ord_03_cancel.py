import uuid

from app.auth import create_access_token
from app.models import Order, OrderItem
from app.serializers import append_status_history


def _seed_order(db_session, buyer_id, address, payment_method, sku, product, status="PAID"):
    order = Order(
        id=str(uuid.uuid4()),
        buyer_id=buyer_id,
        status=status,
        address_id=address.id,
        payment_method_id=payment_method.id,
        subtotal=sku.price,
        total=sku.price,
        number="NM-TEST",
    )
    append_status_history(order, status)
    order.items.append(
        OrderItem(
            sku_id=sku.id,
            product_id=product.id,
            name=f"{product.title} — {sku.name}",
            sku_code=sku.sku_code,
            quantity=1,
            unit_price=sku.price,
            line_total=sku.price,
        )
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_cancel_paid_order_transitions_to_cancelled(
    client, auth_headers, db_session, buyer_id, address, payment_method, seeded_catalog
):
    sku = seeded_catalog["skus"][0]
    product = seeded_catalog["products"][0]
    order = _seed_order(db_session, buyer_id, address, payment_method, sku, product, status="PAID")
    sku.reserved_quantity = 1
    sku.active_quantity = max(0, sku.active_quantity - 1)
    db_session.commit()

    response = client.post(f"/api/v1/orders/{order.id}/cancel", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == order.id
    assert body["status"] == "CANCELLED"
    assert body["status_history"][0]["status"] == "PAID"
    assert body["status_history"][-1]["status"] == "CANCELLED"


def test_other_user_order_returns_404(
    client, db_session, buyer_id, address, payment_method, seeded_catalog
):
    sku = seeded_catalog["skus"][0]
    product = seeded_catalog["products"][0]
    order = _seed_order(db_session, buyer_id, address, payment_method, sku, product)
    other = create_access_token(str(uuid.uuid4()))
    response = client.post(
        f"/api/v1/orders/{order.id}/cancel",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["message"] == "Order not found"


def test_cancel_delivered_order_returns_409(
    client, auth_headers, db_session, buyer_id, address, payment_method, seeded_catalog
):
    sku = seeded_catalog["skus"][0]
    product = seeded_catalog["products"][0]
    order = _seed_order(
        db_session, buyer_id, address, payment_method, sku, product, status="DELIVERED"
    )
    response = client.post(f"/api/v1/orders/{order.id}/cancel", headers=auth_headers)
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "CANCEL_NOT_ALLOWED"


def test_cancel_order_not_authorized_returns_401(
    client, db_session, buyer_id, address, payment_method, seeded_catalog
):
    sku = seeded_catalog["skus"][0]
    product = seeded_catalog["products"][0]
    order = _seed_order(db_session, buyer_id, address, payment_method, sku, product)
    response = client.post(f"/api/v1/orders/{order.id}/cancel", headers={})
    assert response.status_code == 401


def test_cancel_with_restore_cart(
    client, auth_headers, db_session, buyer_id, address, payment_method, seeded_catalog
):
    sku = seeded_catalog["skus"][0]
    product = seeded_catalog["products"][0]
    order = _seed_order(db_session, buyer_id, address, payment_method, sku, product)
    sku.reserved_quantity = 1
    db_session.commit()
    response = client.post(
        f"/api/v1/orders/{order.id}/cancel",
        headers=auth_headers,
        json={"restore_cart": True},
    )
    assert response.status_code == 200
    cart = client.get("/api/v1/cart", headers=auth_headers)
    assert len(cart.json()["items"]) == 1
    assert cart.json()["items"][0]["sku_id"] == sku.id
