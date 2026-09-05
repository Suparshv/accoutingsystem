"""Vendor bill HTTP layer (SPEC.md §9 purchase).

The confirm route is the one to read: it calls the service, then issues the
single commit that makes the bill's state change and its journal entry true
together. It does not catch the engine's exceptions — a failed post must abort
the whole request (§8.3).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import DocumentState
from app.core.errors import AppError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.database import get_db
from app.models.account import Account
from app.models.analytic import AnalyticAccount
from app.models.journal_entry import JournalEntry
from app.models.partner import Partner
from app.models.product import Product
from app.models.purchase import VendorBill, VendorBillLine
from app.models.user import User
from app.schemas.common import Page
from app.schemas.purchase import (
    VendorBillConfirmOut,
    VendorBillCreate,
    VendorBillLineIn,
    VendorBillOut,
    VendorBillRow,
    VendorBillUpdate,
)
from app.services import payments as payments_service
from app.services import purchase as purchase_service

router = APIRouter(prefix="/vendor-bills", tags=["vendor-bills"])

LEDGER_ROLES = ("admin", "accountant")


@router.get("", response_model=Page[VendorBillRow])
def list_vendor_bills(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    state: DocumentState | None = None,
    vendor_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> Page[VendorBillRow]:
    stmt = select(VendorBill)
    if state is not None:
        stmt = stmt.where(VendorBill.state == state)
    if vendor_id is not None:
        stmt = stmt.where(VendorBill.vendor_id == vendor_id)
    if search:
        stmt = stmt.where(VendorBill.number.ilike(f"%{search}%"))
    # id tiebreaker: created_at alone isn't unique (rows from one bulk
    # transaction share a timestamp), which lets LIMIT/OFFSET pagination
    # duplicate/skip rows across pages — see sales_orders.py's list route.
    stmt = stmt.order_by(VendorBill.created_at.desc(), VendorBill.id.desc())

    rows, total = paginate(db, stmt, page, page_size)
    names = _vendor_names(db, [r.vendor_id for r in rows])

    items = []
    for bill in rows:
        # Payment status is derived per row, never read from a column (R5).
        summary = payments_service.bill_payment_summary(db, bill)
        items.append(
            VendorBillRow(
                id=bill.id,
                number=bill.number,
                vendor_id=bill.vendor_id,
                vendor_name=names.get(bill.vendor_id),
                bill_date=bill.bill_date,
                due_date=bill.due_date,
                state=bill.state,
                total_amount=bill.total_amount,
                amount_due=summary.amount_due,
                payment_status=summary.payment_status,
            )
        )

    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{bill_id}", response_model=VendorBillOut)
def get_vendor_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> VendorBillOut:
    return bill_to_out(db, _get_or_404(db, bill_id))


@router.post("", response_model=VendorBillOut, status_code=status.HTTP_201_CREATED)
def create_vendor_bill(
    payload: VendorBillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> VendorBillOut:
    """A bill created directly has source_po_id null — no PO button (§10.5)."""
    _assert_partner(db, payload.vendor_id)

    bill = VendorBill(
        number=purchase_service.next_vendor_bill_number(db),
        vendor_id=payload.vendor_id,
        bill_reference=payload.bill_reference,
        bill_date=payload.bill_date or date.today(),
        due_date=payload.due_date,
        state=DocumentState.DRAFT,
    )
    _replace_lines(db, bill, payload.lines)

    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill_to_out(db, bill)


@router.put("/{bill_id}", response_model=VendorBillOut)
def update_vendor_bill(
    bill_id: int,
    payload: VendorBillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> VendorBillOut:
    """Draft only. A confirmed bill's lines cannot change (R4)."""
    bill = _get_or_404(db, bill_id)
    if bill.state is not DocumentState.DRAFT:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            "Only a draft bill can be edited; a confirmed bill is immutable.",
        )

    if payload.vendor_id is not None:
        _assert_partner(db, payload.vendor_id)
        bill.vendor_id = payload.vendor_id
    if payload.bill_reference is not None:
        bill.bill_reference = payload.bill_reference
    if payload.bill_date is not None:
        bill.bill_date = payload.bill_date
    if payload.due_date is not None:
        bill.due_date = payload.due_date
    if payload.lines is not None:
        _replace_lines(db, bill, payload.lines)

    db.commit()
    db.refresh(bill)
    return bill_to_out(db, bill)


