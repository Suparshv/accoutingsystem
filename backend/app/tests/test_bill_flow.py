"""Purchase cycle tests — SPEC.md §10.5 and §10.8.

The star of this file is the atomicity test. A failed post that leaves a
confirmed document with no ledger entry is the single worst outcome the system
can produce, because nothing looks wrong: the app works, the demo works, and
the database quietly accumulates documents no report can see.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.enums import BudgetLineType, BudgetState, DocumentState
from app.core.errors import AppError
from app.models.budget import Budget, BudgetLine
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.purchase import (
    PurchaseOrder,
    PurchaseOrderLine,
    VendorBill,
    VendorBillLine,
)
from app.services import purchase as purchase_service

JANUARY = date(2026, 1, 15)


def _count_entries(db) -> int:
    return db.execute(select(func.count()).select_from(JournalEntry)).scalar_one()


def _count_entry_lines(db) -> int:
    return db.execute(select(func.count()).select_from(JournalEntryLine)).scalar_one()


def _draft_bill(db, seed, lines) -> VendorBill:
    """A draft bill built directly, so tests can shape lines precisely."""
    bill = VendorBill(
        number=purchase_service.next_vendor_bill_number(db),
        vendor_id=seed["partner_id"],
        bill_date=JANUARY,
        state=DocumentState.DRAFT,
    )
    for index, (account, amount, analytic_id) in enumerate(lines):
        bill.lines.append(
            VendorBillLine(
                product_id=seed["table"].id,
                account_id=account.id,
                analytic_account_id=analytic_id,
                quantity=Decimal("1.00"),
                unit_price=amount,
                line_total=amount,
                sequence=(index + 1) * 10,
            )
        )
    bill.total_amount = purchase_service.recompute_total(bill.lines)
    db.add(bill)
    db.flush()
    return bill


# --- Scenario: confirming a purchase order creates NO journal entry ---------


def test_confirming_a_purchase_order_posts_nothing(db, purchase_ledger):
    """A PO is a commitment, not a financial event (§10.5)."""
    order = PurchaseOrder(
        number=purchase_service.next_purchase_order_number(db),
        vendor_id=purchase_ledger["partner_id"],
        order_date=JANUARY,
        state=DocumentState.DRAFT,
    )
    order.lines.append(
        PurchaseOrderLine(
            product_id=purchase_ledger["table"].id,
            quantity=Decimal("3.00"),
            unit_price=Decimal("2000.00"),
            line_total=Decimal("6000.00"),
            sequence=10,
        )
    )
    order.total_amount = purchase_service.recompute_total(order.lines)
    db.add(order)
    db.flush()

    entries_before = _count_entries(db)
    purchase_service.confirm_purchase_order(db, order)

    assert order.state is DocumentState.CONFIRMED
    assert _count_entries(db) == entries_before


def test_purchase_order_number_format(db, purchase_ledger):
    """P followed by five digits (§12.4)."""
    number = purchase_service.next_purchase_order_number(db)

    assert number.startswith("P")
    assert len(number) == 6
    assert number[1:].isdigit()


def test_purchase_order_numbers_increment(db, purchase_ledger):
    first = purchase_service.next_purchase_order_number(db)
    second = purchase_service.next_purchase_order_number(db)

    assert int(second[1:]) == int(first[1:]) + 1


def test_line_total_is_computed_server_side(db, purchase_ledger):
    """3 x 2000.00 is 6000.00 regardless of what a client claims (§10.5)."""
    assert purchase_service.compute_line_total(
        Decimal("3.00"), Decimal("2000.00")
    ) == Decimal("6000.00")


# --- Scenario: creating a bill from a confirmed PO copies everything --------


def test_create_bill_from_po_copies_lines_and_links_back(db, purchase_ledger):
    order = PurchaseOrder(
        number=purchase_service.next_purchase_order_number(db),
        vendor_id=purchase_ledger["partner_id"],
        order_date=JANUARY,
        state=DocumentState.CONFIRMED,
    )
    order.lines.append(
        PurchaseOrderLine(
            product_id=purchase_ledger["table"].id,
            analytic_account_id=purchase_ledger["project_one"].id,
            quantity=Decimal("3.00"),
            unit_price=Decimal("2000.00"),
            line_total=Decimal("6000.00"),
            sequence=10,
        )
    )
    order.total_amount = Decimal("6000.00")
    db.add(order)
    db.flush()

    bill = purchase_service.create_bill_from_po(db, order)

    assert bill.state is DocumentState.DRAFT
    assert bill.vendor_id == order.vendor_id
    assert bill.source_po_id == order.id
    assert bill.number.startswith("BILL/")
    assert len(bill.lines) == 1

    line = bill.lines[0]
    assert line.product_id == purchase_ledger["table"].id
    assert line.quantity == Decimal("3.00")
    assert line.unit_price == Decimal("2000.00")
    assert line.analytic_account_id == purchase_ledger["project_one"].id
    # Account defaults to Purchase Expense A/c — a PO line carries no account.
    assert line.account_id == purchase_ledger["purchase_expense"].id


def test_a_draft_po_cannot_be_billed(db, purchase_ledger):
    order = PurchaseOrder(
        number=purchase_service.next_purchase_order_number(db),
        vendor_id=purchase_ledger["partner_id"],
        order_date=JANUARY,
        state=DocumentState.DRAFT,
    )
    db.add(order)
    db.flush()

    with pytest.raises(AppError) as excinfo:
        purchase_service.create_bill_from_po(db, order)

    assert excinfo.value.code == "PO_NOT_CONFIRMED"
    assert excinfo.value.status_code == 409


# --- Scenario: confirming a bill posts a balanced entry --------------------


def test_confirming_a_bill_posts_the_worked_example(db, purchase_ledger):
    """§8.2's vendor bill worked example, exactly."""
    bill = _draft_bill(
        db,
        purchase_ledger,
        [(purchase_ledger["purchase_expense"], Decimal("6000.00"), None)],
    )

    bill, warnings = purchase_service.confirm_vendor_bill(db, bill)

    assert bill.state is DocumentState.CONFIRMED
    assert bill.journal_entry_id is not None
    assert warnings == []

    entry = db.get(JournalEntry, bill.journal_entry_id)
    assert entry.number == bill.number
    assert entry.state.value == "posted"
    assert entry.journal_id == purchase_ledger["purchase_journal"].id

    by_account = {line.account_id: line for line in entry.lines}
    expense = by_account[purchase_ledger["purchase_expense"].id]
    creditors = by_account[purchase_ledger["creditors"].id]

    assert expense.debit == Decimal("6000.00")
    assert expense.credit == Decimal("0.00")
    assert expense.partner_id == purchase_ledger["partner_id"]
    assert creditors.credit == Decimal("6000.00")
    assert creditors.debit == Decimal("0.00")
    assert creditors.partner_id == purchase_ledger["partner_id"]


