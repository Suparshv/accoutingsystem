"""Partner (contact) schemas — SPEC.md §7.3, §11."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import PartnerType


class PartnerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    partner_type: PartnerType = PartnerType.customer
    street: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    pincode: str | None = Field(None, max_length=10)


class PartnerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    partner_type: PartnerType | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    pincode: str | None = Field(None, max_length=10)


class PartnerOut(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    partner_type: PartnerType
    street: str | None
    city: str | None
    state: str | None
    country: str | None
    pincode: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
