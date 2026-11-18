from uuid import uuid4

from sqlalchemy import select

from app.models import OutboxEvent


def _create_product(client, auth_headers, category_id):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers,
        json={
            "title": "Phone",
            "description": "Desc",
            "category_id": category_id,
            "images": [{"url": "/s3/p.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 201
    return response.json()


def _add_sku(client, auth_headers, product_id, title="128GB Black"):
    return client.post(
        "/api/v1/skus",
        headers=auth_headers,
        json={
            "product_id": product_id,
            "title": title,
            "price": 99900,
            "cost_price": 70000,
            "stock_quantity": 5,
            "images": [{"url": "/s3/sku.jpg", "ordering": 0}],
        },
    )


def test_first_sku_transitions_product_to_on_moderation(client, auth_headers, category_id):
    product = _create_product(client, auth_headers, category_id)
    response = _add_sku(client, auth_headers, product["id"])
    assert response.status_code == 201
    got = client.get(f"/api/v1/products/{product['id']}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["status"] == "ON_MODERATION"


def test_first_sku_emits_created_event_to_moderation(client, auth_headers, category_id, db_session):
    product = _create_product(client, auth_headers, category_id)
    before = len(db_session.scalars(select(OutboxEvent)).all())
    response = _add_sku(client, auth_headers, product["id"], title="128GB")
    assert response.status_code == 201
    db_session.expire_all()
    events = db_session.scalars(select(OutboxEvent)).all()
    assert len(events) == before + 1
    payload = events[-1].payload_json
    assert '"event_type": "CREATED"' in payload
    assert f'"product_id": "{product["id"]}"' in payload
    assert "idempotency_key" in payload
    assert "X-Service-Key" in payload


def test_second_sku_no_state_change(client, auth_headers, category_id, db_session):
    product = _create_product(client, auth_headers, category_id)
    first = _add_sku(client, auth_headers, product["id"], title="128GB")
    assert first.status_code == 201
    db_session.expire_all()
    events_after_first = len(db_session.scalars(select(OutboxEvent)).all())

    second = _add_sku(client, auth_headers, product["id"], title="256GB")
    assert second.status_code == 201

    got = client.get(f"/api/v1/products/{product['id']}", headers=auth_headers)
    assert got.json()["status"] == "ON_MODERATION"
    db_session.expire_all()
    assert len(db_session.scalars(select(OutboxEvent)).all()) == events_after_first


def test_add_sku_to_hard_blocked_returns_403(client, auth_headers, category_id, moderation_headers):
    from tests.helpers import create_sku, moderate_product

    product = _create_product(client, auth_headers, category_id)
    create_sku(client, auth_headers, product["id"])
    moderate_product(client, moderation_headers, product["id"], "BLOCKED", hard_block=True)

    response = _add_sku(client, auth_headers, product["id"], title="new")
    assert response.status_code == 403
    assert response.json()["code"] == "hard_blocked"


def test_missing_image_returns_400(client, auth_headers, category_id):
    product = _create_product(client, auth_headers, category_id)
    response = client.post(
        "/api/v1/skus",
        headers=auth_headers,
        json={
            "product_id": product["id"],
            "title": "128GB",
            "price": 1000,
            "images": [],
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "image" in body["message"].lower()
