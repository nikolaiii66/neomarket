from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("categories.id"), nullable=True)

    filters: Mapped[list[CategoryFilter]] = relationship(back_populates="category", cascade="all, delete-orphan")


class CategoryFilter(Base):
    __tablename__ = "category_filters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    category_id: Mapped[str] = mapped_column(String(36), ForeignKey("categories.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    filter_type: Mapped[str] = mapped_column(String(32), default="list")

    category: Mapped[Category] = relationship(back_populates="filters")
    values: Mapped[list[FilterValue]] = relationship(back_populates="filter", cascade="all, delete-orphan")


class FilterValue(Base):
    __tablename__ = "filter_values"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filter_id: Mapped[str] = mapped_column(String(36), ForeignKey("category_filters.id"), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    filter: Mapped[CategoryFilter] = relationship(back_populates="values")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    category_id: Mapped[str] = mapped_column(String(36), ForeignKey("categories.id"), nullable=False, index=True)
    seller_id: Mapped[str] = mapped_column(String(36), nullable=False, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), default="MODERATED", nullable=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    popularity: Mapped[int] = mapped_column(Integer, default=0)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    category: Mapped[Category] = relationship()
    images: Mapped[list[ProductImage]] = relationship(back_populates="product", cascade="all, delete-orphan")
    characteristics: Mapped[list[ProductCharacteristic]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    skus: Mapped[list[SKU]] = relationship(back_populates="product", cascade="all, delete-orphan")
    filter_links: Mapped[list[ProductFilterValue]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    ordering: Mapped[int] = mapped_column(Integer, default=0)
    alt: Mapped[str] = mapped_column(String(255), default="")
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)

    product: Mapped[Product] = relationship(back_populates="images")


class ProductCharacteristic(Base):
    __tablename__ = "product_characteristics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    product: Mapped[Product] = relationship(back_populates="characteristics")


class ProductFilterValue(Base):
    __tablename__ = "product_filter_values"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    filter_id: Mapped[str] = mapped_column(String(36), ForeignKey("category_filters.id"), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    product: Mapped[Product] = relationship(back_populates="filter_links")


class SKU(Base):
    __tablename__ = "skus"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku_code: Mapped[str] = mapped_column(String(64), default="")
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    old_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_quantity: Mapped[int] = mapped_column(Integer, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    product: Mapped[Product] = relationship(back_populates="skus")
    images: Mapped[list[SKUImage]] = relationship(back_populates="sku", cascade="all, delete-orphan")
    characteristics: Mapped[list[SKUCharacteristic]] = relationship(
        back_populates="sku", cascade="all, delete-orphan"
    )


class SKUImage(Base):
    __tablename__ = "sku_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sku_id: Mapped[str] = mapped_column(String(36), ForeignKey("skus.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    ordering: Mapped[int] = mapped_column(Integer, default=0)
    alt: Mapped[str] = mapped_column(String(255), default="")
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)

    sku: Mapped[SKU] = relationship(back_populates="images")


class SKUCharacteristic(Base):
    __tablename__ = "sku_characteristics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sku_id: Mapped[str] = mapped_column(String(36), ForeignKey("skus.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    sku: Mapped[SKU] = relationship(back_populates="characteristics")


class Buyer(Base):
    __tablename__ = "buyers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), default="Buyer")
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    buyer_id: Mapped[str] = mapped_column(String(36), ForeignKey("buyers.id"), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(100), default="RU")
    region: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(200), nullable=False)
    street: Mapped[str] = mapped_column(String(200), nullable=False)
    building: Mapped[str] = mapped_column(String(50), nullable=False)
    apartment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    buyer_id: Mapped[str] = mapped_column(String(36), ForeignKey("buyers.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), default="CARD")
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    card_brand: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "sku_id", name="uq_cart_user_sku"),
        UniqueConstraint("session_id", "sku_id", name="uq_cart_session_sku"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    sku_id: Mapped[str] = mapped_column(String(36), ForeignKey("skus.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_at_add: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    sku: Mapped[SKU] = relationship()


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    buyer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="PAID", nullable=False)
    number: Mapped[str] = mapped_column(String(64), default="")
    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    delivery_cost: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    address_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("addresses.id"), nullable=True)
    payment_method_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("payment_methods.id"), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    idempotency_request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status_history_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete-orphan")
    address: Mapped[Address | None] = relationship()
    payment_method: Mapped[PaymentMethod | None] = relationship()


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), nullable=False)
    sku_id: Mapped[str] = mapped_column(String(36), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    sku_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    order: Mapped[Order] = relationship(back_populates="items")
