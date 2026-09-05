"""Pydantic schemas for the sales cycle (SPEC.md §7.7, §9, §11)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import DocumentState, PaymentStatus
from app.schemas.common import Money


class SalesOrderLineCreate(BaseModel):
    """One line as submitted. line_total is never accepted from the client —
    it is always recomputed server-side from quantity * unit_price (R6)."""

    product_id: int
    analytic_account_id: int | None = None
    quantity: Money = Field(gt=0)
    unit_price: Money = Field(ge=0)


class SalesOrderCreate(BaseModel):
    customer_id: int
    order_date: date | None = None
    lines: list[SalesOrderLineCreate]


class SalesOrderUpdate(BaseModel):
    """PUT body. Draft-only (enforced in the router) — omitted fields are
    left unchanged; `lines`, when given, replaces the whole line set."""

    customer_id: int | None = None
    order_date: date | None = None
    lines: list[SalesOrderLineCreate] | None = None


class SalesOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str | None = None
    analytic_account_id: int | None = None
    analytic_account_name: str | None = None
    quantity: Money
    unit_price: Money
    line_total: Money
    sequence: int


class SalesOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    customer_id: int
    customer_name: str | None = None
    order_date: date
    state: DocumentState
    total_amount: Money
    # Non-null once this order has been converted to a customer invoice
    # (mirrors VendorBillOut.source_po_id's role in reverse — §10.5's
    # create-bill behaviour). Not on the ORM object: populated by the router
    # from a CustomerInvoice lookup, never from model_validate directly.
    # Powers the "Create Invoice" -> "View Invoice" swap on the SO detail page.
    invoice_id: int | None = None
    lines: list[SalesOrderLineRead] = []


class SalesOrderListRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    customer_name: str | None = None
    order_date: date
    total_amount: Money
    state: DocumentState


class CustomerInvoiceLineCreate(BaseModel):
    """bill/invoice lines additionally require account_id (§11)."""

    product_id: int
    account_id: int
    analytic_account_id: int | None = None
    quantity: Money = Field(gt=0)
    unit_price: Money = Field(ge=0)


class CustomerInvoiceCreate(BaseModel):
    customer_id: int
    invoice_reference: str | None = Field(default=None, max_length=60)
    invoice_date: date | None = None
    due_date: date | None = None
    lines: list[CustomerInvoiceLineCreate]

    @model_validator(mode="after")
    def _check_due_date(self) -> CustomerInvoiceCreate:
        if (
            self.due_date is not None
            and self.invoice_date is not None
            and self.due_date < self.invoice_date
        ):
            raise ValueError("due_date must be on or after invoice_date")
        return self


class CustomerInvoiceUpdate(BaseModel):
    """PUT body. Draft-only (enforced in the router) — omitted fields are
    left unchanged; `lines`, when given, replaces the whole line set."""

    customer_id: int | None = None
    invoice_reference: str | None = Field(default=None, max_length=60)
    invoice_date: date | None = None
    due_date: date | None = None
    lines: list[CustomerInvoiceLineCreate] | None = None

    @model_validator(mode="after")
    def _check_due_date(self) -> CustomerInvoiceUpdate:
        if (
            self.due_date is not None
            and self.invoice_date is not None
            and self.due_date < self.invoice_date
        ):
            raise ValueError("due_date must be on or after invoice_date")
        return self


class CustomerInvoiceLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_name: str | None = None
    account_id: int
    account_name: str | None = None
    analytic_account_id: int | None = None
    analytic_account_name: str | None = None
    quantity: Money
    unit_price: Money
    line_total: Money
    sequence: int


class CustomerInvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    customer_id: int
    customer_name: str | None = None
    invoice_reference: str | None = None
    invoice_date: date
    due_date: date | None = None
    state: DocumentState
    total_amount: Money
    source_so_id: int | None = None
    journal_entry_id: int | None = None
    # Derived on read, never stored (§7.7 computed_not_stored). Always zero /
    # not_paid until the payments module lands — no payment can exist yet.
    amount_paid: Money = Decimal("0.00")
    amount_due: Money = Decimal("0.00")
    payment_status: PaymentStatus = PaymentStatus.NOT_PAID
    lines: list[CustomerInvoiceLineRead] = []


class CustomerInvoiceListRow(BaseModel):
    id: int
    number: str
    customer_name: str | None = None
    invoice_date: date
    due_date: date | None = None
    total_amount: Money
    amount_due: Money
    payment_status: PaymentStatus
    state: DocumentState


class CustomerInvoiceConfirmResponse(BaseModel):
    """POST /customer-invoices/{id}/confirm response — mirrors the vendor
    bill confirm shape from §9 (`{bill, journal_entry_id, journal_entry_number}`)."""

    invoice: CustomerInvoiceRead
    journal_entry_id: int
    journal_entry_number: str