# --- Scenario: grouped debit lines -----------------------------------------


def test_lines_on_different_accounts_produce_grouped_debits(db, purchase_ledger):
    """Two accounts -> three ledger lines (§10.5)."""
    bill = _draft_bill(
        db,
        purchase_ledger,
        [
            (purchase_ledger["purchase_expense"], Decimal("6000.00"), None),
            (purchase_ledger["other_expense"], Decimal("1000.00"), None),
        ],
    )

    bill, _ = purchase_service.confirm_vendor_bill(db, bill)
    entry = db.get(JournalEntry, bill.journal_entry_id)

    assert len(entry.lines) == 3
    by_account = {line.account_id: line for line in entry.lines}
    assert by_account[purchase_ledger["purchase_expense"].id].debit == Decimal(
        "6000.00"
    )
    assert by_account[purchase_ledger["other_expense"].id].debit == Decimal("1000.00")
    assert by_account[purchase_ledger["creditors"].id].credit == Decimal("7000.00")


def test_two_lines_on_the_same_account_are_merged(db, purchase_ledger):
    """★ Group by account, then sum. Not one ledger line per document line."""
    bill = _draft_bill(
        db,
        purchase_ledger,
        [
            (purchase_ledger["purchase_expense"], Decimal("4000.00"), None),
            (purchase_ledger["purchase_expense"], Decimal("2000.00"), None),
        ],
    )

    bill, _ = purchase_service.confirm_vendor_bill(db, bill)
    entry = db.get(JournalEntry, bill.journal_entry_id)

    assert len(entry.lines) == 2
    by_account = {line.account_id: line for line in entry.lines}
    assert by_account[purchase_ledger["purchase_expense"].id].debit == Decimal(
        "6000.00"
    )
    assert by_account[purchase_ledger["creditors"].id].credit == Decimal("6000.00")


