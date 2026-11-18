from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.b2b_client import B2BClient, set_b2b_client
from app.db import Base, get_db
from app.main import app
from app.models import (
    Address,
    Buyer,
    CartItem,
    Category,
    CategoryFilter,
    FilterValue,
    PaymentMethod,
    Product,
    ProductFilterValue,
    ProductImage,
    SKU,
    SKUImage,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def b2b_client():
    client = B2BClient()
    set_b2b_client(client)
    yield client
    set_b2b_client(B2BClient())


@pytest.fixture()
def client(db_session, b2b_client):
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def buyer_id(db_session) -> str:
    buyer = Buyer(id=str(uuid.uuid4()), email=f"buyer-{uuid.uuid4().hex[:8]}@example.com", first_name="Test")
    db_session.add(buyer)
    db_session.commit()
    return buyer.id


@pytest.fixture()
def auth_headers(buyer_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(buyer_id)}"}


@pytest.fixture()
def session_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def category(db_session) -> Category:
    cat = Category(id=str(uuid.uuid4()), name="Smartphones", slug="smartphones")
    db_session.add(cat)
    db_session.commit()
    return cat


def _make_product(
    db_session,
    *,
    category_id: str,
    title: str,
    description: str = "",
    status: str = "MODERATED",
    deleted: bool = False,
    stock: int = 10,
    price: int = 10000,
    sku_name: str = "Default",
) -> tuple[Product, SKU]:
    product = Product(
        id=str(uuid.uuid4()),
        category_id=category_id,
        title=title,
        slug=title.lower().replace(" ", "-"),
        description=description or f"Description for {title}",
        status=status,
        deleted=deleted,
        rating=4.5,
        popularity=10,
    )
    product.images.append(
        ProductImage(url=f"https://cdn.example/{product.slug}.jpg", ordering=0, is_main=True)
    )
    sku = SKU(
        id=str(uuid.uuid4()),
        name=sku_name,
        price=price,
        active_quantity=stock,
        sku_code=str(uuid.uuid4()),
    )
    sku.images.append(SKUImage(url=f"https://cdn.example/{product.slug}-sku.jpg", ordering=0, is_main=True))
    product.skus.append(sku)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    db_session.refresh(sku)
    return product, sku


@pytest.fixture()
def seeded_catalog(db_session, category):
    filt = CategoryFilter(
        id=str(uuid.uuid4()),
        category_id=category.id,
        name="Brand",
        slug="brand",
        filter_type="list",
    )
    val_a = FilterValue(id=str(uuid.uuid4()), value="Apple")
    val_b = FilterValue(id=str(uuid.uuid4()), value="Samsung")
    filt.values.extend([val_a, val_b])
    db_session.add(filt)

    p1, s1 = _make_product(
        db_session,
        category_id=category.id,
        title="Product 1",
        description="Description 1 common",
        price=15000,
        stock=5,
        sku_name="128GB",
    )
    p2, s2 = _make_product(
        db_session,
        category_id=category.id,
        title="Product 2",
        description="Description 1 common",
        price=20000,
        stock=8,
        sku_name="256GB",
    )
    db_session.add(ProductFilterValue(product_id=p1.id, filter_id=filt.id, value="Apple"))
    db_session.add(ProductFilterValue(product_id=p2.id, filter_id=filt.id, value="Samsung"))
    db_session.commit()
    return {
        "category": category,
        "filters": (filt,),
        "values": (val_a, val_b),
        "products": (p1, p2),
        "skus": (s1, s2),
    }


@pytest.fixture()
def visibility_catalog(db_session, category):
    visible, _ = _make_product(db_session, category_id=category.id, title="Visible", stock=3)
    hidden_status, _ = _make_product(
        db_session, category_id=category.id, title="Blocked", status="BLOCKED", stock=3
    )
    hidden_stock, _ = _make_product(
        db_session, category_id=category.id, title="NoStock", stock=0
    )
    return {
        "category": category,
        "visible_product": visible,
        "hidden_by_status_product": hidden_status,
        "hidden_by_stock_product": hidden_stock,
    }


@pytest.fixture()
def product_card_data(db_session, category):
    product, sku1 = _make_product(
        db_session, category_id=category.id, title="iPhone 15", stock=5, sku_name="256GB Black"
    )
    sku2 = SKU(
        id=str(uuid.uuid4()),
        product_id=product.id,
        name="256GB White",
        price=12999000,
        active_quantity=2,
    )
    db_session.add(sku2)
    db_session.commit()
    return {"base_product": product, "skus": (sku1, sku2)}


@pytest.fixture()
def blocked_product_data(db_session, category):
    product, sku = _make_product(
        db_session, category_id=category.id, title="Blocked Phone", status="BLOCKED", stock=5
    )
    return {"base_product": product, "skus": (sku,)}


@pytest.fixture()
def out_of_stock_sku_product(db_session, category):
    product, sku = _make_product(
        db_session, category_id=category.id, title="Mixed Stock", stock=0, sku_name="OOS"
    )
    in_stock = SKU(
        id=str(uuid.uuid4()),
        product_id=product.id,
        name="InStock",
        price=1000,
        active_quantity=4,
    )
    db_session.add(in_stock)
    db_session.commit()
    return {"base_product": product, "skus": (sku, in_stock)}


@pytest.fixture()
def address(db_session, buyer_id) -> Address:
    addr = Address(
        id=str(uuid.uuid4()),
        buyer_id=buyer_id,
        country="RU",
        city="Ekaterinburg",
        street="Mira",
        building="19",
        apartment="42",
    )
    db_session.add(addr)
    db_session.commit()
    return addr


@pytest.fixture()
def payment_method(db_session, buyer_id) -> PaymentMethod:
    method = PaymentMethod(
        id=str(uuid.uuid4()),
        buyer_id=buyer_id,
        type="CARD",
        card_last4="4242",
        card_brand="VISA",
        is_default=True,
    )
    db_session.add(method)
    db_session.commit()
    return method


@pytest.fixture()
def cart_with_item(db_session, buyer_id, seeded_catalog):
    sku = seeded_catalog["skus"][0]
    item = CartItem(
        id=str(uuid.uuid4()),
        user_id=buyer_id,
        sku_id=sku.id,
        quantity=2,
        unit_price_at_add=sku.price,
    )
    db_session.add(item)
    db_session.commit()
    return {"item": item, "sku": sku, "product": seeded_catalog["products"][0]}


@pytest.fixture()
def guest_cart_item(db_session, session_id, seeded_catalog):
    sku = seeded_catalog["skus"][0]
    item = CartItem(
        id=str(uuid.uuid4()),
        session_id=session_id,
        sku_id=sku.id,
        quantity=1,
        unit_price_at_add=sku.price,
    )
    db_session.add(item)
    db_session.commit()
    return {"item": item, "sku": sku, "product": seeded_catalog["products"][0], "session_id": session_id}
