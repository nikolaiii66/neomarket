from __future__ import annotations

import uuid
from typing import Any

from app.models import ModerationCard


def moderator_headers(moderator_id: str) -> dict[str, str]:
    return {"X-Moderator-Id": moderator_id}


def service_headers(service_key: str = "dev-service-key") -> dict[str, str]:
    return {"X-Service-Key": service_key}


def make_card(
    db_session,
    *,
    moderator_id: str | None = None,
    status: str | None = None,
    skus: list | None = None,
    json_after: dict[str, Any] | None = None,
) -> ModerationCard:
    card = ModerationCard(
        product_id=str(uuid.uuid4()),
        seller_id=str(uuid.uuid4()),
        status=status or ModerationCard.Status.IN_REVIEW,
        assigned_moderator_id=moderator_id or str(uuid.uuid4()),
        kind=ModerationCard.Kind.CREATE,
    )
    if json_after is not None:
        card.json_after = json_after
    else:
        card.json_after = {"skus": skus if skus is not None else [{"id": str(uuid.uuid4())}]}
    db_session.add(card)
    db_session.commit()
    db_session.refresh(card)
    return card
