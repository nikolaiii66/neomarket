from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import seed_blocking_reasons


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
    seed_blocking_reasons(session)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    original_b2b_url = settings.b2b_base_url
    original_service_key = settings.service_key
    original_b2b_key = settings.b2b_service_key
    settings.b2b_base_url = ""
    settings.service_key = "dev-service-key"
    settings.b2b_service_key = "dev-mod-to-b2b-key"
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    settings.b2b_base_url = original_b2b_url
    settings.service_key = original_service_key
    settings.b2b_service_key = original_b2b_key
