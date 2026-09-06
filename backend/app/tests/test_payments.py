"""Payment tests — SPEC.md §10.6.

Payment status is the thing to watch here. Every assertion below reads it from
a query, never from a column, which is the whole point: there is no stored
field that can drift out of step with the payments themselves.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.enums import (
    DocumentState,
    JournalType,
    PaymentState,
    PaymentStatus,
    PaymentType,
)
from app.core.errors import AppError
from app.models.account import Journal
from app.models.journal_entry import JournalEntry
from app.models.purchase import VendorBill, VendorBillLine
from app.services import payments as payments_service
from app.services import purchase as purchase_service

JANUARY = date(2026, 1, 15)


def _confirmed_bill(db, seed, amount: str = "6000.00") -> VendorBill:
    bill = VendorBill(
        number=purchase_service.next_vendor_bill_number(db),
        vendor_id=seed["partner_id"],
        bill_date=JANUARY,
        state=DocumentState.DRAFT,
    )
    bill.lines.append(
        VendorBillLine(
            product_id=seed["table"].id,
            account_id=seed["purchase_expense"].id,
            quantity=Decimal("1.00"),
            unit_price=Decimal(amount),
            line_total=Decimal(amount),
            sequence=10,
        )
    )
    bill.total_amount = Decimal(amount)
    db.add(bill)
    db.flush()

    bill, _ = purchase_service.confirm_vendor_bill(db, bill)
    return bill


def _bank_journal(db, seed) -> Journal:
    journal = Journal(
        name="Bank Payments",
        journal_type=JournalType.BANK,
        default_account_id=seed["bank"].id,
    )
    db.add(journal)
    db.flush()
    return journal


# --- Scenario: derived status ----------------------------------------------


def test_a_new_bill_is_not_paid(db, purchase_ledger):
    bill = _confirmed_bill(db, purchase_ledger)

    summary = payments_service.bill_payment_summary(db, bill)

    assert summary.amount_paid == Decimal("0.00")
    assert summary.amount_due == Decimal("6000.00")
    assert summary.payment_status is PaymentStatus.NOT_PAID


@pytest.mark.parametrize(
    ("paid", "expected"),
    [
        ("0.00", PaymentStatus.NOT_PAID),
        ("0.01", PaymentStatus.PARTIAL),
        ("9999.99", PaymentStatus.PARTIAL),
        ("10000.00", PaymentStatus.PAID),
    ],
)
def test_payment_status_is_derived(paid, expected):
    """§10.6's Scenario Outline, exactly. Pure function, no database needed."""
    summary = payments_service.summarise(Decimal("10000.00"), Decimal(paid))

    assert summary.payment_status is expected


def test_a_draft_payment_has_no_ledger_effect(db, purchase_ledger):
    """A draft payment records intent and nothing more (§10.6)."""
    bill = _confirmed_bill(db, purchase_ledger)
    journal = _bank_journal(db, purchase_ledger)
    entries_before = db.query(JournalEntry).count()

    payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("2000.00"),
        payment_date=JANUARY,
        bill_id=bill.id,
    )

    assert db.query(JournalEntry).count() == entries_before
    # The bill's amount due is untouched by a draft payment.
    assert payments_service.bill_payment_summary(db, bill).amount_due == Decimal(
        "6000.00"
    )


def test_partial_then_full_payment_moves_status(db, purchase_ledger):
    """not_paid -> partial -> paid, with the ledger following along (§10.6)."""
    bill = _confirmed_bill(db, purchase_ledger)
    journal = _bank_journal(db, purchase_ledger)

    first = payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("2000.00"),
        payment_date=JANUARY,
        bill_id=bill.id,
    )
    payments_service.confirm_payment(db, first)

    summary = payments_service.bill_payment_summary(db, bill)
    assert summary.amount_paid == Decimal("2000.00")
    assert summary.amount_due == Decimal("4000.00")
    assert summary.payment_status is PaymentStatus.PARTIAL

    second = payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("4000.00"),
        payment_date=JANUARY,
        bill_id=bill.id,
    )
    payments_service.confirm_payment(db, second)

    summary = payments_service.bill_payment_summary(db, bill)
    assert summary.amount_due == Decimal("0.00")
    assert summary.payment_status is PaymentStatus.PAID


# --- Scenario: the send payment's journal entry (§8.2) ----------------------


