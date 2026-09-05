"""Auth dependencies — get_current_user and require_role (SPEC.md §12.2)."""

from __future__ import annotations

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Extracts and verifies the JWT, then loads the User. Raises 401 on any
    failure: missing header, expired token, tampered signature, unknown or
    deactivated user — all with the same TOKEN_INVALID/TOKEN_EXPIRED codes,
    never a distinguishing detail.
    """
    if credentials is None:
        raise AppError(
            401, "TOKEN_INVALID", "Missing or malformed Authorization header."
        )

    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise AppError(
            401, "TOKEN_EXPIRED", "Your session has expired. Please log in again."
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(401, "TOKEN_INVALID", "Invalid authentication token.") from exc

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(401, "TOKEN_INVALID", "Invalid authentication token.") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "TOKEN_INVALID", "Invalid authentication token.")

    return user


def require_role(*roles: str):
    """Route-level authorisation. Checks the CURRENT (DB) role, not the
    token's role claim, so a role change or deactivation takes effect
    immediately rather than only after the token expires.
    """

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in roles:
            raise AppError(
                403,
                "INSUFFICIENT_ROLE",
                "You do not have permission to perform this action.",
            )
        return current_user

    return dependency
