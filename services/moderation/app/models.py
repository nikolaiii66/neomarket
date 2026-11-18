from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


SEED_REASONS: list[tuple[str, str, str, bool]] = [
    ("a7b8c9d0-1234-5678-ef01-890123456789", "DESCRIPTION_MISMATCH", "Описание не соответствует товару", False),
    ("b8c9d0e1-2345-6789-f012-901234567890", "IMAGE_MISMATCH", "Изображение не соответствует товару", False),
    ("c9d0e1f2-3456-7890-0123-012345678901", "WRONG_CATEGORY", "Некорректная категория товара", False),
    ("d0e1f2a3-4567-8901-1234-123456789012", "NOT_ENOUGH_INFO", "Недостаточно информации о товаре", False),
    ("e1f2a3b4-5678-9012-2345-234567890123", "OFFENSIVE_CONTENT", "Нецензурные или оскорбительные материалы", False),
    ("f2a3b4c5-6789-0123-3456-345678901234", "DUPLICATE_PRODUCT", "Дублирование существующего товара", False),
    ("a3b4c5d6-7890-1234-4567-456789012345", "INVALID_PRICE", "Некорректная цена", False),
    ("b4c5d6e7-8901-2345-5678-567890123456", "COUNTERFEIT", "Контрафактный товар", True),
    ("c5d6e7f8-9012-3456-6789-678901234567", "FORBIDDEN_GOODS", "Товар запрещён к продаже на территории РФ", True),
    ("d6e7f8a9-0123-4567-7890-789012345678", "COPYRIGHT_VIOLATION", "Товар нарушает авторские права", True),
]


class BlockingReason(Base):
    __tablename__ = "blocking_reasons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hard_block: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    cards: Mapped[list[ModerationCard]] = relationship(back_populates="blocking_reason")


class ModerationCard(Base):
    __tablename__ = "moderation_cards"
    __table_args__ = (UniqueConstraint("product_id", name="uq_moderation_card_product"),)

    class Kind:
        CREATE = "CREATE"
        EDIT = "EDIT"

    class Status:
        PENDING = "PENDING"
        IN_REVIEW = "IN_REVIEW"
        MODERATED = "MODERATED"
        BLOCKED = "BLOCKED"
        HARD_BLOCKED = "HARD_BLOCKED"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    seller_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    category_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default=Kind.CREATE, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=Status.PENDING, nullable=False, index=True)
    queue_priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    assigned_moderator_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    json_before_text: Mapped[str | None] = mapped_column("json_before", Text, nullable=True)
    json_after_text: Mapped[str] = mapped_column("json_after", Text, default="{}", nullable=False)
    field_reports_text: Mapped[str] = mapped_column("field_reports", Text, default="[]", nullable=False)
    blocking_reason_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("blocking_reasons.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    blocking_reason: Mapped[BlockingReason | None] = relationship(back_populates="cards")
    outgoing_events: Mapped[list[OutgoingModerationEvent]] = relationship(
        back_populates="card", cascade="all, delete-orphan"
    )

    @property
    def json_before(self) -> dict | None:
        if self.json_before_text is None:
            return None
        return json.loads(self.json_before_text)

    @json_before.setter
    def json_before(self, value: dict | None) -> None:
        self.json_before_text = None if value is None else json.dumps(value)

    @property
    def json_after(self) -> dict:
        return json.loads(self.json_after_text or "{}")

    @json_after.setter
    def json_after(self, value: dict | None) -> None:
        self.json_after_text = json.dumps(value or {})

    @property
    def field_reports(self) -> list:
        return json.loads(self.field_reports_text or "[]")

    @field_reports.setter
    def field_reports(self, value: list | None) -> None:
        self.field_reports_text = json.dumps(value or [])


class OutgoingModerationEvent(Base):
    __tablename__ = "outgoing_moderation_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid, nullable=False)
    card_id: Mapped[str] = mapped_column(String(36), ForeignKey("moderation_cards.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_text: Mapped[str] = mapped_column("payload", Text, default="{}", nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    card: Mapped[ModerationCard] = relationship(back_populates="outgoing_events")

    @property
    def payload(self) -> dict:
        return json.loads(self.payload_text or "{}")

    @payload.setter
    def payload(self, value: dict | None) -> None:
        self.payload_text = json.dumps(value or {})


class IncomingProductEvent(Base):
    __tablename__ = "incoming_product_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    payload_text: Mapped[str] = mapped_column("payload", Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def payload(self) -> dict:
        return json.loads(self.payload_text or "{}")

    @payload.setter
    def payload(self, value: dict | None) -> None:
        self.payload_text = json.dumps(value or {})


def seed_blocking_reasons(session) -> None:
    from sqlalchemy import select

    existing = {row.code for row in session.scalars(select(BlockingReason)).all()}
    for reason_id, code, title, hard_block in SEED_REASONS:
        if code in existing:
            continue
        session.add(
            BlockingReason(
                id=reason_id,
                code=code,
                title=title,
                description="",
                hard_block=hard_block,
                is_active=True,
            )
        )
    session.commit()
