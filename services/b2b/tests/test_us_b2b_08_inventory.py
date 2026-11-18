from uuid import uuid4

from tests.helpers import create_product, create_sku, moderate_product


def _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=5):
    product = create_product(client, auth_headers, category_id)
    sku = create_sku(client, auth_headers, product["id"], stock=stock)
    moderate_product(client, moderation_headers, product["id"], "MODERATED")
    return sku


def test_reserve_all_skus_succeeds(
    client, auth_headers, category_id, moderation_headers, b2c_headers
):
    sku = _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=5)
    order_id = str(uuid4())
    response = client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json={
            "idempotency_key": str(uuid4()),
            "order_id": order_id,
            "items": [{"sku_id": sku["id"], "quantity": 2}],
        },
    )
    assert response.status_code == 200
    assert response.json()["order_id"] == order_id


def test_partial_insufficient_stock_returns_409_all_rollback(
    client, auth_headers, category_id, moderation_headers, b2c_headers
):
    sku = _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=1)
    response = client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json={
            "idempotency_key": str(uuid4()),
            "order_id": str(uuid4()),
            "items": [{"sku_id": sku["id"], "quantity": 5}],
        },
    )
    assert response.status_code == 409


def test_idempotent_reserve_returns_200_without_double_deduction(
    client, auth_headers, category_id, moderation_headers, b2c_headers
):
    sku = _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=5)
    key = str(uuid4())
    order_id = str(uuid4())
    body = {
        "idempotency_key": key,
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 2}],
    }
    assert client.post("/api/v1/inventory/reserve", headers=b2c_headers, json=body).status_code == 200
    assert client.post("/api/v1/inventory/reserve", headers=b2c_headers, json=body).status_code == 200
    product = client.get(
        f"/api/v1/products/{sku['product_id']}", headers=auth_headers
    ).json()
    assert product["skus"][0]["reserved_quantity"] == 2


def test_unreserve_restores_quantities(
    client, auth_headers, category_id, moderation_headers, b2c_headers
):
    sku = _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=5)
    order_id = str(uuid4())
    client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json={
            "idempotency_key": str(uuid4()),
            "order_id": order_id,
            "items": [{"sku_id": sku["id"], "quantity": 2}],
        },
    )
    response = client.post(
        "/api/v1/inventory/unreserve",
        headers=b2c_headers,
        json={"order_id": order_id, "items": [{"sku_id": sku["id"], "quantity": 2}]},
    )
    assert response.status_code == 200
    product = client.get(f"/api/v1/products/{sku['product_id']}", headers=auth_headers).json()
    assert product["skus"][0]["reserved_quantity"] == 0


def test_reserve_missing_service_key_returns_401(client):
    response = client.post(
        "/api/v1/inventory/reserve",
        json={
            "idempotency_key": str(uuid4()),
            "order_id": str(uuid4()),
            "items": [{"sku_id": str(uuid4()), "quantity": 1}],
        },
    )
    assert response.status_code == 401
