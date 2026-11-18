from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt

from app.config import settings


def create_access_token(buyer_id: str) -> str:
    payload = {
        "sub": buyer_id,
        "role": "buyer",
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def require_buyer(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Missing bearer token"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        buyer_id = payload.get("sub")
        if not buyer_id:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "Invalid token"},
            )
        return str(buyer_id)
    except JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Invalid token"},
        ) from exc


def optional_buyer(
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    if not authorization:
        return None
    return require_buyer(authorization)
