"""Payment registration, confirmation and derived status (SPEC.md §8.2, §10.6).

Two things are worth reading closely here.

**Payment status is a query, never a column.** ``amount_paid``, ``amount_due``
and ``payment_status`` are computed from confirmed payments every time they are
asked for. A stored status would need updating when a payment is confirmed,
cancelled, or its amount edited, and when the document total changes — and a
missed path leaves a bill showing "paid" that is not (R5, §7.8).

**A draft payment has no ledger effect at all.** It records intent. Only
``confirm_payment`` touches the ledger, and it does so through the posting
engine like every other writer (R1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import (
    AccountType,
    DocumentState,
    JournalType,
    PaymentState,
    PaymentStatus,
    PaymentType,
)
from app.core.errors import AppError
from app.models.account import Account, Journal
from app.models.payment import Payment
from app.models.purchase import VendorBill
from app.services._sales_bridge import customer_invoices
from app.services.accounting import LineInput, post_journal_entry
from app.services.sequences import _lock_sequence_row

ZERO = Decimal("0.00")

PAYMENT_SEQUENCE = "payment"
PAYMENT_PREFIX = "PAY"

# Money may only move through an account that actually holds money.
PAYMENT_JOURNAL_TYPES = (JournalType.BANK, JournalType.CASH)


@dataclass(frozen=True)
class PaymentSummary:
    """The three derived figures shown against a bill or an invoice."""

    total_amount: Decimal
    amount_paid: Decimal
    amount_due: Decimal
    payment_status: PaymentStatus


# --- numbering --------------------------------------------------------------


def next_payment_number(db: Session) -> str:
    """PAY/2026/0001 — resets yearly (§12.4).

    Reuses the row lock in services/sequences.py rather than reimplementing it;
    see the note on next_purchase_order_number in services/purchase.py.
    """
    year = date_type.today().year
    row = _lock_sequence_row(
        db, name=PAYMENT_SEQUENCE, prefix=PAYMENT_PREFIX, year=year
    )
    if row.year != year:
        row.year = year
        row.last_number = 0
    row.last_number += 1
    db.flush()
    return f"{PAYMENT_PREFIX}/{row.year}/{row.last_number:04d}"


# --- derived status (R5) ----------------------------------------------------


def amount_paid_for_bill(db: Session, bill_id: int) -> Decimal:
    """Sum of CONFIRMED payments against one bill. Drafts never count."""
    return Decimal(
        db.execute(
            select(func.coalesce(func.sum(Payment.amount), ZERO)).where(
                Payment.bill_id == bill_id,
                Payment.state == PaymentState.CONFIRMED,
            )
        ).scalar_one()
        or ZERO
    )


def amount_paid_for_invoice(db: Session, invoice_id: int) -> Decimal:
    """Sum of CONFIRMED payments against one customer invoice."""
    return Decimal(
        db.execute(
            select(func.coalesce(func.sum(Payment.amount), ZERO)).where(
                Payment.invoice_id == invoice_id,
                Payment.state == PaymentState.CONFIRMED,
            )
        ).scalar_one()
        or ZERO
    )


def summarise(total_amount: Decimal, amount_paid: Decimal) -> PaymentSummary:
    """Turn a total and a paid figure into the derived status (§10.6).

    The thresholds are exact Decimal comparisons, so 0.01 against a 10000.00
    document is 'partial' and 10000.00 is 'paid' — no epsilon, no rounding.
    """
    due = total_amount - amount_paid

    if due <= ZERO:
        status = PaymentStatus.PAID
    elif amount_paid <= ZERO:
        status = PaymentStatus.NOT_PAID
    else:
        status = PaymentStatus.PARTIAL

    return PaymentSummary(
        total_amount=total_amount,
        amount_paid=amount_paid,
        amount_due=due,
        payment_status=status,
    )


def bill_payment_summary(db: Session, bill: VendorBill) -> PaymentSummary:
    return summarise(bill.total_amount, amount_paid_for_bill(db, bill.id))


def invoice_payment_summary(db: Session, invoice_id: int) -> PaymentSummary:
    """Same computation for an invoice, read through the sales bridge."""
    row = db.execute(
        select(
            customer_invoices.c.total_amount,
            customer_invoices.c.state,
        ).where(customer_invoices.c.id == invoice_id)
    ).one_or_none()
    if row is None:
        raise AppError(404, "NOT_FOUND", f"Invoice {invoice_id} does not exist.")

    return summarise(Decimal(row.total_amount), amount_paid_for_invoice(db, invoice_id))


# --- registration -----------------------------------------------------------


def register_payment(
    db: Session,
    *,
    payment_type: PaymentType,
    partner_id: int,
    journal_id: int,
    amount: Decimal,
    payment_date,
    note: str | None = None,
    invoice_id: int | None = None,
    bill_id: int | None = None,
) -> Payment:
    """Create a DRAFT payment after every §9 validation passes.

    Nothing here touches the ledger. The payment exists, the document's
    amount_due is unchanged, and it does not appear in the trial balance
    until someone confirms it (§10.6).
    """
    if amount <= ZERO:
        raise AppError(422, "VALIDATION_ERROR", "Payment amount must be positive.")

    _assert_exactly_one_target(invoice_id, bill_id)
    _assert_direction_matches(payment_type, invoice_id, bill_id)
    _assert_payment_journal(db, journal_id)

    summary = _target_summary(db, invoice_id=invoice_id, bill_id=bill_id)

    # Overpayment is rejected rather than clamped: silently accepting 5000
    # against a 4000 balance would leave the ledger showing a negative debt.
    if amount > summary.amount_due:
        raise AppError(
            422,
            "OVERPAYMENT",
            f"Payment of {amount:.2f} exceeds the remaining due of "
            f"{summary.amount_due:.2f}.",
            {
                "amount": f"{amount:.2f}",
                "amount_due": f"{summary.amount_due:.2f}",
                "total_amount": f"{summary.total_amount:.2f}",
            },
        )

    payment = Payment(
        number=next_payment_number(db),
        payment_type=payment_type,
        partner_id=partner_id,
        journal_id=journal_id,
        amount=amount,
        payment_date=payment_date,
        note=note,
        state=PaymentState.DRAFT,
        invoice_id=invoice_id,
        bill_id=bill_id,
    )
    db.add(payment)
    db.flush()
    return payment


def confirm_payment(db: Session, payment: Payment) -> Payment:
    """★ Post the payment's journal entry and mark it confirmed (§8.2).

    Two lines, and which account sits on which side is the whole of it:

      receive — the customer paid us. Cash went UP, so the bank/cash account
                is debited; what they owe went DOWN, so Debtors is credited.
      send    — we paid a vendor. What we owe went DOWN, so Creditors is
                debited; cash went DOWN, so the bank/cash account is credited.

    After a full settlement the document's control account nets to zero and the
    partner correctly disappears from the Balance Sheet. That is the system
    working, and it is worth showing in the demo.

    Like the bill flow, this flushes and lets the caller commit, so the payment
    and its entry become true together or not at all (R3).
    """
    if payment.state is PaymentState.CONFIRMED:
        raise AppError(
            409, "ALREADY_CONFIRMED", "This payment has already been confirmed."
        )
    if payment.state is PaymentState.CANCELLED:
        raise AppError(
            409, "INVALID_STATE_TRANSITION", "A cancelled payment cannot be confirmed."
        )

    # Re-checked at confirm, not only at registration: another payment may have
    # been confirmed against the same document in between.
    summary = _target_summary(
        db, invoice_id=payment.invoice_id, bill_id=payment.bill_id
    )
    if payment.amount > summary.amount_due:
        raise AppError(
            422,
            "OVERPAYMENT",
            f"Payment of {payment.amount:.2f} exceeds the remaining due of "
            f"{summary.amount_due:.2f}.",
            {
                "amount": f"{payment.amount:.2f}",
                "amount_due": f"{summary.amount_due:.2f}",
            },
        )

    journal = db.get(Journal, payment.journal_id)
    if journal is None:
        raise AppError(404, "JOURNAL_NOT_FOUND", "The payment journal does not exist.")

    money_account_id = journal.default_account_id

    if payment.payment_type is PaymentType.RECEIVE:
        control = _control_account(db, AccountType.ASSET, "Debtors")
        lines = [
            LineInput(
                account_id=money_account_id,
                debit=payment.amount,
                label=payment.number,
            ),
            LineInput(
                account_id=control.id,
                credit=payment.amount,
                partner_id=payment.partner_id,
                label=payment.number,
            ),
        ]
    else:
        control = _control_account(db, AccountType.LIABILITY, "Creditors")
        lines = [
            LineInput(
                account_id=control.id,
                debit=payment.amount,
                partner_id=payment.partner_id,
                label=payment.number,
            ),
            LineInput(
                account_id=money_account_id,
                credit=payment.amount,
                label=payment.number,
            ),
        ]

    entry = post_journal_entry(
        db,
        entry_date=payment.payment_date,
        journal_id=payment.journal_id,
        lines=lines,
        partner_id=payment.partner_id,
        source_type="payment",
        source_id=payment.id,
        number=payment.number,
    )

    payment.state = PaymentState.CONFIRMED
    payment.journal_entry_id = entry.id
    db.flush()

    return payment


def cancel_payment(db: Session, payment: Payment) -> Payment:
    """Only a draft payment may be cancelled.

    A confirmed payment's journal entry is posted and immutable (P4), so there
    is nothing to undo without a reversal — which is the P2 path (§10.6).
    """
    if payment.state is PaymentState.CONFIRMED:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            "A confirmed payment cannot be cancelled; its journal entry is "
            "posted and immutable. Reverse the entry instead.",
        )

    payment.state = PaymentState.CANCELLED
    db.flush()
    return payment


# --- validation helpers -----------------------------------------------------


def _assert_exactly_one_target(invoice_id: int | None, bill_id: int | None) -> None:
    if (invoice_id is None) == (bill_id is None):
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "A payment settles exactly one document: supply either invoice_id "
            "or bill_id, not both and not neither.",
        )


def _assert_direction_matches(
    payment_type: PaymentType, invoice_id: int | None, bill_id: int | None
) -> None:
    if payment_type is PaymentType.RECEIVE and invoice_id is None:
        raise AppError(
            422,
            "PAYMENT_DIRECTION_MISMATCH",
            "A 'receive' payment settles a customer invoice.",
        )
    if payment_type is PaymentType.SEND and bill_id is None:
        raise AppError(
            422,
            "PAYMENT_DIRECTION_MISMATCH",
            "A 'send' payment settles a vendor bill.",
        )


def _assert_payment_journal(db: Session, journal_id: int) -> None:
    journal = db.get(Journal, journal_id)
    if journal is None:
        raise AppError(404, "JOURNAL_NOT_FOUND", "The payment journal does not exist.")
    if journal.journal_type not in PAYMENT_JOURNAL_TYPES:
        raise AppError(
            422,
            "INVALID_PAYMENT_JOURNAL",
            "Payments must use a bank or cash journal.",
            {"journal_type": journal.journal_type.value},
        )


def _target_summary(
    db: Session, *, invoice_id: int | None, bill_id: int | None
) -> PaymentSummary:
    """Load the target document and assert it is confirmed."""
    if bill_id is not None:
        bill = db.get(VendorBill, bill_id)
        if bill is None:
            raise AppError(404, "NOT_FOUND", f"Bill {bill_id} does not exist.")
        if bill.state is not DocumentState.CONFIRMED:
            raise AppError(
                422,
                "DOCUMENT_NOT_CONFIRMED",
                "A draft bill cannot be paid. Confirm it first.",
            )
        return bill_payment_summary(db, bill)

    row = db.execute(
        select(customer_invoices.c.total_amount, customer_invoices.c.state).where(
            customer_invoices.c.id == invoice_id
        )
    ).one_or_none()
    if row is None:
        raise AppError(404, "NOT_FOUND", f"Invoice {invoice_id} does not exist.")
    if row.state != DocumentState.CONFIRMED.value:
        raise AppError(
            422,
            "DOCUMENT_NOT_CONFIRMED",
            "A draft invoice cannot be paid. Confirm it first.",
        )
    return summarise(Decimal(row.total_amount), amount_paid_for_invoice(db, invoice_id))


def _control_account(db: Session, account_type: AccountType, label: str) -> Account:
    """Debtors (asset) or Creditors (liability) — the partner control account."""
    account = (
        db.execute(
            select(Account)
            .where(
                Account.account_type == account_type,
                Account.is_archived.is_(False),
            )
            .order_by(Account.code)
        )
        .scalars()
        .first()
    )
    if account is None:
        raise AppError(
            422,
            "ACCOUNT_NOT_FOUND",
            f"No {label} account exists. Seed the chart of accounts first.",
        )
    return account
