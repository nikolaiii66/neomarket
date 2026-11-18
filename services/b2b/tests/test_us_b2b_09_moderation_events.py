from datetime import datetime, timezone
from uuid import uuid4

from tests.helpers import create_product, create_sku, moderate_product


def test_moderated_event_clears_blocking_data(
    client, auth_headers, category_id, moderation_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"])
    moderate_product(client, moderation_headers, product["id"], "BLOCKED", hard_block=False)
    moderate_product(client, moderation_headers, product["id"], "MODERATED")
    data = client.get(f"/api/v1/products/{product['id']}", headers=auth_headers).json()
    assert data["status"] == "MODERATED"
    assert data["blocking_reason_id"] is None
    assert data["field_reports"] == []


def test_blocked_soft_saves_field_reports(
    client, auth_headers, category_id, moderation_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"])
    moderate_product(client, moderation_headers, product["id"], "BLOCKED", hard_block=False)
    data = client.get(f"/api/v1/products/{product['id']}", headers=auth_headers).json()
    assert data["status"] == "BLOCKED"
    assert len(data["field_reports"]) == 1


def test_blocked_hard_sets_terminal_status(
    client, auth_headers, category_id, moderation_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"])
    moderate_product(client, moderation_headers, product["id"], "BLOCKED", hard_block=True)
    data = client.get(f"/api/v1/products/{product['id']}", headers=auth_headers).json()
    assert data["status"] == "HARD_BLOCKED"


def test_hard_blocked_product_rejects_seller_edits(
    client, auth_headers, category_id, moderation_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"])
    moderate_product(client, moderation_headers, product["id"], "BLOCKED", hard_block=True)
    response = client.post(
        "/api/v1/skus",
        headers=auth_headers,
        json={
            "product_id": product["id"],
            "title": "Another",
            "price": 1,
            "images": [{"url": "/s3/x.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 403


def test_duplicate_event_same_idempotency_key_no_side_effects(
    client, auth_headers, category_id, moderation_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"])
    key = str(uuid4())
    body = {
        "idempotency_key": key,
        "product_id": product["id"],
        "event_type": "MODERATED",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    assert client.post("/api/v1/moderation/events", headers=moderation_headers, json=body).status_code == 200
    assert client.post("/api/v1/moderation/events", headers=moderation_headers, json=body).status_code == 200


def test_missing_service_key_returns_401(client, auth_headers, category_id):
    product = create_product(client, auth_headers, category_id)
    response = client.post(
        "/api/v1/moderation/events",
        json={
            "idempotency_key": str(uuid4()),
            "product_id": product["id"],
            "event_type": "MODERATED",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert response.status_code == 401


def test_blocked_without_reason_returns_flat_400(
    client, auth_headers, category_id, moderation_headers
):
    product = create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"])
    response = client.post(
        "/api/v1/moderation/events",
        headers=moderation_headers,
        json={
            "idempotency_key": str(uuid4()),
            "product_id": product["id"],
            "event_type": "BLOCKED",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "hard_block": False,
        },
    )
    assert response.status_code == 400


def test_b2c_service_key_cannot_apply_moderation(client, auth_headers, category_id, b2c_headers):
    product = create_product(client, auth_headers, category_id)
    response = client.post(
        "/api/v1/moderation/events",
        headers=b2c_headers,
        json={
            "idempotency_key": str(uuid4()),
            "product_id": product["id"],
            "event_type": "MODERATED",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert response.status_code == 403
