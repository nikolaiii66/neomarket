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


def test_first_sku_transitions_product_to_on_moderation(client, auth_headers, category_id):
    product = _create_product(client, auth_headers, category_id)
    response = client.post(
        "/api/v1/skus",
        headers=auth_headers,
        json={
            "product_id": product["id"],
            "title": "128GB Black",
            "price": 99900,
            "cost_price": 70000,
            "stock_quantity": 5,
            "images": [{"url": "/s3/sku.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 201
    got = client.get(f"/api/v1/products/{product['id']}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["status"] == "ON_MODERATION"


def test_first_sku_emits_created_event_to_moderation(client, auth_headers, category_id, db_session):
    from app.models import OutboxEvent
    from sqlalchemy import select

    product = _create_product(client, auth_headers, category_id)
    before = len(db_session.scalars(select(OutboxEvent)).all())
    response = client.post(
        "/api/v1/skus",
        headers=auth_headers,
        json={
            "product_id": product["id"],
            "title": "128GB",
            "price": 1000,
            "images": [{"url": "/s3/sku.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 201
    db_session.expire_all()
    events = db_session.scalars(select(OutboxEvent)).all()
    assert len(events) == before + 1
    assert '"event_type": "CREATED"' in events[-1].payload_json


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
    assert response.status_code == 422
