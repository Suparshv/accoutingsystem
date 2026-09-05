"""Auth request/response schemas — every rule in SPEC.md §11 auth section."""

from __future__ import annotations

import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    ValidationInfo,
    field_validator,
)

from app.core.enums import UserRole

LOGIN_ID_REGEX = re.compile(r"^[A-Za-z0-9_]{6,12}$")
# Minimum 9 chars (mockup's ">8 characters"), at least one lower, one upper,
# one special character.
PASSWORD_REGEX = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{9,}$")

LOGIN_ID_MESSAGE = (
    "login_id must be 6-12 characters: letters, digits and underscore only"
)
PASSWORD_MESSAGE = (
    "password must be at least 9 characters and include an uppercase letter, "
    "a lowercase letter and a special character"
)


class SignupRequest(BaseModel):
    login_id: str
    email: EmailStr
    password: str
    confirm_password: str

    @field_validator("login_id")
    @classmethod
    def _validate_login_id(cls, v: str) -> str:
        if not LOGIN_ID_REGEX.match(v):
            raise ValueError(LOGIN_ID_MESSAGE)
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if not PASSWORD_REGEX.match(v):
            raise ValueError(PASSWORD_MESSAGE)
        return v

    @field_validator("confirm_password")
    @classmethod
    def _validate_confirm_password(cls, v: str, info: ValidationInfo) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("confirm_password must match password")
        return v


class SignupResponse(BaseModel):
    id: int
    login_id: str
    email: EmailStr
    role: UserRole

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    login_id: str
    password: str


class AuthenticatedUser(BaseModel):
    id: int
    name: str | None = None
    login_id: str
    role: UserRole
    partner_id: int | None

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthenticatedUser


class CreateUserRequest(BaseModel):
    """POST /auth/users (admin only). role is restricted to admin|contact per
    SPEC.md §9 — self-signup is the only path that produces an accountant."""

    name: str = Field(..., min_length=1)
    login_id: str
    email: EmailStr
    role: UserRole
    password: str
    confirm_password: str
    partner_id: int | None = None

    @field_validator("login_id")
    @classmethod
    def _validate_login_id(cls, v: str) -> str:
        if not LOGIN_ID_REGEX.match(v):
            raise ValueError(LOGIN_ID_MESSAGE)
        return v

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: UserRole) -> UserRole:
        if v not in (UserRole.admin, UserRole.contact):
            raise ValueError("role must be 'admin' or 'contact'")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if not PASSWORD_REGEX.match(v):
            raise ValueError(PASSWORD_MESSAGE)
        return v

    @field_validator("confirm_password")
    @classmethod
    def _validate_confirm_password(cls, v: str, info: ValidationInfo) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("confirm_password must match password")
        return v


class UserOut(BaseModel):
    id: int
    name: str
    login_id: str
    email: EmailStr
    role: UserRole
    partner_id: int | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
