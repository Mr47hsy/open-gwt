"""Bearer tokens (JWT, HS256). A token identifies a player, never a match."""

from __future__ import annotations

import time
import uuid

import jwt

from opengwt.server.errors import AppError

ALGORITHM = "HS256"


def new_id() -> str:
    return uuid.uuid4().hex


def create_token(player_id: str, secret: str, ttl_seconds: int) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": player_id, "iat": now, "exp": now + ttl_seconds}, secret, algorithm=ALGORITHM
    )


def player_id_from_token(token: str, secret: str) -> str:
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as e:
        raise AppError("unauthorised", 401) from e
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AppError("unauthorised", 401)
    return subject


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()
