from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.db import Base, get_db
from app.main import app
from app.models import Category


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
def client(db_session):
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
def seller_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def valid_jwt(seller_id: str) -> str:
    return create_access_token(seller_id)


@pytest.fixture()
def valid_jwt_with_fixed_id():
    fixed = "11111111-1111-1111-1111-111111111111"
    return create_access_token(fixed), fixed


@pytest.fixture()
def category_id(db_session) -> str:
    cat = Category(id=str(uuid.uuid4()), name="Phones")
    db_session.add(cat)
    db_session.commit()
    return cat.id


@pytest.fixture()
def auth_headers(valid_jwt: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {valid_jwt}"}


@pytest.fixture()
def b2c_headers() -> dict[str, str]:
    return {"X-Service-Key": "b2c-service-key"}


@pytest.fixture()
def moderation_headers() -> dict[str, str]:
    return {"X-Service-Key": "moderation-service-key"}
