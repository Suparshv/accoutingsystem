"""Pydantic schemas for payments (SPEC.md §7.8, §9)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import PaymentState, PaymentType
from app.schemas.common import Money


class PaymentCreate(BaseModel):
    """POST body. number, state and journal_entry_id are server-owned (R6)."""

    payment_type: PaymentType
    partner_id: int
    journal_id: int
    amount: Money = Field(gt=0)
    payment_date: date | None = None
    note: str | None = None
    invoice_id: int | None = None
    bill_id: int | None = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    payment_type: PaymentType
    partner_id: int
    partner_name: str | None = None
    journal_id: int
    amount: Money
    payment_date: date
    note: str | None = None
    state: PaymentState
    invoice_id: int | None = None
    bill_id: int | None = None
    journal_entry_id: int | None = None
