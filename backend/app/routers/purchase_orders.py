"""Purchase order HTTP layer (SPEC.md §9 purchase).

Every route is guarded. §9's role table gives a contact no purchase access at
all, so accountant-or-admin is the requirement on reads as well as writes.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import DocumentState
from app.core.errors import AppError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.core.search import fk_matches, ilike_any, like_pattern
from app.database import get_db
from app.models.analytic import AnalyticAccount
from app.models.partner import Partner
from app.models.product import Product
from app.models.purchase import PurchaseOrder, PurchaseOrderLine, VendorBill
from app.models.user import User
from app.schemas.common import Page
from app.schemas.purchase import (
    PurchaseOrderCreate,
    PurchaseOrderLineIn,
    PurchaseOrderOut,
    PurchaseOrderRow,
    PurchaseOrderUpdate,
    VendorBillOut,
)
from app.services import purchase as purchase_service

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])

LEDGER_ROLES = ("admin", "accountant")


@router.get("", response_model=Page[PurchaseOrderRow])
def list_purchase_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    state: DocumentState | None = None,
    vendor_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> Page[PurchaseOrderRow]:
    stmt = select(PurchaseOrder)
    if state is not None:
        stmt = stmt.where(PurchaseOrder.state == state)
    if vendor_id is not None:
        stmt = stmt.where(PurchaseOrder.vendor_id == vendor_id)
    if search:
        pattern = like_pattern(search)
        stmt = stmt.where(
            or_(
                ilike_any(pattern, PurchaseOrder.number),
                fk_matches(
                    PurchaseOrder.vendor_id,
                    Partner.id,
                    ilike_any(pattern, Partner.name),
                ),
            )
        )
    # id tiebreaker: created_at alone isn't unique (rows from one bulk
    # transaction share a timestamp), which lets LIMIT/OFFSET pagination
    # duplicate/skip rows across pages — see sales_orders.py's list route.
    stmt = stmt.order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())

    rows, total = paginate(db, stmt, page, page_size)
    names = _vendor_names(db, [r.vendor_id for r in rows])

    return Page(
        items=[
            PurchaseOrderRow(
                id=r.id,
                number=r.number,
                vendor_id=r.vendor_id,
                vendor_name=names.get(r.vendor_id),
                order_date=r.order_date,
                state=r.state,
                total_amount=r.total_amount,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{order_id}", response_model=PurchaseOrderOut)
def get_purchase_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> PurchaseOrderOut:
    return _to_out(db, _get_or_404(db, order_id))


@router.post("", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> PurchaseOrderOut:
    _assert_partner(db, payload.vendor_id)

    order = PurchaseOrder(
        number=purchase_service.next_purchase_order_number(db),
        vendor_id=payload.vendor_id,
        order_date=payload.order_date or date.today(),
        state=DocumentState.DRAFT,
    )
    _replace_lines(db, order, payload.lines)

    db.add(order)
    db.commit()
    db.refresh(order)
    return _to_out(db, order)


@router.put("/{order_id}", response_model=PurchaseOrderOut)
def update_purchase_order(
    order_id: int,
    payload: PurchaseOrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> PurchaseOrderOut:
    order = _get_or_404(db, order_id)
    if order.state is not DocumentState.DRAFT:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            "Only a draft purchase order can be edited.",
        )

    if payload.vendor_id is not None:
        _assert_partner(db, payload.vendor_id)
        order.vendor_id = payload.vendor_id
    if payload.order_date is not None:
        order.order_date = payload.order_date
    if payload.lines is not None:
        _replace_lines(db, order, payload.lines)

    db.commit()
    db.refresh(order)
    return _to_out(db, order)


@router.post("/{order_id}/confirm", response_model=PurchaseOrderOut)
def confirm_purchase_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> PurchaseOrderOut:
    """Confirm a PO. Produces NO journal entry — it is a commitment (§10.5)."""
    order = _get_or_404(db, order_id)
    purchase_service.confirm_purchase_order(db, order)
    db.commit()
    db.refresh(order)
    return _to_out(db, order)


@router.post("/{order_id}/cancel", response_model=PurchaseOrderOut)
def cancel_purchase_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> PurchaseOrderOut:
    order = _get_or_404(db, order_id)
    purchase_service.cancel_purchase_order(db, order)
    db.commit()
    db.refresh(order)
    return _to_out(db, order)


@router.post(
    "/{order_id}/create-bill",
    response_model=VendorBillOut,
    status_code=status.HTTP_201_CREATED,
)
def create_bill_from_purchase_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> VendorBillOut:
    """Copy a confirmed PO into a draft bill (§10.5)."""
    from app.routers.vendor_bills import bill_to_out

    order = _get_or_404(db, order_id)
    bill = purchase_service.create_bill_from_po(db, order)
    db.commit()
    db.refresh(bill)
    return bill_to_out(db, bill)


# --- helpers ----------------------------------------------------------------


def _get_or_404(db: Session, order_id: int) -> PurchaseOrder:
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise AppError(404, "NOT_FOUND", f"Purchase order {order_id} does not exist.")
    return order


def _assert_partner(db: Session, partner_id: int) -> None:
    partner = db.get(Partner, partner_id)
    if partner is None or not partner.is_active:
        raise AppError(404, "NOT_FOUND", "Vendor not found.")


def _replace_lines(
    db: Session, order: PurchaseOrder, lines: list[PurchaseOrderLineIn]
) -> None:
    """Rebuild the line set, recomputing every total server-side (R6)."""
    order.lines.clear()
    for index, line in enumerate(lines):
        if db.get(Product, line.product_id) is None:
            raise AppError(404, "NOT_FOUND", f"Product {line.product_id} not found.")
        if (
            line.analytic_account_id is not None
            and db.get(AnalyticAccount, line.analytic_account_id) is None
        ):
            raise AppError(404, "NOT_FOUND", "Analytic account not found.")

        order.lines.append(
            PurchaseOrderLine(
                product_id=line.product_id,
                analytic_account_id=line.analytic_account_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                # Any client-supplied line_total was never accepted; this is
                # the only place the figure comes from.
                line_total=purchase_service.compute_line_total(
                    line.quantity, line.unit_price
                ),
                sequence=(index + 1) * 10,
            )
        )
    order.total_amount = purchase_service.recompute_total(order.lines)


def _vendor_names(db: Session, ids: list[int]) -> dict[int, str]:
    unique = {i for i in ids if i is not None}
    if not unique:
        return {}
    rows = db.execute(
        select(Partner.id, Partner.name).where(Partner.id.in_(unique))
    ).all()
    return {r.id: r.name for r in rows}


def _to_out(db: Session, order: PurchaseOrder) -> PurchaseOrderOut:
    names = _vendor_names(db, [order.vendor_id])
    # Non-null once this order has been converted to a vendor bill — powers
    # the "Create Bill" -> "View Bill" swap on the PO detail page (§10.5).
    bill_id = db.execute(
        select(VendorBill.id).where(VendorBill.source_po_id == order.id)
    ).scalar_one_or_none()
    return PurchaseOrderOut(
        id=order.id,
        number=order.number,
        vendor_id=order.vendor_id,
        vendor_name=names.get(order.vendor_id),
        order_date=order.order_date,
        state=order.state,
        total_amount=order.total_amount,
        bill_id=bill_id,
        lines=[
            {
                "id": line.id,
                "product_id": line.product_id,
                "analytic_account_id": line.analytic_account_id,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "line_total": line.line_total,
                "sequence": line.sequence,
            }
            for line in order.lines
        ],
    )
