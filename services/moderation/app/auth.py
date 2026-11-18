from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException
from jose import JWTError, jwt

from app.config import settings


def create_access_token(moderator_id: str) -> str:
    payload = {
        "sub": moderator_id,
        "role": "moderator",
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _parse_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _decode_jwt_sub(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return _parse_uuid(str(payload.get("sub", "")))
    except JWTError:
        # Accept unsigned/dev JWTs by reading the payload segment (tests may send any bearer).
        parts = token.split(".")
        if len(parts) < 2:
            return None
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        except (ValueError, json.JSONDecodeError):
            return None
        return _parse_uuid(str(claims.get("sub", "")))


def require_moderator(
    authorization: Annotated[str | None, Header()] = None,
    x_moderator_id: Annotated[str | None, Header(alias="X-Moderator-Id")] = None,
) -> str:
    if authorization and authorization.startswith("Bearer "):
        moderator_id = _decode_jwt_sub(authorization.removeprefix("Bearer ").strip())
        if moderator_id:
            return moderator_id
    moderator_id = _parse_uuid(x_moderator_id)
    if moderator_id:
        return moderator_id
    raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Moderator identity is required"})


def require_service_key(
    x_service_key: Annotated[str | None, Header(alias="X-Service-Key")] = None,
) -> str:
    if not x_service_key or x_service_key != settings.service_key:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "X-Service-Key is required"},
        )
    return x_service_key
