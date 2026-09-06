"""Payment HTTP layer (SPEC.md §9 payments)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import PaymentState, PaymentType
from app.core.errors import AppError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.core.search import fk_matches, ilike_any, like_pattern
from app.database import get_db
from app.models.partner import Partner
from app.models.payment import Payment
from app.models.sales import CustomerInvoice
from app.models.user import User
from app.schemas.common import Page
from app.schemas.payment import PaymentCreate, PaymentOut
from app.services import payments as payments_service

router = APIRouter(prefix="/payments", tags=["payments"])

LEDGER_ROLES = ("admin", "accountant")
# A contact may create and confirm a payment against their OWN document —
# §9 roles: "contact: ... create payments against them" — but never list or
# read arbitrary payments, which stays LEDGER_ROLES-only.
CREATE_ROLES = ("admin", "accountant", "contact")


def _assert_contact_owns_target(
    db: Session,
    current_user: User,
    *,
    partner_id: int,
    invoice_id: int | None,
    bill_id: int | None,
) -> None:
    """A contact may only ever pay their OWN customer invoice — never a
    vendor bill, regardless of ownership (§10.10, §12.2).

    A vendor bill means Urban Furniture owes the vendor; the vendor side of
    that transaction is passive (owed money, not paying it), and a 'send'
    payment records Urban Furniture's own outgoing bank transfer, which only
    an accountant/admin should ever create. A partner who is both a customer
    and a vendor (partner_type='both', e.g. seed data's "Mr Rahul") could
    otherwise pass an ownership check on their OWN bill and register a
    payment against it — ownership alone doesn't rule this out, so bill_id
    is refused outright before any ownership lookup runs.

    Every id here — partner_id, invoice_id, bill_id — comes from the request
    body, so none of it is trusted: each is checked against the document
    actually stored, not against what the client claims (R6).
    """
    if partner_id != current_user.partner_id:
        raise AppError(
            403,
            "INSUFFICIENT_ROLE",
            "You do not have permission to register this payment.",
        )
    if bill_id is not None:
        raise AppError(
            403,
            "INSUFFICIENT_ROLE",
            "You do not have permission to register a payment against a vendor bill.",
        )
    if invoice_id is not None:
        invoice = db.get(CustomerInvoice, invoice_id)
        if invoice is None or invoice.customer_id != current_user.partner_id:
            raise AppError(
                403,
                "INSUFFICIENT_ROLE",
                "You do not have permission to pay this invoice.",
            )


@router.get("", response_model=Page[PaymentOut])
def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    payment_type: PaymentType | None = None,
    partner_id: int | None = None,
    state: PaymentState | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> Page[PaymentOut]:
    stmt = select(Payment)
    if payment_type is not None:
        stmt = stmt.where(Payment.payment_type == payment_type)
    if partner_id is not None:
        stmt = stmt.where(Payment.partner_id == partner_id)
    if state is not None:
        stmt = stmt.where(Payment.state == state)
    if search:
        pattern = like_pattern(search)
        stmt = stmt.where(
            or_(
                ilike_any(pattern, Payment.number, Payment.note),
                fk_matches(
                    Payment.partner_id,
                    Partner.id,
                    ilike_any(pattern, Partner.name),
                ),
            )
        )
    # id tiebreaker: created_at alone isn't unique (rows from one bulk
    # transaction share a timestamp), which lets LIMIT/OFFSET pagination
    # duplicate/skip rows across pages — see routers/sales_orders.py.
    stmt = stmt.order_by(Payment.created_at.desc(), Payment.id.desc())

    rows, total = paginate(db, stmt, page, page_size)
    names = _partner_names(db, [r.partner_id for r in rows])

    return Page(
        items=[_to_out(p, names) for p in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> PaymentOut:
    payment = _get_or_404(db, payment_id)
    return _to_out(payment, _partner_names(db, [payment.partner_id]))


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*CREATE_ROLES)),
) -> PaymentOut:
    """Register a DRAFT payment. No ledger effect until confirmed (§10.6).

    Every §9 validation runs in the service: direction, journal type, target
    state, and the overpayment check. A contact may only register a payment
    against their own document (§9 roles, §10.10) — admin/accountant are
    unrestricted.
    """
    if db.get(Partner, payload.partner_id) is None:
        raise AppError(404, "NOT_FOUND", "Partner not found.")
    if current_user.role.value == "contact":
        _assert_contact_owns_target(
            db,
            current_user,
            partner_id=payload.partner_id,
            invoice_id=payload.invoice_id,
            bill_id=payload.bill_id,
        )

    payment = payments_service.register_payment(
        db,
        payment_type=payload.payment_type,
        partner_id=payload.partner_id,
        journal_id=payload.journal_id,
        amount=payload.amount,
        payment_date=payload.payment_date or date.today(),
        note=payload.note,
        invoice_id=payload.invoice_id,
        bill_id=payload.bill_id,
    )
    db.commit()
    db.refresh(payment)
    return _to_out(payment, _partner_names(db, [payment.partner_id]))


@router.post("/{payment_id}/confirm", response_model=PaymentOut)
def confirm_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*CREATE_ROLES)),
) -> PaymentOut:
    """★ Atomic: the payment's state change and its journal entry, or neither.

    A contact may only confirm their OWN payment against their OWN customer
    invoice — re-checked here, not only at registration, because the payment
    id is a path parameter a contact could otherwise enumerate to confirm
    someone else's draft (§12.2), or (were create_payment's bill_id refusal
    ever bypassed, e.g. a draft payment an accountant created on a vendor's
    behalf) confirm a vendor-bill payment they have no business acting on —
    see _assert_contact_owns_target's docstring for why bill_id is refused
    outright rather than checked for ownership.
    """
    payment = _get_or_404(db, payment_id)
    if current_user.role.value == "contact":
        if payment.bill_id is not None:
            raise AppError(
                403,
                "INSUFFICIENT_ROLE",
                "You do not have permission to confirm a payment against a "
                "vendor bill.",
            )
        if payment.partner_id != current_user.partner_id:
            raise AppError(
                403,
                "INSUFFICIENT_ROLE",
                "You do not have permission to confirm this payment.",
            )
    payments_service.confirm_payment(db, payment)
    db.commit()
    db.refresh(payment)
    return _to_out(payment, _partner_names(db, [payment.partner_id]))


@router.post("/{payment_id}/cancel", response_model=PaymentOut)
def cancel_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> PaymentOut:
    """Draft only — a confirmed payment's entry is posted and immutable."""
    payment = _get_or_404(db, payment_id)
    payments_service.cancel_payment(db, payment)
    db.commit()
    db.refresh(payment)
    return _to_out(payment, _partner_names(db, [payment.partner_id]))


# --- helpers ----------------------------------------------------------------


def _get_or_404(db: Session, payment_id: int) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise AppError(404, "NOT_FOUND", f"Payment {payment_id} does not exist.")
    return payment


def _partner_names(db: Session, ids: list[int]) -> dict[int, str]:
    unique = {i for i in ids if i is not None}
    if not unique:
        return {}
    rows = db.execute(
        select(Partner.id, Partner.name).where(Partner.id.in_(unique))
    ).all()
    return {r.id: r.name for r in rows}


def _to_out(payment: Payment, names: dict[int, str]) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        number=payment.number,
        payment_type=payment.payment_type,
        partner_id=payment.partner_id,
        partner_name=names.get(payment.partner_id),
        journal_id=payment.journal_id,
        amount=payment.amount,
        payment_date=payment.payment_date,
        note=payment.note,
        state=payment.state,
        invoice_id=payment.invoice_id,
        bill_id=payment.bill_id,
        journal_entry_id=payment.journal_entry_id,
    )
