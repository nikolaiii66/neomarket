from tests.helpers import create_product, create_sku, moderate_product


def test_catalog_returns_moderated_in_stock_products(
    client, auth_headers, category_id, moderation_headers, b2c_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"], stock=3)
    moderate_product(client, moderation_headers, product["id"], "MODERATED")
    response = client.get("/api/v1/public/products", headers=b2c_headers)
    assert response.status_code == 200
    ids = [p["id"] for p in response.json()]
    assert product["id"] in ids


def test_catalog_excludes_hard_blocked(
    client, auth_headers, category_id, moderation_headers, b2c_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"], stock=3)
    moderate_product(client, moderation_headers, product["id"], "BLOCKED", hard_block=True)
    response = client.get("/api/v1/public/products", headers=b2c_headers)
    assert product["id"] not in [p["id"] for p in response.json()]


def test_catalog_missing_service_key_returns_401(client):
    response = client.get("/api/v1/public/products")
    assert response.status_code == 401


def test_catalog_response_has_no_cost_price(
    client, auth_headers, category_id, moderation_headers, b2c_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"], stock=3)
    moderate_product(client, moderation_headers, product["id"], "MODERATED")
    response = client.get(f"/api/v1/public/products/{product['id']}", headers=b2c_headers)
    assert response.status_code == 200
    data = response.json()
    assert "cost_price" not in data["skus"][0]
