"""Auth endpoints — SPEC.md §9 (auth section), §10.2, §11, §12.2."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.core.enums import UserRole
from app.core.errors import AppError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.core.security import encode_token, hash_password, verify_password
from app.core.search import ilike_any, like_pattern
from app.database import get_db
from app.models.partner import Partner
from app.models.user import User
from app.schemas.auth import (
    AuthenticatedUser,
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    SignupRequest,
    SignupResponse,
    UserOut,
)
from app.schemas.common import Page

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS_MESSAGE = "Invalid Login Id or Password"


@router.post("/signup", response_model=SignupResponse, status_code=201)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> User:
    if db.execute(
        select(User).where(User.login_id == body.login_id)
    ).scalar_one_or_none():
        raise AppError(409, "LOGIN_ID_TAKEN", "This login id is already taken.")
    if db.execute(select(User).where(User.email == body.email)).scalar_one_or_none():
        raise AppError(409, "EMAIL_TAKEN", "This email is already registered.")

    # SPEC.md §9 only sends login_id/email/password for self-signup — there is
    # no name field on the wire, so the login_id doubles as the display name
    # until the user edits their profile.
    user = User(
        name=body.login_id,
        login_id=body.login_id,
        email=body.email,
        password_hash=hash_password(body.password),
        role=UserRole.accountant,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.execute(
        select(User).where(User.login_id == body.login_id)
    ).scalar_one_or_none()

    # Identical failure for "no such user", "wrong password" and "deactivated
    # user" — a differing message would let an attacker enumerate accounts
    # (SPEC.md §10.2).
    if (
        user is None
        or not user.is_active
        or not verify_password(body.password, user.password_hash)
    ):
        raise AppError(401, "INVALID_CREDENTIALS", INVALID_CREDENTIALS_MESSAGE)

    token = encode_token(
        user_id=user.id, role=user.role.value, partner_id=user.partner_id
    )
    return LoginResponse(
        access_token=token,
        user=AuthenticatedUser.model_validate(user),
    )


@router.get("/me", response_model=AuthenticatedUser)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> User:
    if body.role == UserRole.contact and body.partner_id is None:
        raise AppError(
            422,
            "CONTACT_REQUIRES_PARTNER",
            "A portal (contact) user must be linked to a partner.",
        )
    if body.partner_id is not None and db.get(Partner, body.partner_id) is None:
        raise AppError(404, "NOT_FOUND", "Partner not found.")
    if db.execute(
        select(User).where(User.login_id == body.login_id)
    ).scalar_one_or_none():
        raise AppError(409, "LOGIN_ID_TAKEN", "This login id is already taken.")
    if db.execute(select(User).where(User.email == body.email)).scalar_one_or_none():
        raise AppError(409, "EMAIL_TAKEN", "This email is already registered.")

    user = User(
        name=body.name,
        login_id=body.login_id,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        partner_id=body.partner_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=Page[UserOut])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
) -> Page[UserOut]:
    stmt = select(User)
    if search:
        stmt = stmt.where(
            ilike_any(like_pattern(search), User.name, User.login_id, User.email)
        )
    # id tiebreaker: created_at alone isn't unique (rows from one bulk
    # transaction share a timestamp), which lets LIMIT/OFFSET pagination
    # duplicate/skip rows across pages — see routers/sales_orders.py.
    stmt = stmt.order_by(User.created_at.desc(), User.id.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return Page(items=rows, total=total, page=page, page_size=page_size)
