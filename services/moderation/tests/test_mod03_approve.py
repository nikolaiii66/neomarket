from __future__ import annotations

import uuid

from sqlalchemy import select

from app.config import settings
from app.models import ModerationCard, OutgoingModerationEvent
from tests.helpers import make_card, moderator_headers


def test_approve_transitions_to_moderated_and_emits_event(client, db_session, monkeypatch) -> None:
    moderator_id = str(uuid.uuid4())
    card = make_card(db_session, moderator_id=moderator_id)
    sent: dict = {}
    settings.b2b_base_url = "https://b2b.example.test"

    class Response:
        status_code = 200

    def fake_post(url, json=None, headers=None, timeout=None, **_kwargs):
        sent["url"] = url
        sent["json"] = json
        sent["headers"] = headers
        sent["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.services.httpx.post", fake_post)

    response = client.post(
        f"/api/v1/products/{card.product_id}/approve",
        json={"moderator_comment": "ok"},
        headers=moderator_headers(moderator_id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "MODERATED"
    db_session.refresh(card)
    assert card.status == ModerationCard.Status.MODERATED
    assert card.decision_comment == "ok"
    assert sent["url"] == "https://b2b.example.test/api/v1/moderation/events"
    assert sent["headers"]["X-Service-Key"] == settings.b2b_service_key
    assert sent["json"]["product_id"] == card.product_id
    assert sent["json"]["event_type"] == "MODERATED"
    assert sent["json"]["moderator_id"] == moderator_id
    assert sent["json"]["moderator_comment"] == "ok"
    assert "idempotency_key" in sent["json"]
    assert "occurred_at" in sent["json"]
    event = db_session.scalar(
        select(OutgoingModerationEvent).where(
            OutgoingModerationEvent.card_id == card.id,
            OutgoingModerationEvent.event_type == "MODERATED",
            OutgoingModerationEvent.delivered.is_(True),
        )
    )
    assert event is not None


def test_protocol_approve_returns_ticket_response_shape(client, db_session) -> None:
    moderator_id = str(uuid.uuid4())
    card = make_card(db_session, moderator_id=moderator_id)

    response = client.post(
        f"/api/v1/tickets/{card.id}/approve",
        json={},
        headers=moderator_headers(moderator_id),
    )

    assert response.status_code == 200
    payload = response.json()
    assert {"id", "product_id", "seller_id", "kind", "status", "queue_priority", "created_at"} <= set(payload)
    assert payload["id"] == card.id
    assert payload["status"] == "APPROVED"


def test_approve_others_card_returns_403(client, db_session) -> None:
    card = make_card(db_session, moderator_id=str(uuid.uuid4()))

    response = client.post(
        f"/api/v1/products/{card.product_id}/approve",
        json={},
        headers=moderator_headers(str(uuid.uuid4())),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "NOT_ASSIGNED"


def test_approve_after_edited_returns_409(client, db_session) -> None:
    moderator_id = str(uuid.uuid4())
    card = make_card(db_session, status=ModerationCard.Status.PENDING, moderator_id=moderator_id)

    response = client.post(
        f"/api/v1/products/{card.product_id}/approve",
        json={},
        headers=moderator_headers(moderator_id),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATUS"


def test_approve_without_sku_returns_409(client, db_session) -> None:
    moderator_id = str(uuid.uuid4())
    card = make_card(db_session, moderator_id=moderator_id, skus=[])

    response = client.post(
        f"/api/v1/products/{card.product_id}/approve",
        json={},
        headers=moderator_headers(moderator_id),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "NO_SKUS"


def test_missing_moderator_identity_returns_401(client, db_session) -> None:
    card = make_card(db_session)

    response = client.post(
        f"/api/v1/products/{card.product_id}/approve",
        json={},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
