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
    assert not oos["in_stock"]
    assert oos["available_quantity"] == 0
