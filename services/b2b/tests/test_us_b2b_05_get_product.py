from uuid import uuid4

from tests.helpers import create_product, create_sku, moderate_product


def test_get_moderated_product_returns_full_payload(
    client, auth_headers, category_id, moderation_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"])
    moderate_product(client, moderation_headers, product["id"], "MODERATED")
    response = client.get(f"/api/v1/products/{product['id']}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "MODERATED"
    assert data["blocked"] is False
    assert data["blocking_reason"] is None
    assert data["field_reports"] == []
    assert len(data["skus"]) == 1
    assert data["skus"][0]["cost_price"] == 500
    assert "reserved_quantity" in data["skus"][0]
    for field in (
        "id",
        "seller_id",
        "category_id",
        "title",
        "slug",
        "description",
        "status",
        "deleted",
        "images",
        "characteristics",
        "skus",
        "created_at",
        "updated_at",
    ):
        assert field in data


def test_get_blocked_product_returns_blocking_reason_and_field_reports(
    client, auth_headers, category_id, moderation_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"])
    moderate_product(client, moderation_headers, product["id"], "BLOCKED", hard_block=False)
    response = client.get(f"/api/v1/products/{product['id']}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "BLOCKED"
    assert data["blocked"] is True
    assert data["blocking_reason"] is not None
    assert data["blocking_reason"]["title"]
    assert isinstance(data["field_reports"], list)
    assert len(data["field_reports"]) == 1
    assert data["field_reports"][0]["field_name"] == "images"


def test_get_product_supports_all_five_statuses(client, auth_headers, category_id, moderation_headers):
    statuses = []
    p = create_product(client, auth_headers, category_id, title="A")
    statuses.append(client.get(f"/api/v1/products/{p['id']}", headers=auth_headers).json()["status"])
    create_sku(client, auth_headers, p["id"])
    statuses.append(client.get(f"/api/v1/products/{p['id']}", headers=auth_headers).json()["status"])
    moderate_product(client, moderation_headers, p["id"], "MODERATED")
    statuses.append(client.get(f"/api/v1/products/{p['id']}", headers=auth_headers).json()["status"])
    moderate_product(client, moderation_headers, p["id"], "BLOCKED", hard_block=False)
    statuses.append(client.get(f"/api/v1/products/{p['id']}", headers=auth_headers).json()["status"])
    p2 = create_product(client, auth_headers, category_id, title="B")
    create_sku(client, auth_headers, p2["id"])
    moderate_product(client, moderation_headers, p2["id"], "BLOCKED", hard_block=True)
    statuses.append(client.get(f"/api/v1/products/{p2['id']}", headers=auth_headers).json()["status"])
    assert statuses == ["CREATED", "ON_MODERATION", "MODERATED", "BLOCKED", "HARD_BLOCKED"]


def test_get_others_product_returns_404(client, auth_headers, category_id):
    from app.auth import create_access_token

    product = create_product(client, auth_headers, category_id)
    other = {"Authorization": f"Bearer {create_access_token(str(uuid4()))}"}
    response = client.get(f"/api/v1/products/{product['id']}", headers=other)
    assert response.status_code == 404


def test_get_nonexistent_returns_404(client, auth_headers):
    response = client.get(f"/api/v1/products/{uuid4()}", headers=auth_headers)
    assert response.status_code == 404
