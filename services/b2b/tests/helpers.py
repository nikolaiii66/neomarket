from datetime import datetime, timezone
from uuid import uuid4


def create_product(client, auth_headers, category_id, title="Phone"):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers,
        json={
            "title": title,
            "description": "Desc",
            "category_id": category_id,
            "images": [{"url": "/s3/p.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 201
    return response.json()


def create_sku(client, auth_headers, product_id, stock=10, price=1000):
    response = client.post(
        "/api/v1/skus",
        headers=auth_headers,
        json={
            "product_id": product_id,
            "title": "SKU",
            "price": price,
            "cost_price": 500,
            "stock_quantity": stock,
            "images": [{"url": "/s3/sku.jpg", "ordering": 0}],
        },
    )
    assert response.status_code == 201
    return response.json()


def moderate_product(client, moderation_headers, product_id, event_type="MODERATED", hard_block=False):
    reason = str(uuid4())
    body = {
        "idempotency_key": str(uuid4()),
        "product_id": product_id,
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "hard_block": hard_block,
        "moderator_comment": "ok" if event_type == "MODERATED" else "Blurry product photos",
    }
    if event_type == "BLOCKED":
        body["blocking_reason_id"] = reason
        body["field_reports"] = [
            {"field_name": "images", "message": "Blurry", "reason_id": reason},
        ]
    response = client.post("/api/v1/moderation/events", headers=moderation_headers, json=body)
    assert response.status_code == 200
    return response.json()