@router.post("/{bill_id}/confirm", response_model=VendorBillConfirmOut)
def confirm_vendor_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> VendorBillConfirmOut:
    """★ Atomic: state change + journal entry, or neither (§10.5).

    The single db.commit() below is the transaction boundary. If
    confirm_vendor_bill raises anywhere inside — an unbalanced entry, a missing
    account, an archived account — this line is never reached, the request's
    transaction rolls back, and the bill is still draft with no entry behind it.
    """
    bill = _get_or_404(db, bill_id)

    bill, warnings = purchase_service.confirm_vendor_bill(db, bill)
    db.commit()
    db.refresh(bill)

    entry = db.get(JournalEntry, bill.journal_entry_id)
    return VendorBillConfirmOut(
        bill=bill_to_out(db, bill),
        journal_entry_id=entry.id,
        journal_entry_number=entry.number,
        warnings=warnings,
    )


@router.post("/{bill_id}/cancel", response_model=VendorBillOut)
def cancel_vendor_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> VendorBillOut:
    bill = _get_or_404(db, bill_id)
    purchase_service.cancel_vendor_bill(db, bill)
    db.commit()
    db.refresh(bill)
    return bill_to_out(db, bill)


# --- helpers ----------------------------------------------------------------


def _get_or_404(db: Session, bill_id: int) -> VendorBill:
    bill = db.get(VendorBill, bill_id)
    if bill is None:
        raise AppError(404, "NOT_FOUND", f"Vendor bill {bill_id} does not exist.")
    return bill


def _assert_partner(db: Session, partner_id: int) -> None:
    partner = db.get(Partner, partner_id)
    if partner is None or not partner.is_active:
        raise AppError(404, "NOT_FOUND", "Vendor not found.")


def _replace_lines(
    db: Session, bill: VendorBill, lines: list[VendorBillLineIn]
) -> None:
    bill.lines.clear()
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
                "An archived account cannot be used on a new bill line.",
            )
        if (
            line.analytic_account_id is not None
            and db.get(AnalyticAccount, line.analytic_account_id) is None
        ):
            raise AppError(404, "NOT_FOUND", "Analytic account not found.")

        bill.lines.append(
            VendorBillLine(
                product_id=line.product_id,
                account_id=line.account_id,
                analytic_account_id=line.analytic_account_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=purchase_service.compute_line_total(
                    line.quantity, line.unit_price
                ),
                sequence=(index + 1) * 10,
            )
        )
    bill.total_amount = purchase_service.recompute_total(bill.lines)


def _vendor_names(db: Session, ids: list[int]) -> dict[int, str]:
    unique = {i for i in ids if i is not None}
    if not unique:
        return {}
    rows = db.execute(
        select(Partner.id, Partner.name).where(Partner.id.in_(unique))
    ).all()
    return {r.id: r.name for r in rows}


def bill_to_out(db: Session, bill: VendorBill) -> VendorBillOut:
    """Shape a bill for the wire, with its derived payment figures."""
    names = _vendor_names(db, [bill.vendor_id])
    summary = payments_service.bill_payment_summary(db, bill)

    return VendorBillOut(
        id=bill.id,
        number=bill.number,
        vendor_id=bill.vendor_id,
        vendor_name=names.get(bill.vendor_id),
        bill_reference=bill.bill_reference,
        bill_date=bill.bill_date,
        due_date=bill.due_date,
        state=bill.state,
        total_amount=bill.total_amount,
        source_po_id=bill.source_po_id,
        journal_entry_id=bill.journal_entry_id,
        amount_paid=summary.amount_paid,
        amount_due=summary.amount_due,
        payment_status=summary.payment_status,
        lines=[
            {
                "id": line.id,
                "product_id": line.product_id,
                "account_id": line.account_id,
                "analytic_account_id": line.analytic_account_id,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "line_total": line.line_total,
                "sequence": line.sequence,
            }
            for line in bill.lines
        ],
    )