def test_debits_equal_credits_on_a_confirmed_bill(db, purchase_ledger):
    bill = _draft_bill(
        db,
        purchase_ledger,
        [
            (purchase_ledger["purchase_expense"], Decimal("6000.00"), None),
            (purchase_ledger["other_expense"], Decimal("1000.00"), None),
        ],
    )
    bill, _ = purchase_service.confirm_vendor_bill(db, bill)
    entry = db.get(JournalEntry, bill.journal_entry_id)

    assert sum(line.debit for line in entry.lines) == sum(
        line.credit for line in entry.lines
    )


# --- Scenario: a bill with no lines / double confirm -----------------------


def test_a_bill_with_no_lines_cannot_be_confirmed(db, purchase_ledger):
    bill = _draft_bill(db, purchase_ledger, [])

    with pytest.raises(AppError) as excinfo:
        purchase_service.confirm_vendor_bill(db, bill)

    assert excinfo.value.code == "NO_LINES"
    assert excinfo.value.status_code == 422
    assert bill.state is DocumentState.DRAFT


def test_confirming_twice_is_rejected(db, purchase_ledger):
    bill = _draft_bill(
        db,
        purchase_ledger,
        [(purchase_ledger["purchase_expense"], Decimal("6000.00"), None)],
    )
    bill, _ = purchase_service.confirm_vendor_bill(db, bill)
    entries_after_first = _count_entries(db)

    with pytest.raises(AppError) as excinfo:
        purchase_service.confirm_vendor_bill(db, bill)

    assert excinfo.value.code == "ALREADY_CONFIRMED"
    assert excinfo.value.status_code == 409
    assert _count_entries(db) == entries_after_first


# --- ★ Scenario: atomicity — a failed post leaves nothing behind ------------


def test_a_failed_post_leaves_the_bill_draft_and_no_entry(db, purchase_ledger):
    """★ The most important non-happy-path behaviour in the system (§10.5).

    The account is archived after the bill is drafted, so the posting engine
    rejects it at step 6 — a real path, not an artificial one. Nothing about
    the bill or the ledger may survive.
    """
    bill = _draft_bill(
        db,
        purchase_ledger,
        [(purchase_ledger["purchase_expense"], Decimal("6000.00"), None)],
    )
    bill_id = bill.id

    # Commit the setup, so the rollback below discards only the failed confirm
    # — the same boundary a real request has, where the chart of accounts was
    # committed long before.
    db.commit()

    entries_before = _count_entries(db)
    lines_before = _count_entry_lines(db)

    purchase_ledger["purchase_expense"].is_archived = True
    db.commit()

    with pytest.raises(AppError) as excinfo:
        purchase_service.confirm_vendor_bill(db, bill)

    assert excinfo.value.code == "ACCOUNT_ARCHIVED"

    # In production get_db closes the session without committing, which
    # discards the transaction. Rolling back here is that same discard.
    db.rollback()

    reloaded = db.get(VendorBill, bill_id)
    assert reloaded.state is DocumentState.DRAFT
    assert reloaded.journal_entry_id is None
    assert _count_entries(db) == entries_before
    assert _count_entry_lines(db) == lines_before


