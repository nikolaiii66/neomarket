from uuid import uuid4

from sqlalchemy import select

from app.models import OutboxEvent
from tests.helpers import create_product, create_sku, moderate_product


def _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=5):
    product = create_product(client, auth_headers, category_id)
    sku = create_sku(client, auth_headers, product["id"], stock=stock)
    moderate_product(client, moderation_headers, product["id"], "MODERATED")
    return sku


def _sku_state(client, auth_headers, product_id, sku_id):
    product = client.get(f"/api/v1/products/{product_id}", headers=auth_headers).json()
    sku = next(s for s in product["skus"] if s["id"] == sku_id)
    active = sku["stock_quantity"] - sku["reserved_quantity"]
    return sku["stock_quantity"], sku["reserved_quantity"], active


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
    stock, reserved, active = _sku_state(client, auth_headers, sku["product_id"], sku["id"])
    assert stock == 5
    assert reserved == 2
    assert active == 3  # active_quantity decreased


def test_partial_insufficient_stock_returns_409_all_rollback(
    client, auth_headers, category_id, moderation_headers, b2c_headers
):
    sku_ok = _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=5)
    sku_short = _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=1)
    response = client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json={
            "idempotency_key": str(uuid4()),
            "order_id": str(uuid4()),
            "items": [
                {"sku_id": sku_ok["id"], "quantity": 2},
                {"sku_id": sku_short["id"], "quantity": 5},
            ],
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "INSUFFICIENT_STOCK"
    _, reserved_ok, _ = _sku_state(client, auth_headers, sku_ok["product_id"], sku_ok["id"])
    _, reserved_short, _ = _sku_state(
        client, auth_headers, sku_short["product_id"], sku_short["id"]
    )
    assert reserved_ok == 0
    assert reserved_short == 0


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
    _, reserved, active = _sku_state(client, auth_headers, sku["product_id"], sku["id"])
    assert reserved == 2
    assert active == 3


def test_sku_out_of_stock_event_emitted(
    client, auth_headers, category_id, moderation_headers, b2c_headers, db_session
):
    sku = _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=2)
    before = len(db_session.scalars(select(OutboxEvent)).all())
    response = client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json={
            "idempotency_key": str(uuid4()),
            "order_id": str(uuid4()),
            "items": [{"sku_id": sku["id"], "quantity": 2}],
        },
    )
    assert response.status_code == 200
    _, reserved, active = _sku_state(client, auth_headers, sku["product_id"], sku["id"])
    assert reserved == 2
    assert active == 0
    db_session.expire_all()
    events = db_session.scalars(select(OutboxEvent)).all()
    assert len(events) == before + 1
    payload = events[-1].payload_json
    assert '"event_type": "SKU_OUT_OF_STOCK"' in payload
    assert f'"sku_id": "{sku["id"]}"' in payload


def test_unreserve_restores_quantities(
    client, auth_headers, category_id, moderation_headers, b2c_headers
):
    sku = _moderated_sku(client, auth_headers, category_id, moderation_headers, stock=5)
    order_id = str(uuid4())
    assert (
        client.post(
            "/api/v1/inventory/reserve",
            headers=b2c_headers,
            json={
                "idempotency_key": str(uuid4()),
                "order_id": order_id,
                "items": [{"sku_id": sku["id"], "quantity": 2}],
            },
        ).status_code
        == 200
    )
    response = client.post(
        "/api/v1/inventory/unreserve",
        headers=b2c_headers,
        json={"order_id": order_id, "items": [{"sku_id": sku["id"], "quantity": 2}]},
    )
    assert response.status_code == 200
    _, reserved, active = _sku_state(client, auth_headers, sku["product_id"], sku["id"])
    assert reserved == 0
    assert active == 5


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
