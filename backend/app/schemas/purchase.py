"""Pydantic schemas for the purchase cycle (SPEC.md §7.6, §9)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import DocumentState, PaymentStatus
from app.schemas.common import Money


class PurchaseOrderLineIn(BaseModel):
    """One submitted PO line.

    line_total is deliberately absent: the server computes it from quantity x
    unit_price and discards anything the client sent (R6, §10.5).
    """

    product_id: int
    analytic_account_id: int | None = None
    quantity: Money = Field(gt=0)
    unit_price: Money = Field(ge=0)


class PurchaseOrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    analytic_account_id: int | None = None
    quantity: Money
    unit_price: Money
    line_total: Money
    sequence: int


class PurchaseOrderCreate(BaseModel):
    """POST body. number, state and total_amount are server-owned (R6)."""

    vendor_id: int
    order_date: date | None = None
    lines: list[PurchaseOrderLineIn] = []


class PurchaseOrderUpdate(BaseModel):
    vendor_id: int | None = None
    order_date: date | None = None
    lines: list[PurchaseOrderLineIn] | None = None


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    vendor_id: int
    vendor_name: str | None = None
    order_date: date
    state: DocumentState
    total_amount: Money
    lines: list[PurchaseOrderLineOut] = []


class PurchaseOrderRow(BaseModel):
    """List view row."""

    id: int
    number: str
    vendor_id: int
    vendor_name: str | None = None
    order_date: date
    state: DocumentState
    total_amount: Money


class VendorBillLineIn(BaseModel):
    product_id: int
    account_id: int
    analytic_account_id: int | None = None
    quantity: Money = Field(gt=0)
    unit_price: Money = Field(ge=0)


class VendorBillLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    account_id: int
    analytic_account_id: int | None = None
    quantity: Money
    unit_price: Money
    line_total: Money
    sequence: int


class VendorBillCreate(BaseModel):
    vendor_id: int
    bill_reference: str | None = Field(default=None, max_length=60)
    bill_date: date | None = None
    due_date: date | None = None
    lines: list[VendorBillLineIn] = []

    @model_validator(mode="after")
    def check_dates(self) -> VendorBillCreate:
        """Mirrors ck_bills_due_after_bill so the client gets a clean 422."""
        if self.due_date and self.bill_date and self.due_date < self.bill_date:
            raise ValueError("due_date must be on or after bill_date")
        return self


class VendorBillUpdate(BaseModel):
    vendor_id: int | None = None
    bill_reference: str | None = Field(default=None, max_length=60)
    bill_date: date | None = None
    due_date: date | None = None
    lines: list[VendorBillLineIn] | None = None


class VendorBillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    vendor_id: int
    vendor_name: str | None = None
    bill_reference: str | None = None
    bill_date: date
    due_date: date | None = None
    state: DocumentState
    total_amount: Money
    # Non-null only on bills created from a PO; the mockup shows the PO button
    # exactly when this is set.
    source_po_id: int | None = None
    journal_entry_id: int | None = None
    # Derived on read from confirmed payments, never stored (R5).
    amount_paid: Money
    amount_due: Money
    payment_status: PaymentStatus
    lines: list[VendorBillLineOut] = []


class VendorBillRow(BaseModel):
    id: int
    number: str
    vendor_id: int
    vendor_name: str | None = None
    bill_date: date
    due_date: date | None = None
    state: DocumentState
    total_amount: Money
    amount_due: Money
    payment_status: PaymentStatus


class Warning_(BaseModel):
    """A non-blocking advisory that rides along with a SUCCESS response (§12.1)."""

    code: str
    message: str
    details: dict | None = None


class VendorBillConfirmOut(BaseModel):
    """§9: confirming returns the bill plus its new journal entry."""

    bill: VendorBillOut
    journal_entry_id: int
    journal_entry_number: str
    # EXCEEDS_BUDGET rides here. It never blocks the post (§10.8).
    warnings: list[Warning_] = []
