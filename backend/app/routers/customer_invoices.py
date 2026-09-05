"""Customer invoice HTTP layer (SPEC.md §9 sales section, §8.2, §10.6, §10.10)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.core.enums import DocumentState, PaymentStatus
from app.core.errors import AppError, NotFoundError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.database import get_db
from app.models.sales import CustomerInvoice
from app.models.user import User
from app.schemas.common import Page
from app.schemas.sales import (
    CustomerInvoiceConfirmResponse,
    CustomerInvoiceCreate,
    CustomerInvoiceListRow,
    CustomerInvoiceRead,
)
from app.services import sales as sales_service

router = APIRouter(prefix="/customer-invoices", tags=["customer-invoices"])


def _get_or_404(db: Session, invoice_id: int) -> CustomerInvoice:
    invoice = db.get(CustomerInvoice, invoice_id)
    if invoice is None:
        raise NotFoundError(f"Customer invoice {invoice_id} does not exist.")
    return invoice


def _to_invoice_read(invoice: CustomerInvoice) -> CustomerInvoiceRead:
    """Attach the derived, never-stored payment fields (§7.7, P5).

    No payments module exists yet in this tree, so amount_paid is always
    zero — see services.sales.compute_payment_status's docstring for why
    wiring in a real amount_paid query later needs no change here.
    """
    amount_paid = Decimal("0.00")
    amount_due, status_value = sales_service.compute_payment_status(
        invoice.total_amount, amount_paid
    )
    read = CustomerInvoiceRead.model_validate(invoice)
    read.amount_paid = amount_paid
    read.amount_due = amount_due
    read.payment_status = PaymentStatus(status_value)
    return read


def _to_list_row(invoice: CustomerInvoice) -> CustomerInvoiceListRow:
    amount_paid = Decimal("0.00")
    amount_due, status_value = sales_service.compute_payment_status(
        invoice.total_amount, amount_paid
    )
    return CustomerInvoiceListRow(
        id=invoice.id,
        number=invoice.number,
        customer_name=invoice.customer_name,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        total_amount=invoice.total_amount,
        amount_due=amount_due,
        payment_status=PaymentStatus(status_value),
        state=invoice.state,
    )


@router.get("", response_model=Page[CustomerInvoiceListRow])
def list_customer_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    state: DocumentState | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Page[CustomerInvoiceListRow]:
    """Admin/accountant only — a contact lists their own via
    GET /portal/my-documents (§9 roles), never this general endpoint."""
    stmt = select(CustomerInvoice)
    if state is not None:
        stmt = stmt.where(CustomerInvoice.state == state)
    if search:
        stmt = stmt.where(CustomerInvoice.number.ilike(f"%{search}%"))
    stmt = stmt.order_by(CustomerInvoice.created_at.desc())

    rows, total = paginate(db, stmt, page, page_size)
    return Page[CustomerInvoiceListRow](
        items=[_to_list_row(invoice) for invoice in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{invoice_id}", response_model=CustomerInvoiceRead)
def get_customer_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CustomerInvoiceRead:
    """Any authenticated role may call this — a contact only their own.

    Ownership is checked here, in the router's authorisation step, on the
    resource that was actually looked up, not via a query filter: the
    request either passes or is refused with no invoice data in the body
    (§12.2 ownership_checks, §10.10 "reveals nothing, including via the
    error message"). admin/accountant see any invoice.
    """
    invoice = _get_or_404(db, invoice_id)
    if (
        current_user.role.value == "contact"
        and invoice.customer_id != current_user.partner_id
    ):
        raise AppError(
            403,
            "INSUFFICIENT_ROLE",
            "You do not have permission to view this invoice.",
        )
    return _to_invoice_read(invoice)


@router.post(
    "", response_model=CustomerInvoiceRead, status_code=status.HTTP_201_CREATED
)
def create_customer_invoice(
    payload: CustomerInvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> CustomerInvoiceRead:
    invoice = sales_service.create_customer_invoice(
        db,
        customer_id=payload.customer_id,
        invoice_reference=payload.invoice_reference,
        invoice_date=payload.invoice_date or date.today(),
        due_date=payload.due_date,
        lines=[line.model_dump() for line in payload.lines],
    )
    db.commit()
    db.refresh(invoice)
    return _to_invoice_read(invoice)


@router.post("/{invoice_id}/confirm", response_model=CustomerInvoiceConfirmResponse)
def confirm_customer_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> CustomerInvoiceConfirmResponse:
    """★ Atomic per P3/R3: one commit for both the invoice's state change and
    its journal entry (§8.2). If the engine raises, the router never calls
    commit and nothing survives — no orphan entry, no half-confirmed invoice.
    """
    invoice, entry = sales_service.confirm_customer_invoice(db, invoice_id=invoice_id)
    db.commit()
    db.refresh(invoice)
    return CustomerInvoiceConfirmResponse(
        invoice=_to_invoice_read(invoice),
        journal_entry_id=entry.id,
        journal_entry_number=entry.number,
    )
