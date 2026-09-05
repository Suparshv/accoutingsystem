"""Sales order HTTP layer (SPEC.md §9 sales section)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import DocumentState, PaymentStatus
from app.core.errors import AppError, NotFoundError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.database import get_db
from app.models.analytic import AnalyticAccount
from app.models.partner import Partner
from app.models.product import Product
from app.models.sales import CustomerInvoice, SalesOrder, SalesOrderLine
from app.models.user import User
from app.schemas.common import Page
from app.schemas.sales import (
    CustomerInvoiceRead,
    SalesOrderCreate,
    SalesOrderLineCreate,
    SalesOrderListRow,
    SalesOrderRead,
    SalesOrderUpdate,
)
from app.services import payments as payments_service
from app.services import sales as sales_service

router = APIRouter(prefix="/sales-orders", tags=["sales-orders"])

LEDGER_ROLES = ("admin", "accountant")


def _get_or_404(db: Session, sales_order_id: int) -> SalesOrder:
    so = db.get(SalesOrder, sales_order_id)
    if so is None:
        raise NotFoundError(f"Sales order {sales_order_id} does not exist.")
    return so


def _assert_partner(db: Session, customer_id: int) -> None:
    partner = db.get(Partner, customer_id)
    if partner is None or not partner.is_active:
        raise AppError(404, "NOT_FOUND", "Customer not found.")


def _replace_lines(
    db: Session, so: SalesOrder, lines: list[SalesOrderLineCreate]
) -> None:
    """Rebuild the line set, recomputing every total server-side (R6) —
    mirrors routers/purchase_orders.py's _replace_lines exactly."""
    so.lines.clear()
    for index, line in enumerate(lines):
        if db.get(Product, line.product_id) is None:
            raise AppError(404, "NOT_FOUND", f"Product {line.product_id} not found.")
        if (
            line.analytic_account_id is not None
            and db.get(AnalyticAccount, line.analytic_account_id) is None
        ):
            raise AppError(404, "NOT_FOUND", "Analytic account not found.")

        so.lines.append(
            SalesOrderLine(
                product_id=line.product_id,
                analytic_account_id=line.analytic_account_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=sales_service.compute_line_total(
                    line.quantity, line.unit_price
                ),
                sequence=(index + 1) * 10,
            )
        )
    so.total_amount = sales_service.recompute_total(so.lines)


def _to_invoice_read(db: Session, invoice: CustomerInvoice) -> CustomerInvoiceRead:
    """Attach the derived, never-stored payment fields (§7.7, P5).

    Duplicated in routers/customer_invoices.py rather than shared, because a
    router must never import another router (AGENTS.md §3) — the real
    computation lives once, in services/payments.py.
    """
    summary = payments_service.invoice_payment_summary(db, invoice.id)
    read = CustomerInvoiceRead.model_validate(invoice)
    read.amount_paid = summary.amount_paid
    read.amount_due = summary.amount_due
    read.payment_status = PaymentStatus(summary.payment_status)
    return read


@router.get("", response_model=Page[SalesOrderListRow])
def list_sales_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    state: DocumentState | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> Page[SalesOrderListRow]:
    stmt = select(SalesOrder)
    if state is not None:
        stmt = stmt.where(SalesOrder.state == state)
    if search:
        stmt = stmt.where(SalesOrder.number.ilike(f"%{search}%"))
    stmt = stmt.order_by(SalesOrder.created_at.desc())

    rows, total = paginate(db, stmt, page, page_size)
    return Page[SalesOrderListRow](
        items=[SalesOrderListRow.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{sales_order_id}", response_model=SalesOrderRead)
def get_sales_order(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> SalesOrderRead:
    return SalesOrderRead.model_validate(_get_or_404(db, sales_order_id))


@router.post("", response_model=SalesOrderRead, status_code=status.HTTP_201_CREATED)
def create_sales_order(
    payload: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> SalesOrderRead:
    _assert_partner(db, payload.customer_id)
    so = sales_service.create_sales_order(
        db,
        customer_id=payload.customer_id,
        order_date=payload.order_date or date.today(),
        lines=[line.model_dump() for line in payload.lines],
    )
    db.commit()
    db.refresh(so)
    return SalesOrderRead.model_validate(so)


@router.put("/{sales_order_id}", response_model=SalesOrderRead)
def update_sales_order(
    sales_order_id: int,
    payload: SalesOrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> SalesOrderRead:
    """Draft only. A confirmed order's lines cannot change."""
    so = _get_or_404(db, sales_order_id)
    if so.state is not DocumentState.DRAFT:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            "Only a draft sales order can be edited.",
        )

    if payload.customer_id is not None:
        _assert_partner(db, payload.customer_id)
        so.customer_id = payload.customer_id
    if payload.order_date is not None:
        so.order_date = payload.order_date
    if payload.lines is not None:
        _replace_lines(db, so, payload.lines)

    db.commit()
    db.refresh(so)
    return SalesOrderRead.model_validate(so)


@router.post("/{sales_order_id}/confirm", response_model=SalesOrderRead)
def confirm_sales_order(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> SalesOrderRead:
    """State change only — a sales order produces NO journal entry (§7.7)."""
    so = sales_service.confirm_sales_order(db, sales_order_id=sales_order_id)
    db.commit()
    db.refresh(so)
    return SalesOrderRead.model_validate(so)


@router.post("/{sales_order_id}/cancel", response_model=SalesOrderRead)
def cancel_sales_order(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> SalesOrderRead:
    so = _get_or_404(db, sales_order_id)
    sales_service.cancel_sales_order(db, so)
    db.commit()
    db.refresh(so)
    return SalesOrderRead.model_validate(so)


@router.post(
    "/{sales_order_id}/create-invoice",
    response_model=CustomerInvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invoice_from_sales_order(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> CustomerInvoiceRead:
    """Copies vendor/lines/analytics/qty/price into a draft invoice (§10.5's
    create-bill behaviour, mirrored on the sales side)."""
    invoice = sales_service.create_invoice_from_so(db, sales_order_id=sales_order_id)
    db.commit()
    db.refresh(invoice)
    return _to_invoice_read(db, invoice)