def test_a_failed_post_through_the_api_leaves_nothing_behind(
    client, db, purchase_ledger
):
    """The same guarantee, exercised through the HTTP layer."""
    bill = _draft_bill(
        db,
        purchase_ledger,
        [(purchase_ledger["purchase_expense"], Decimal("6000.00"), None)],
    )
    db.commit()
    bill_id = bill.id

    purchase_ledger["purchase_expense"].is_archived = True
    db.commit()

    entries_before = _count_entries(db)
    lines_before = _count_entry_lines(db)

    response = client.post(f"/api/vendor-bills/{bill_id}/confirm")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ACCOUNT_ARCHIVED"

    db.rollback()
    reloaded = db.get(VendorBill, bill_id)
    assert reloaded.state is DocumentState.DRAFT
    assert reloaded.journal_entry_id is None
    assert _count_entries(db) == entries_before
    assert _count_entry_lines(db) == lines_before


# --- Scenario: cancelling a PO resolves its linked bill (§10.5) ------------


def _confirmed_po(db, seed) -> PurchaseOrder:
    order = PurchaseOrder(
        number=purchase_service.next_purchase_order_number(db),
        vendor_id=seed["partner_id"],
        order_date=JANUARY,
        state=DocumentState.CONFIRMED,
    )
    order.lines.append(
        PurchaseOrderLine(
            product_id=seed["table"].id,
            quantity=Decimal("3.00"),
            unit_price=Decimal("2000.00"),
            line_total=Decimal("6000.00"),
            sequence=10,
        )
    )
    order.total_amount = Decimal("6000.00")
    db.add(order)
    db.flush()
    return order


def test_get_vendor_bill_resolves_product_and_account_names(
    client, db, purchase_ledger
):
    """A bill's lines must resolve product_name/account_name for the wire,
    exactly like CustomerInvoiceRead already does for invoice lines.

    Regression test: bill_to_out used to build each line as a raw dict with
    no name fields at all (a bill's Product/Service column showed a raw id
    on the portal detail view), and — once VendorBillLine grew product/
    account relationships and bill_to_out switched to model_validate — a
    second bug where VendorBillOut.amount_paid/amount_due/payment_status had
    no defaults, so model_validate(bill) 500'd before those three could be
    overwritten with the real computed values. Goes through the actual HTTP
    routes (create-bill, confirm, get) because both bugs only manifest when
    bill_to_out actually runs to completion on a real ORM object — every
    other test in this file drives services/purchase.py directly and never
    hit either one.
    """
    order = _confirmed_po(db, purchase_ledger)

    create_response = client.post(f"/api/purchase-orders/{order.id}/create-bill")
    assert create_response.status_code == 201, create_response.text
    bill = create_response.json()
    assert bill["lines"][0]["product_name"] == purchase_ledger["table"].name
    assert bill["lines"][0]["account_name"] == purchase_ledger["purchase_expense"].name

    confirm_response = client.post(f"/api/vendor-bills/{bill['id']}/confirm")
    assert confirm_response.status_code == 200, confirm_response.text

    get_response = client.get(f"/api/vendor-bills/{bill['id']}")
    assert get_response.status_code == 200, get_response.text
    fetched = get_response.json()
    assert fetched["state"] == "confirmed"
    assert fetched["lines"][0]["product_name"] == purchase_ledger["table"].name


def test_cancelling_po_with_confirmed_bill_is_blocked(db, purchase_ledger):
    """Mirrors cancel_sales_order's Fix B on the purchase side: a confirmed
    bill's journal entry is posted and immutable (R4) — cancelling the PO
    must refuse rather than silently orphan it."""
    order = _confirmed_po(db, purchase_ledger)
    bill = purchase_service.create_bill_from_po(db, order)
    bill, _ = purchase_service.confirm_vendor_bill(db, bill)
    assert bill.state is DocumentState.CONFIRMED

    with pytest.raises(AppError) as excinfo:
        purchase_service.cancel_purchase_order(db, order)

    assert excinfo.value.code == "INVALID_STATE_TRANSITION"
    assert excinfo.value.status_code == 409
    assert order.state is DocumentState.CONFIRMED
    assert bill.state is DocumentState.CONFIRMED


