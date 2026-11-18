import uuid

from app.models import CartItem


def test_get_cart_enriched_with_b2b_data_user(client, auth_headers, cart_with_item):
    response = client.get("/api/v1/cart", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["quantity"] == cart_with_item["item"].quantity
    assert item["product_id"] == cart_with_item["product"].id
    assert item["name"] == f"{cart_with_item['product'].title} — {cart_with_item['sku'].name}"
    assert item["sku_code"] == cart_with_item["sku"].sku_code
    assert item["unit_price"] == cart_with_item["sku"].price
    assert item["unit_price_at_add"] == cart_with_item["item"].unit_price_at_add
    assert item["line_total"] == cart_with_item["sku"].price * cart_with_item["item"].quantity
    assert item["available_quantity"] == cart_with_item["sku"].active_quantity
    assert item["image"]["url"] == cart_with_item["sku"].images[0].url


def test_get_cart_enriched_with_b2b_data_session(client, guest_cart_item):
    response = client.get(
        "/api/v1/cart",
        headers={"X-Session-Id": guest_cart_item["session_id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["product_id"] == guest_cart_item["product"].id


def test_success_cart_validation(client, auth_headers, cart_with_item):
    response = client.post("/api/v1/cart/validate", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"]
    assert body["issues"] == []


def test_validate_reports_price_changed(client, auth_headers, cart_with_item, db_session):
    sku = cart_with_item["sku"]
    old = cart_with_item["item"].unit_price_at_add
    sku.price = old + 500
    db_session.commit()
    response = client.post("/api/v1/cart/validate", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert not body["is_valid"]
    assert body["issues"][0]["type"] == "PRICE_CHANGED"
    assert body["issues"][0]["old_value"] == old
    assert body["issues"][0]["new_value"] == sku.price


def test_unavailable_sku_shown_with_reason(client, auth_headers, cart_with_item, db_session):
    sku = cart_with_item["sku"]
    sku.active_quantity = 0
    db_session.commit()
    response = client.post("/api/v1/cart/validate", headers=auth_headers)
    assert response.status_code == 200
    assert not response.json()["is_valid"]
    assert response.json()["issues"][0]["type"] == "OUT_OF_STOCK"


def test_add_sku_increments_quantity_if_already_in_cart(client, auth_headers, cart_with_item):
    sku = cart_with_item["sku"]
    before = int(cart_with_item["item"].quantity)
    response = client.post(
        "/api/v1/cart/items",
        json={"sku_id": sku.id, "quantity": 1},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == before + 1


def test_clear_cart_returns_204(client, auth_headers, cart_with_item):
    response = client.delete("/api/v1/cart", headers=auth_headers)
    assert response.status_code == 204
    response = client.get("/api/v1/cart", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_delete_cart_item_returns_updated_cart(client, auth_headers, cart_with_item):
    sku = cart_with_item["sku"]
    response = client.delete(f"/api/v1/cart/items/{sku.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_update_cart_item_quantity_returns_updated_cart(client, auth_headers, cart_with_item):
    sku = cart_with_item["sku"]
    new_quantity = sku.active_quantity - 1
    response = client.patch(
        f"/api/v1/cart/items/{sku.id}",
        json={"quantity": new_quantity},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == new_quantity


def test_merge_without_auth_returns_401(client, guest_cart_item):
    response = client.post(
        "/api/v1/cart/merge",
        headers={"X-Session-Id": guest_cart_item["session_id"]},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_guest_cart_merged_on_login(
    client, auth_headers, buyer_id, db_session, seeded_catalog, session_id
):
    sku = seeded_catalog["skus"][0]
    db_session.add(
        CartItem(user_id=buyer_id, sku_id=sku.id, quantity=1, unit_price_at_add=sku.price)
    )
    db_session.add(
        CartItem(session_id=session_id, sku_id=sku.id, quantity=2, unit_price_at_add=sku.price)
    )
    db_session.commit()
    headers = {**auth_headers, "X-Session-Id": session_id}
    response = client.post("/api/v1/cart/merge", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 2
    assert body["items"][0]["sku_id"] == sku.id


def test_missing_identity_returns_400(client):
    response = client.get("/api/v1/cart")
    assert response.status_code == 400
    assert response.json()["code"] == "MISSING_CART_IDENTITY"
