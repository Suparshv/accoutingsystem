"""Sales order HTTP layer (SPEC.md §9 sales section)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import DocumentState, PaymentStatus
from app.core.errors import NotFoundError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.database import get_db
from app.models.sales import CustomerInvoice, SalesOrder
from app.models.user import User
from app.schemas.common import Page
from app.schemas.sales import (
    CustomerInvoiceRead,
    SalesOrderCreate,
    SalesOrderListRow,
    SalesOrderRead,
)
from app.services import sales as sales_service

router = APIRouter(prefix="/sales-orders", tags=["sales-orders"])


def _get_or_404(db: Session, sales_order_id: int) -> SalesOrder:
    so = db.get(SalesOrder, sales_order_id)
    if so is None:
        raise NotFoundError(f"Sales order {sales_order_id} does not exist.")
    return so


def _to_invoice_read(invoice: CustomerInvoice) -> CustomerInvoiceRead:
    """Attach the derived, never-stored payment fields (§7.7, P5).

    Duplicated in routers/customer_invoices.py rather than shared, because a
    router must never import another router (AGENTS.md §3) and this is a few
    lines of pure shaping, not business logic — compute_payment_status
    itself lives once, in services/sales.py.
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


@router.get("", response_model=Page[SalesOrderListRow])
def list_sales_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    state: DocumentState | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
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
    current_user: User = Depends(require_role("admin", "accountant")),
) -> SalesOrderRead:
    return SalesOrderRead.model_validate(_get_or_404(db, sales_order_id))


@router.post("", response_model=SalesOrderRead, status_code=status.HTTP_201_CREATED)
def create_sales_order(
    payload: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> SalesOrderRead:
    so = sales_service.create_sales_order(
        db,
        customer_id=payload.customer_id,
        order_date=payload.order_date or date.today(),
        lines=[line.model_dump() for line in payload.lines],
    )
    db.commit()
    db.refresh(so)
    return SalesOrderRead.model_validate(so)


@router.post("/{sales_order_id}/confirm", response_model=SalesOrderRead)
def confirm_sales_order(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> SalesOrderRead:
    """State change only — a sales order produces NO journal entry (§7.7)."""
    so = sales_service.confirm_sales_order(db, sales_order_id=sales_order_id)
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
    current_user: User = Depends(require_role("admin", "accountant")),
) -> CustomerInvoiceRead:
    """Copies vendor/lines/analytics/qty/price into a draft invoice (§10.5's
    create-bill behaviour, mirrored on the sales side)."""
    invoice = sales_service.create_invoice_from_so(db, sales_order_id=sales_order_id)
    db.commit()
    db.refresh(invoice)
    return _to_invoice_read(invoice)