def test_confirming_a_send_payment_posts_the_worked_example(db, purchase_ledger):
    """Creditors debited, bank credited — what we owe goes down, cash goes down."""
    bill = _confirmed_bill(db, purchase_ledger)
    journal = _bank_journal(db, purchase_ledger)

    payment = payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("6000.00"),
        payment_date=JANUARY,
        bill_id=bill.id,
    )
    payments_service.confirm_payment(db, payment)

    assert payment.state is PaymentState.CONFIRMED
    entry = db.get(JournalEntry, payment.journal_entry_id)
    assert entry.number == payment.number

    by_account = {line.account_id: line for line in entry.lines}
    creditors = by_account[purchase_ledger["creditors"].id]
    bank = by_account[purchase_ledger["bank"].id]

    assert creditors.debit == Decimal("6000.00")
    assert creditors.partner_id == purchase_ledger["partner_id"]
    assert bank.credit == Decimal("6000.00")


def test_creditors_nets_to_zero_when_fully_paid(db, purchase_ledger):
    """The vendor correctly disappears from the Balance Sheet (§10.6)."""
    from sqlalchemy import func, select

    from app.models.journal_entry import JournalEntryLine

    bill = _confirmed_bill(db, purchase_ledger)
    journal = _bank_journal(db, purchase_ledger)

    payment = payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("6000.00"),
        payment_date=JANUARY,
        bill_id=bill.id,
    )
    payments_service.confirm_payment(db, payment)

    net = db.execute(
        select(
            func.coalesce(func.sum(JournalEntryLine.credit), 0)
            - func.coalesce(func.sum(JournalEntryLine.debit), 0)
        ).where(JournalEntryLine.account_id == purchase_ledger["creditors"].id)
    ).scalar_one()

    assert Decimal(net) == Decimal("0.00")


# --- Scenario: overpayment is rejected -------------------------------------


def test_overpayment_is_rejected(db, purchase_ledger):
    """★ 5000 against a remaining 4000 is refused, naming the 4000 (§10.6)."""
    bill = _confirmed_bill(db, purchase_ledger, "10000.00")
    journal = _bank_journal(db, purchase_ledger)

    first = payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("6000.00"),
        payment_date=JANUARY,
        bill_id=bill.id,
    )
    payments_service.confirm_payment(db, first)

    with pytest.raises(AppError) as excinfo:
        payments_service.register_payment(
            db,
            payment_type=PaymentType.SEND,
            partner_id=purchase_ledger["partner_id"],
            journal_id=journal.id,
            amount=Decimal("5000.00"),
            payment_date=JANUARY,
            bill_id=bill.id,
        )

    assert excinfo.value.code == "OVERPAYMENT"
    assert excinfo.value.status_code == 422
    assert excinfo.value.details["amount_due"] == "4000.00"


def test_exact_remaining_amount_is_accepted(db, purchase_ledger):
    """The boundary is <=, not <. Paying off the exact remainder must work."""
    bill = _confirmed_bill(db, purchase_ledger, "10000.00")
    journal = _bank_journal(db, purchase_ledger)

    payment = payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("10000.00"),
        payment_date=JANUARY,
        bill_id=bill.id,
    )

    assert payment.amount == Decimal("10000.00")


# --- Scenario: validations --------------------------------------------------


def test_a_draft_bill_cannot_be_paid(db, purchase_ledger):
    bill = VendorBill(
        number=purchase_service.next_vendor_bill_number(db),
        vendor_id=purchase_ledger["partner_id"],
        bill_date=JANUARY,
        state=DocumentState.DRAFT,
        total_amount=Decimal("100.00"),
    )
    db.add(bill)
    db.flush()
    journal = _bank_journal(db, purchase_ledger)

    with pytest.raises(AppError) as excinfo:
        payments_service.register_payment(
            db,
            payment_type=PaymentType.SEND,
            partner_id=purchase_ledger["partner_id"],
            journal_id=journal.id,
            amount=Decimal("10.00"),
            payment_date=JANUARY,
            bill_id=bill.id,
        )

    assert excinfo.value.code == "DOCUMENT_NOT_CONFIRMED"


def test_payment_direction_must_match_the_document(db, purchase_ledger):
    """'receive' cannot settle a vendor bill (§10.6)."""
    bill = _confirmed_bill(db, purchase_ledger)
    journal = _bank_journal(db, purchase_ledger)

    with pytest.raises(AppError) as excinfo:
        payments_service.register_payment(
            db,
            payment_type=PaymentType.RECEIVE,
            partner_id=purchase_ledger["partner_id"],
            journal_id=journal.id,
            amount=Decimal("10.00"),
            payment_date=JANUARY,
            bill_id=bill.id,
        )

    assert excinfo.value.code == "PAYMENT_DIRECTION_MISMATCH"


