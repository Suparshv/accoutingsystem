"""Password hashing and JWT encode/decode (SPEC.md §12.2).

bcrypt is used directly — not passlib, which has a known incompatibility
with bcrypt 4.x (SPEC.md §3, §12.2).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import settings

BCRYPT_COST_FACTOR = 12


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_COST_FACTOR)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def encode_token(*, user_id: int, role: str, partner_id: int | None) -> str:
    """Claims exactly per SPEC.md §12.2: sub, role, partner_id, exp."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "partner_id": partner_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Verifies the signature and expiry. Raises jwt.PyJWTError subclasses
    (ExpiredSignatureError, InvalidTokenError, ...) on any failure — callers
    (app.core.deps) translate those into the standard 401 envelope."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