def test_cancelling_po_cascades_to_draft_bill(db, purchase_ledger):
    """Mirrors cancel_sales_order's Fix C: a still-draft bill has no ledger
    effect (journal_entry_id is null), so cancelling the PO safely cascades
    to it instead of leaving it orphaned."""
    order = _confirmed_po(db, purchase_ledger)
    bill = purchase_service.create_bill_from_po(db, order)
    assert bill.state is DocumentState.DRAFT

    purchase_service.cancel_purchase_order(db, order)

    assert order.state is DocumentState.CANCELLED
    assert bill.state is DocumentState.CANCELLED


def test_confirming_bill_whose_source_po_was_cancelled_is_blocked(db, purchase_ledger):
    """Mirrors cancel_sales_order's Fix A: a bill already left orphaned (its
    source PO cancelled some other way, e.g. a pre-fix row) must not be
    confirmable. The PO is flipped directly here to reproduce that
    pre-existing-data shape, since cancel_purchase_order itself now always
    cascades to a draft bill and so can no longer produce it end to end.
    """
    order = _confirmed_po(db, purchase_ledger)
    bill = purchase_service.create_bill_from_po(db, order)

    order.state = DocumentState.CANCELLED
    db.flush()

    with pytest.raises(AppError) as excinfo:
        purchase_service.confirm_vendor_bill(db, bill)

    assert excinfo.value.code == "INVALID_STATE_TRANSITION"
    assert excinfo.value.status_code == 409


# --- Scenario: EXCEEDS_BUDGET warning (§10.8) ------------------------------


def _confirmed_budget(db, seed, committed: str, analytic_id: int) -> Budget:
    budget = Budget(
        name="January 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        state=BudgetState.CONFIRMED,
    )
    budget.lines.append(
        BudgetLine(
            analytic_account_id=analytic_id,
            line_type=BudgetLineType.EXPENSE,
            committed_amount=Decimal(committed),
            sequence=10,
        )
    )
    db.add(budget)
    db.flush()
    return budget


def test_confirming_over_budget_warns_but_still_posts(db, purchase_ledger):
    """★ Non-blocking: the bill IS confirmed and the entry IS posted (§10.8)."""
    analytic_id = purchase_ledger["project_one"].id
    _confirmed_budget(db, purchase_ledger, "10000.00", analytic_id)

    # 8000 already spent against Project 1.
    spent = _draft_bill(
        db,
        purchase_ledger,
        [(purchase_ledger["purchase_expense"], Decimal("8000.00"), analytic_id)],
    )
    purchase_service.confirm_vendor_bill(db, spent)

    # A further 5000 against a remaining 2000.
    bill = _draft_bill(
        db,
        purchase_ledger,
        [(purchase_ledger["purchase_expense"], Decimal("5000.00"), analytic_id)],
    )
    bill, warnings = purchase_service.confirm_vendor_bill(db, bill)

    assert bill.state is DocumentState.CONFIRMED
    assert bill.journal_entry_id is not None

    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["code"] == "EXCEEDS_BUDGET"
    assert warning["details"]["analytic_account_id"] == analytic_id
    assert warning["details"]["remaining_amount"] == "2000.00"


def test_confirming_within_budget_produces_no_warning(db, purchase_ledger):
    analytic_id = purchase_ledger["project_one"].id
    _confirmed_budget(db, purchase_ledger, "10000.00", analytic_id)

    bill = _draft_bill(
        db,
        purchase_ledger,
        [(purchase_ledger["purchase_expense"], Decimal("5000.00"), analytic_id)],
    )
    _, warnings = purchase_service.confirm_vendor_bill(db, bill)

    assert warnings == []


def test_untagged_lines_never_warn(db, purchase_ledger):
    _confirmed_budget(db, purchase_ledger, "10.00", purchase_ledger["project_one"].id)

    bill = _draft_bill(
        db,
        purchase_ledger,
        [(purchase_ledger["purchase_expense"], Decimal("99999.00"), None)],
    )
    _, warnings = purchase_service.confirm_vendor_bill(db, bill)

    assert warnings == []
