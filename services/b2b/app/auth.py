from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt

from app.config import settings


def create_access_token(seller_id: str) -> str:
    payload = {
        "sub": seller_id,
        "role": "seller",
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def require_seller(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Missing bearer token"})
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        seller_id = payload.get("sub")
        if not seller_id:
            raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Invalid token"})
        return str(seller_id)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Invalid token"}) from exc


def require_service_key(
    x_service_key: Annotated[str | None, Header(alias="X-Service-Key")] = None,
    allowed: set[str] | None = None,
) -> str:
    if not x_service_key:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Missing X-Service-Key"})
    for name, key in settings.service_keys.items():
        if key == x_service_key:
            if allowed and name not in allowed:
                raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Service not allowed"})
            return name
    raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Invalid X-Service-Key"})


def new_seller_id() -> str:
    return str(uuid4())
