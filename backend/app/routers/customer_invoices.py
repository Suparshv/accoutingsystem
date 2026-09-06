"""Customer invoice HTTP layer (SPEC.md §9 sales section, §8.2, §10.6, §10.10)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.core.enums import DocumentState, PaymentStatus
from app.core.errors import AppError, NotFoundError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.core.search import fk_matches, ilike_any, like_pattern
from app.database import get_db
from app.models.account import Account
from app.models.analytic import AnalyticAccount
from app.models.partner import Partner
from app.models.product import Product
from app.models.sales import CustomerInvoice, CustomerInvoiceLine
from app.models.user import User
from app.schemas.common import Page
from app.schemas.sales import (
    CustomerInvoiceConfirmResponse,
    CustomerInvoiceCreate,
    CustomerInvoiceLineCreate,
    CustomerInvoiceListRow,
    CustomerInvoiceRead,
    CustomerInvoiceUpdate,
)
from app.services import payments as payments_service
from app.services import sales as sales_service

router = APIRouter(prefix="/customer-invoices", tags=["customer-invoices"])

LEDGER_ROLES = ("admin", "accountant")


def _get_or_404(db: Session, invoice_id: int) -> CustomerInvoice:
    invoice = db.get(CustomerInvoice, invoice_id)
    if invoice is None:
        raise NotFoundError(f"Customer invoice {invoice_id} does not exist.")
    return invoice


def _assert_partner(db: Session, customer_id: int) -> None:
    partner = db.get(Partner, customer_id)
    if partner is None or not partner.is_active:
        raise AppError(404, "NOT_FOUND", "Customer not found.")


def _replace_lines(
    db: Session, invoice: CustomerInvoice, lines: list[CustomerInvoiceLineCreate]
) -> None:
    """Rebuild the line set, recomputing every total server-side (R6) —
    mirrors routers/vendor_bills.py's _replace_lines exactly."""
    invoice.lines.clear()
    for index, line in enumerate(lines):
        if db.get(Product, line.product_id) is None:
            raise AppError(404, "NOT_FOUND", f"Product {line.product_id} not found.")
        account = db.get(Account, line.account_id)
        if account is None:
            raise AppError(404, "ACCOUNT_NOT_FOUND", "Account not found.")
        if account.is_archived:
            raise AppError(
                422,
                "ACCOUNT_ARCHIVED",
                "An archived account cannot be used on a new invoice line.",
            )
        if (
            line.analytic_account_id is not None
            and db.get(AnalyticAccount, line.analytic_account_id) is None
        ):
            raise AppError(404, "NOT_FOUND", "Analytic account not found.")

        invoice.lines.append(
            CustomerInvoiceLine(
                product_id=line.product_id,
                account_id=line.account_id,
                analytic_account_id=line.analytic_account_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=sales_service.compute_line_total(
                    line.quantity, line.unit_price
                ),
                sequence=(index + 1) * 10,
            )
        )
    invoice.total_amount = sales_service.recompute_total(invoice.lines)


def _to_invoice_read(db: Session, invoice: CustomerInvoice) -> CustomerInvoiceRead:
    """Attach the derived, never-stored payment fields (§7.7, P5), computed
    for real from confirmed payments — never hardcoded."""
    summary = payments_service.invoice_payment_summary(db, invoice.id)
    read = CustomerInvoiceRead.model_validate(invoice)
    read.amount_paid = summary.amount_paid
    read.amount_due = summary.amount_due
    read.payment_status = PaymentStatus(summary.payment_status)
    return read


def _to_list_row(db: Session, invoice: CustomerInvoice) -> CustomerInvoiceListRow:
    summary = payments_service.invoice_payment_summary(db, invoice.id)
    return CustomerInvoiceListRow(
        id=invoice.id,
        number=invoice.number,
        customer_name=invoice.customer_name,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        total_amount=invoice.total_amount,
        amount_due=summary.amount_due,
        payment_status=PaymentStatus(summary.payment_status),
        state=invoice.state,
    )


@router.get("", response_model=Page[CustomerInvoiceListRow])
def list_customer_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    state: DocumentState | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> Page[CustomerInvoiceListRow]:
    """Admin/accountant only — a contact lists their own via
    GET /portal/my-documents (§9 roles), never this general endpoint."""
    stmt = select(CustomerInvoice)
    if state is not None:
        stmt = stmt.where(CustomerInvoice.state == state)
    if search:
        pattern = like_pattern(search)
        stmt = stmt.where(
            or_(
                ilike_any(pattern, CustomerInvoice.number),
                fk_matches(
                    CustomerInvoice.customer_id,
                    Partner.id,
                    ilike_any(pattern, Partner.name),
                ),
            )
        )
    # id tiebreaker: created_at alone isn't unique (rows from one bulk
    # transaction share a timestamp), which lets LIMIT/OFFSET pagination
    # duplicate/skip rows across pages — see routers/sales_orders.py.
    stmt = stmt.order_by(CustomerInvoice.created_at.desc(), CustomerInvoice.id.desc())

    rows, total = paginate(db, stmt, page, page_size)
    return Page[CustomerInvoiceListRow](
        items=[_to_list_row(db, invoice) for invoice in rows],
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
    return _to_invoice_read(db, invoice)


@router.post(
    "", response_model=CustomerInvoiceRead, status_code=status.HTTP_201_CREATED
)
def create_customer_invoice(
    payload: CustomerInvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> CustomerInvoiceRead:
    _assert_partner(db, payload.customer_id)
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
    return _to_invoice_read(db, invoice)


@router.put("/{invoice_id}", response_model=CustomerInvoiceRead)
def update_customer_invoice(
    invoice_id: int,
    payload: CustomerInvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> CustomerInvoiceRead:
    """Draft only. A confirmed invoice's lines cannot change (R4)."""
    invoice = _get_or_404(db, invoice_id)
    if invoice.state is not DocumentState.DRAFT:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            "Only a draft invoice can be edited; a confirmed invoice is immutable.",
        )

    if payload.customer_id is not None:
        _assert_partner(db, payload.customer_id)
        invoice.customer_id = payload.customer_id
    if payload.invoice_reference is not None:
        invoice.invoice_reference = payload.invoice_reference
    if payload.invoice_date is not None:
        invoice.invoice_date = payload.invoice_date
    if payload.due_date is not None:
        invoice.due_date = payload.due_date
    if payload.lines is not None:
        _replace_lines(db, invoice, payload.lines)

    db.commit()
    db.refresh(invoice)
    return _to_invoice_read(db, invoice)


@router.post("/{invoice_id}/confirm", response_model=CustomerInvoiceConfirmResponse)
def confirm_customer_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> CustomerInvoiceConfirmResponse:
    """★ Atomic per P3/R3: one commit for both the invoice's state change and
    its journal entry (§8.2). If the engine raises, the router never calls
    commit and nothing survives — no orphan entry, no half-confirmed invoice.
    """
    invoice, entry = sales_service.confirm_customer_invoice(db, invoice_id=invoice_id)
    db.commit()
    db.refresh(invoice)
    return CustomerInvoiceConfirmResponse(
        invoice=_to_invoice_read(db, invoice),
        journal_entry_id=entry.id,
        journal_entry_number=entry.number,
    )


@router.post("/{invoice_id}/cancel", response_model=CustomerInvoiceRead)
def cancel_customer_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> CustomerInvoiceRead:
    invoice = _get_or_404(db, invoice_id)
    sales_service.cancel_customer_invoice(db, invoice)
    db.commit()
    db.refresh(invoice)
    return _to_invoice_read(db, invoice)