def test_payments_must_use_a_bank_or_cash_journal(db, purchase_ledger):
    """The Purchase journal holds no money (§10.6)."""
    bill = _confirmed_bill(db, purchase_ledger)

    with pytest.raises(AppError) as excinfo:
        payments_service.register_payment(
            db,
            payment_type=PaymentType.SEND,
            partner_id=purchase_ledger["partner_id"],
            journal_id=purchase_ledger["purchase_journal"].id,
            amount=Decimal("10.00"),
            payment_date=JANUARY,
            bill_id=bill.id,
        )

    assert excinfo.value.code == "INVALID_PAYMENT_JOURNAL"


def test_a_confirmed_payment_cannot_be_cancelled(db, purchase_ledger):
    """Its journal entry is posted and immutable (§10.6, R4)."""
    bill = _confirmed_bill(db, purchase_ledger)
    journal = _bank_journal(db, purchase_ledger)

    payment = payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("6000.00"),
        payment_date=JANUARY,
        bill_id=bill.id,
    )
    payments_service.confirm_payment(db, payment)

    with pytest.raises(AppError) as excinfo:
        payments_service.cancel_payment(db, payment)

    assert excinfo.value.status_code == 409


def test_a_payment_needs_exactly_one_target(db, purchase_ledger):
    journal = _bank_journal(db, purchase_ledger)

    with pytest.raises(AppError):
        payments_service.register_payment(
            db,
            payment_type=PaymentType.SEND,
            partner_id=purchase_ledger["partner_id"],
            journal_id=journal.id,
            amount=Decimal("10.00"),
            payment_date=JANUARY,
        )


# --- payment date vs the document it settles --------------------------------
#
# Not in §10.6's scenario list. payment_date becomes the journal entry's
# entry_date (§8.2 payment mapping), so a payment dated before the document it
# settles posts to the ledger in a period where nothing was owed — the trial
# balance for that period shows a payment against a debt that does not exist
# yet. Rejected at registration, before anything reaches the ledger.


def test_a_payment_cannot_predate_the_bill_it_settles(db, purchase_ledger):
    bill = _confirmed_bill(db, purchase_ledger, "6000.00")
    journal = _bank_journal(db, purchase_ledger)

    with pytest.raises(AppError) as excinfo:
        payments_service.register_payment(
            db,
            payment_type=PaymentType.SEND,
            partner_id=purchase_ledger["partner_id"],
            journal_id=journal.id,
            amount=Decimal("6000.00"),
            payment_date=JANUARY - timedelta(days=1),
            bill_id=bill.id,
        )

    assert excinfo.value.code == "PAYMENT_BEFORE_DOCUMENT"
    assert excinfo.value.status_code == 422
    assert excinfo.value.details["document_date"] == JANUARY.isoformat()


def test_a_payment_on_the_bill_date_itself_is_accepted(db, purchase_ledger):
    """The boundary is >=, not >. Paying the day it is raised is normal."""
    bill = _confirmed_bill(db, purchase_ledger, "6000.00")
    journal = _bank_journal(db, purchase_ledger)

    payment = payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("6000.00"),
        payment_date=JANUARY,
        bill_id=bill.id,
    )

    assert payment.state is PaymentState.DRAFT


def test_a_later_payment_date_is_accepted(db, purchase_ledger):
    bill = _confirmed_bill(db, purchase_ledger, "6000.00")
    journal = _bank_journal(db, purchase_ledger)

    payment = payments_service.register_payment(
        db,
        payment_type=PaymentType.SEND,
        partner_id=purchase_ledger["partner_id"],
        journal_id=journal.id,
        amount=Decimal("6000.00"),
        payment_date=JANUARY + timedelta(days=30),
        bill_id=bill.id,
    )
    payments_service.confirm_payment(db, payment)

    entry = db.get(JournalEntry, payment.journal_entry_id)
    assert entry.entry_date == JANUARY + timedelta(days=30)


# --- line total rounding ----------------------------------------------------


def test_both_cycles_round_a_half_paise_tie_the_same_way():
    """The forms show this product live while you type (lib/money.ts), so the
    two services must not settle a tie in opposite directions.
    """
    from app.services import sales as sales_service

    quantity, unit_price = Decimal("1.50"), Decimal("0.01")

    assert purchase_service.compute_line_total(quantity, unit_price) == Decimal("0.02")
    assert sales_service.compute_line_total(quantity, unit_price) == Decimal("0.02")
