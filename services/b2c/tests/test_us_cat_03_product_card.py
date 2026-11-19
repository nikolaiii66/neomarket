"""US-CAT-03: buyer product card — full SKUs, no seller-internal field leaks."""

from app.serializers import FORBIDDEN_BUYER_SKU_FIELDS


def test_product_card_returns_full_data_with_skus(client, product_card_data):
    product = product_card_data["base_product"]
    skus = product_card_data["skus"]
    response = client.get(f"/api/v1/products/{product.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == product.id
    assert body["title"] == product.title
    assert body["description"] == product.description
    assert body["images"] == [image.url for image in product.images]
    assert [item["name"] for item in body["skus"]] == [sku.name for sku in skus]
    assert len(body["skus"]) == 2
    for sku_out, sku in zip(body["skus"], skus, strict=False):
        assert sku_out["price"] == sku.price
        assert "available_quantity" in sku_out
        assert "in_stock" in sku_out
    assert "discount" in body


def test_cost_price_absent_in_response(client, product_card_data):
    product = product_card_data["base_product"]
    response = client.get(f"/api/v1/products/{product.id}")
    assert response.status_code == 200
    body = response.json()
    assert "cost_price" not in body["skus"][0]
    assert "reserved_quantity" not in body["skus"][0]
    for sku in body["skus"]:
        assert FORBIDDEN_BUYER_SKU_FIELDS.isdisjoint(sku.keys())
    # Also ensure catalog alias path is safe.
    alt = client.get(f"/api/v1/catalog/products/{product.id}")
    assert alt.status_code == 200
    assert "cost_price" not in alt.json()["skus"][0]


def test_blocked_product_returns_404(client, blocked_product_data):
    product = blocked_product_data["base_product"]
    response = client.get(f"/api/v1/products/{product.id}")
    assert response.status_code == 404


def test_sku_without_stock_is_shown_as_unavailable(client, out_of_stock_sku_product):
    product = out_of_stock_sku_product["base_product"]
    response = client.get(f"/api/v1/products/{product.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == product.id
    oos = next(s for s in body["skus"] if s["name"] == "OOS")
    assert oos["in_stock"] is False
    assert oos["available_quantity"] == 0
    # OOS SKU stays in the list (buyer can still see the variant).
    assert any(s["name"] == "InStock" and s["in_stock"] for s in body["skus"])


def test_deleted_product_returns_404(client, product_card_data, db_session):
    product = product_card_data["base_product"]
    product.deleted = True
    db_session.commit()
    response = client.get(f"/api/v1/products/{product.id}")
    assert response.status_code == 404


def test_discount_from_old_price(client, product_card_data, db_session):
    sku = product_card_data["skus"][0]
    sku.old_price = sku.price + 2000
    db_session.commit()
    response = client.get(f"/api/v1/products/{product_card_data['base_product'].id}")
    assert response.status_code == 200
    body = response.json()
    matched = next(s for s in body["skus"] if s["id"] == sku.id)
    assert matched["discount"] == 2000
    assert matched["old_price"] == sku.old_price
    assert body["discount"] >= 2000
