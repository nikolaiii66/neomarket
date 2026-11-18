from __future__ import annotations

import uuid

from sqlalchemy import select

from app.config import settings
from app.models import BlockingReason, IncomingProductEvent, ModerationCard, OutgoingModerationEvent
from tests.helpers import make_card, moderator_headers, service_headers


def _reason(db_session, code: str) -> BlockingReason:
    return db_session.scalar(select(BlockingReason).where(BlockingReason.code == code))


def test_hard_block_transitions_to_terminal_and_emits_event(client, db_session, monkeypatch) -> None:
    moderator_id = str(uuid.uuid4())
    card = make_card(db_session, moderator_id=moderator_id)
    reason = _reason(db_session, "COUNTERFEIT")
    sent: dict = {}
    settings.b2b_base_url = "https://b2b.example.test"

    class Response:
        status_code = 200

    def fake_post(url, json=None, headers=None, timeout=None, **_kwargs):
        sent["url"] = url
        sent["json"] = json
        sent["headers"] = headers
        return Response()

    monkeypatch.setattr("app.services.httpx.post", fake_post)

    response = client.post(
        f"/api/v1/products/{card.product_id}/decline",
        json={
            "blocking_reason_id": reason.id,
            "moderator_comment": "counterfeit",
            "field_reports": [],
        },
        headers=moderator_headers(moderator_id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "HARD_BLOCKED"
    db_session.refresh(card)
    assert card.status == ModerationCard.Status.HARD_BLOCKED
    assert card.blocking_reason_id == reason.id
    assert card.decision_comment == "counterfeit"
    assert sent["url"] == "https://b2b.example.test/api/v1/moderation/events"
    assert sent["headers"]["X-Service-Key"] == settings.b2b_service_key
    assert sent["json"]["event_type"] == "BLOCKED"
    assert sent["json"]["blocking_reason_id"] == reason.id
    assert sent["json"]["moderator_id"] == moderator_id
    assert sent["json"]["moderator_comment"] == "counterfeit"
    assert sent["json"]["field_reports"] == []
    assert "idempotency_key" in sent["json"]
    assert "occurred_at" in sent["json"]
    event = db_session.scalar(
        select(OutgoingModerationEvent).where(
            OutgoingModerationEvent.card_id == card.id,
            OutgoingModerationEvent.event_type == "BLOCKED",
            OutgoingModerationEvent.delivered.is_(True),
        )
    )
    assert event is not None


def test_hard_block_event_carries_hard_block_true(client, db_session) -> None:
    moderator_id = str(uuid.uuid4())
    card = make_card(db_session, moderator_id=moderator_id)
    reason = _reason(db_session, "FORBIDDEN_GOODS")

    response = client.post(
        f"/api/v1/tickets/{card.id}/block",
        json={"blocking_reason_ids": [reason.id], "comment": "forbidden", "field_reports": []},
        headers=moderator_headers(moderator_id),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == card.id
    assert payload["status"] == "HARD_BLOCKED"
    event = db_session.scalar(
        select(OutgoingModerationEvent).where(
            OutgoingModerationEvent.card_id == card.id,
            OutgoingModerationEvent.event_type == "BLOCKED",
        )
    )
    assert event is not None
    assert event.payload["hard_block"] is True
    assert event.payload["event_type"] == "BLOCKED"
    assert event.payload["blocking_reason_id"] == reason.id
    assert "occurred_at" in event.payload


def test_any_modify_on_hard_blocked_returns_403(client, db_session) -> None:
    moderator_id = str(uuid.uuid4())
    card = make_card(db_session, moderator_id=moderator_id)
    card.status = ModerationCard.Status.HARD_BLOCKED
    db_session.commit()
    reason = _reason(db_session, "COPYRIGHT_VIOLATION")

    approve = client.post(
        f"/api/v1/products/{card.product_id}/approve",
        json={},
        headers=moderator_headers(moderator_id),
    )
    decline = client.post(
        f"/api/v1/products/{card.product_id}/decline",
        json={"blocking_reason_id": reason.id, "field_reports": []},
        headers=moderator_headers(moderator_id),
    )

    assert approve.status_code == 403
    assert decline.status_code == 403
    assert approve.json()["code"] == "HARD_BLOCKED"
    assert decline.json()["code"] == "HARD_BLOCKED"


def test_edited_event_on_hard_blocked_is_ignored(client, db_session) -> None:
    card = make_card(
        db_session,
        status=ModerationCard.Status.HARD_BLOCKED,
        json_after={"title": "old", "skus": [{"id": str(uuid.uuid4())}]},
    )

    response = client.post(
        "/api/v1/events/product",
        json={
            "idempotency_key": "edited-on-hard-blocked",
            "event": "EDITED",
            "product_id": card.product_id,
            "json_after": {"title": "new"},
        },
        headers=service_headers(settings.service_key),
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored_hard_blocked"
    db_session.refresh(card)
    assert card.status == ModerationCard.Status.HARD_BLOCKED
    assert card.json_after["title"] == "old"
    incoming = db_session.scalar(
        select(IncomingProductEvent).where(IncomingProductEvent.idempotency_key == "edited-on-hard-blocked")
    )
    assert incoming is not None


def test_deleted_event_removes_hard_blocked(client, db_session) -> None:
    card = make_card(db_session, status=ModerationCard.Status.HARD_BLOCKED)
    card_id = card.id

    response = client.post(
        "/api/v1/events/product",
        json={
            "idempotency_key": "delete-hard-blocked",
            "event": "DELETED",
            "product_id": card.product_id,
        },
        headers=service_headers(settings.service_key),
    )

    assert response.status_code == 202
    assert response.json()["status"] == "archived"
    assert db_session.get(ModerationCard, card_id) is None


def test_soft_reason_routes_to_blocked_not_hard_blocked(client, db_session) -> None:
    moderator_id = str(uuid.uuid4())
    card = make_card(db_session, moderator_id=moderator_id)
    reason = _reason(db_session, "DESCRIPTION_MISMATCH")

    response = client.post(
        f"/api/v1/products/{card.product_id}/decline",
        json={
            "blocking_reason_id": reason.id,
            "field_reports": [{"field_path": "description", "message": "too short"}],
        },
        headers=moderator_headers(moderator_id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    db_session.refresh(card)
    assert card.field_reports == [{"field_path": "description", "message": "too short", "severity": "ERROR"}]
    event = db_session.scalar(
        select(OutgoingModerationEvent).where(
            OutgoingModerationEvent.card_id == card.id,
            OutgoingModerationEvent.event_type == "BLOCKED",
        )
    )
    assert event is not None
    assert event.payload["field_reports"] == [{"field_name": "description", "comment": "too short"}]


def test_blocked_event_matches_b2b_openapi_request(client, db_session, monkeypatch) -> None:
    moderator_id = str(uuid.uuid4())
    card = make_card(db_session, moderator_id=moderator_id)
    reason = _reason(db_session, "COUNTERFEIT")
    sent: dict = {}
    settings.b2b_base_url = "https://b2b.example.test"

    class Response:
        status_code = 200

    def fake_post(url, json=None, headers=None, timeout=None, **_kwargs):
        sent["url"] = url
        sent["json"] = json
        return Response()

    monkeypatch.setattr("app.services.httpx.post", fake_post)

    response = client.post(
        f"/api/v1/products/{card.product_id}/decline",
        json={
            "blocking_reason_id": reason.id,
            "moderator_comment": "counterfeit",
            "field_reports": [{"field_path": "images[0]", "message": "bad image"}],
        },
        headers=moderator_headers(moderator_id),
    )

    assert response.status_code == 200
    assert sent["url"].endswith("/api/v1/moderation/events")
    assert {
        "idempotency_key",
        "product_id",
        "event_type",
        "occurred_at",
        "moderator_id",
        "moderator_comment",
        "blocking_reason_id",
        "hard_block",
        "field_reports",
    } <= set(sent["json"])
    assert sent["json"]["event_type"] == "BLOCKED"
    assert sent["json"]["blocking_reason_id"] == reason.id
    assert "blocking_reason" not in sent["json"]
    assert "status" not in sent["json"]
    assert sent["json"]["field_reports"] == [{"field_name": "images[0]", "comment": "bad image"}]


def test_b2b_event_path_accepts_product_edited_for_hard_blocked(client, db_session) -> None:
    card = make_card(
        db_session,
        status=ModerationCard.Status.HARD_BLOCKED,
        json_after={"title": "old", "skus": [{"id": str(uuid.uuid4())}]},
    )

    response = client.post(
        "/api/v1/b2b/events",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "event_type": "PRODUCT_EDITED",
            "occurred_at": "2026-06-09T00:00:00Z",
            "payload": {
                "product_id": card.product_id,
                "seller_id": card.seller_id,
                "json_before": {"title": "old"},
                "json_after": {"title": "new"},
            },
        },
        headers=service_headers(settings.service_key),
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored_hard_blocked"
    db_session.refresh(card)
    assert card.status == ModerationCard.Status.HARD_BLOCKED
    assert card.json_after["title"] == "old"
    incoming = db_session.scalar(
        select(IncomingProductEvent).where(
            IncomingProductEvent.product_id == card.product_id,
            IncomingProductEvent.event_type == "EDITED",
        )
    )
    assert incoming is not None


def test_b2b_event_path_accepts_product_deleted_for_hard_blocked(client, db_session) -> None:
    card = make_card(db_session, status=ModerationCard.Status.HARD_BLOCKED)
    card_id = card.id

    response = client.post(
        "/api/v1/b2b/events",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "event_type": "PRODUCT_DELETED",
            "occurred_at": "2026-06-09T00:00:00Z",
            "payload": {"product_id": card.product_id},
        },
        headers=service_headers(settings.service_key),
    )

    assert response.status_code == 202
    assert response.json()["status"] == "archived"
    assert db_session.get(ModerationCard, card_id) is None
