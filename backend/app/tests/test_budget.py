"""Budget tests — SPEC.md §10.7.

Achievement is the interesting half. Every test here proves a filter: state,
period, analytic tag, or line type. Each one is a way the number could be
silently wrong if it were stored and an invalidation path were missed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core.enums import BudgetLineType, BudgetState, DocumentState
from app.core.errors import AppError
from app.models.budget import Budget, BudgetLine
from app.models.purchase import VendorBill, VendorBillLine
from app.models.sales import CustomerInvoice, CustomerInvoiceLine
from app.services import budgets as budgets_service
from app.services import purchase as purchase_service

JANUARY_START = date(2026, 1, 1)
JANUARY_END = date(2026, 1, 31)


def _budget(
    db,
    seed,
    *,
    committed: str,
    line_type: BudgetLineType = BudgetLineType.EXPENSE,
    state: BudgetState = BudgetState.CONFIRMED,
    analytic_id: int | None = None,
) -> Budget:
    budget = Budget(
        name="January 2026",
        start_date=JANUARY_START,
        end_date=JANUARY_END,
        responsible_id=seed["partner_id"],
        state=state,
    )
    budget.lines.append(
        BudgetLine(
            analytic_account_id=analytic_id or seed["project_one"].id,
            line_type=line_type,
            committed_amount=Decimal(committed),
            sequence=10,
        )
    )
    db.add(budget)
    db.flush()
    return budget


def _bill(
    db, seed, *, amount: str, when: date, analytic_id: int | None, confirm: bool = True
) -> VendorBill:
    bill = VendorBill(
        number=purchase_service.next_vendor_bill_number(db),
        vendor_id=seed["partner_id"],
        bill_date=when,
        state=DocumentState.DRAFT,
    )
    bill.lines.append(
        VendorBillLine(
            product_id=seed["table"].id,
            account_id=seed["purchase_expense"].id,
            analytic_account_id=analytic_id,
            quantity=Decimal("1.00"),
            unit_price=Decimal(amount),
            line_total=Decimal(amount),
            sequence=10,
        )
    )
    bill.total_amount = Decimal(amount)
    db.add(bill)
    db.flush()

    if confirm:
        bill, _ = purchase_service.confirm_vendor_bill(db, bill)
    return bill


def _invoice(
    db,
    seed,
    *,
    amount: str,
    when: date,
    analytic_id,
    state: DocumentState = DocumentState.CONFIRMED,
) -> CustomerInvoice:
    """Build a real CustomerInvoice + CustomerInvoiceLine (§7.7), mirroring
    _bill()'s pattern now that models/sales.py has merged in — the raw-SQL
    stub this used to insert against has retired itself as designed.
    """
    invoice = CustomerInvoice(
        number=f"INV/2026/{when.day:04d}",
        customer_id=seed["partner_id"],
        invoice_date=when,
        state=state,
    )
    invoice.lines.append(
        CustomerInvoiceLine(
            product_id=seed["table"].id,
            account_id=seed["sales_income"].id,
            analytic_account_id=analytic_id,
            quantity=Decimal("1.00"),
            unit_price=Decimal(amount),
            line_total=Decimal(amount),
            sequence=10,
        )
    )
    invoice.total_amount = Decimal(amount)
    db.add(invoice)
    db.flush()
    return invoice


# --- ★ Scenario: expense achievement sums vendor bill lines ----------------


def test_expense_achievement_sums_confirmed_bills_in_the_period(db, purchase_ledger):
    budget = _budget(db, purchase_ledger, committed="200000.00")
    _bill(
        db,
        purchase_ledger,
        amount="10000.00",
        when=date(2026, 1, 15),
        analytic_id=purchase_ledger["project_one"].id,
    )

    achievement = budgets_service.compute_achievement(db, budget.lines[0])

    assert achievement.achieved_amount == Decimal("10000.00")
    assert achievement.achieved_percent == Decimal("5.00")
    assert achievement.amount_to_achieve == Decimal("190000.00")


# --- ★ Scenario: income achievement sums customer invoice lines ------------


def test_income_achievement_sums_confirmed_invoices_in_the_period(db, purchase_ledger):
    budget = _budget(
        db, purchase_ledger, committed="500000.00", line_type=BudgetLineType.INCOME
    )
    _invoice(
        db,
        purchase_ledger,
        amount="21000.00",
        when=date(2026, 1, 20),
        analytic_id=purchase_ledger["project_one"].id,
    )

    achievement = budgets_service.compute_achievement(db, budget.lines[0])

    assert achievement.achieved_amount == Decimal("21000.00")
    assert achievement.achieved_percent == Decimal("4.20")


# --- ★ Scenario: income lines ignore bills, expense lines ignore invoices ---


def test_an_income_line_ignores_vendor_bills(db, purchase_ledger):
    """Invoice lines map to Income; bill lines map to Expense. No crossing."""
    budget = _budget(
        db, purchase_ledger, committed="500000.00", line_type=BudgetLineType.INCOME
    )
    _bill(
        db,
        purchase_ledger,
        amount="50000.00",
        when=date(2026, 1, 15),
        analytic_id=purchase_ledger["project_one"].id,
    )

    achievement = budgets_service.compute_achievement(db, budget.lines[0])

    assert achievement.achieved_amount == Decimal("0.00")


def test_an_expense_line_ignores_customer_invoices(db, purchase_ledger):
    budget = _budget(db, purchase_ledger, committed="200000.00")
    _invoice(
        db,
        purchase_ledger,
        amount="50000.00",
        when=date(2026, 1, 20),
        analytic_id=purchase_ledger["project_one"].id,
    )

    achievement = budgets_service.compute_achievement(db, budget.lines[0])

    assert achievement.achieved_amount == Decimal("0.00")


# --- Scenario: the three exclusion filters ---------------------------------


def test_documents_outside_the_period_are_excluded(db, purchase_ledger):
    budget = _budget(db, purchase_ledger, committed="200000.00")
    _bill(
        db,
        purchase_ledger,
        amount="10000.00",
        when=date(2026, 2, 5),
        analytic_id=purchase_ledger["project_one"].id,
    )

    assert budgets_service.compute_achievement(
        db, budget.lines[0]
    ).achieved_amount == Decimal("0.00")


def test_draft_documents_are_excluded(db, purchase_ledger):
    """A draft is not yet a commitment (§10.7)."""
    budget = _budget(db, purchase_ledger, committed="200000.00")
    _bill(
        db,
        purchase_ledger,
        amount="50000.00",
        when=date(2026, 1, 15),
        analytic_id=purchase_ledger["project_one"].id,
        confirm=False,
    )

    assert budgets_service.compute_achievement(
        db, budget.lines[0]
    ).achieved_amount == Decimal("0.00")


def test_untagged_document_lines_contribute_nothing(db, purchase_ledger):
    budget = _budget(db, purchase_ledger, committed="200000.00")
    _bill(
        db,
        purchase_ledger,
        amount="50000.00",
        when=date(2026, 1, 15),
        analytic_id=None,
    )

    assert budgets_service.compute_achievement(
        db, budget.lines[0]
    ).achieved_amount == Decimal("0.00")


def test_a_different_analytic_contributes_nothing(db, purchase_ledger):
    budget = _budget(db, purchase_ledger, committed="200000.00")
    _bill(
        db,
        purchase_ledger,
        amount="50000.00",
        when=date(2026, 1, 15),
        analytic_id=purchase_ledger["project_two"].id,
    )

    assert budgets_service.compute_achievement(
        db, budget.lines[0]
    ).achieved_amount == Decimal("0.00")


# --- Scenario: over 100 percent, and division by zero ----------------------


def test_achievement_may_exceed_one_hundred_percent(db, purchase_ledger):
    """Over-budget is a real state and must be representable, not clamped."""
    budget = _budget(db, purchase_ledger, committed="10000.00")
    _bill(
        db,
        purchase_ledger,
        amount="12000.00",
        when=date(2026, 1, 15),
        analytic_id=purchase_ledger["project_one"].id,
    )

    achievement = budgets_service.compute_achievement(db, budget.lines[0])

    assert achievement.achieved_amount == Decimal("12000.00")
    assert achievement.achieved_percent == Decimal("120.00")
    assert achievement.amount_to_achieve == Decimal("-2000.00")


def test_division_by_zero_is_impossible(db, purchase_ledger):
    """Guarded even though a CHECK constraint forbids committed_amount = 0."""
    budget = _budget(db, purchase_ledger, committed="10000.00")
    line = budget.lines[0]
    # Bypass the constraint in Python only — never written to the database.
    line.committed_amount = Decimal("0.00")

    achievement = budgets_service.compute_achievement(db, line)

    assert achievement.achieved_percent == Decimal("0.00")


# --- Scenario: achievement is hidden while draft ---------------------------


def test_achievement_is_null_on_a_draft_budget(db, purchase_ledger):
    budget = _budget(
        db, purchase_ledger, committed="200000.00", state=BudgetState.DRAFT
    )

    assert budgets_service.achievement_or_none(db, budget.lines[0]) is None


def test_achievement_is_visible_once_confirmed(db, purchase_ledger):
    budget = _budget(
        db, purchase_ledger, committed="200000.00", state=BudgetState.DRAFT
    )
    budgets_service.confirm_budget(db, budget)

    assert budgets_service.achievement_or_none(db, budget.lines[0]) is not None


# --- ★ Scenario: revising creates a linked copy ----------------------------


def test_revising_creates_a_linked_draft_copy(db, purchase_ledger):
    """★ Both directional links, original becomes 'revised' (§10.7)."""
    original = _budget(db, purchase_ledger, committed="200000.00")
    original_id = original.id

    revision = budgets_service.revise_budget(db, original)

    assert revision.name == "January 2026 Revised"
    assert revision.state is BudgetState.DRAFT
    assert revision.start_date == original.start_date
    assert revision.end_date == original.end_date
    assert revision.responsible_id == original.responsible_id

    # Same lines, copied.
    assert len(revision.lines) == 1
    assert revision.lines[0].committed_amount == Decimal("200000.00")
    assert (
        revision.lines[0].analytic_account_id == original.lines[0].analytic_account_id
    )

    # Doubly-linked: the revision points back, the original points forward.
    assert revision.revision_of_id == original_id
    assert original.revised_with_id == revision.id
    assert original.state is BudgetState.REVISED

    # Both remain visible.
    assert db.get(Budget, original_id) is not None
    assert db.get(Budget, revision.id) is not None


def test_only_a_confirmed_budget_can_be_revised(db, purchase_ledger):
    budget = _budget(db, purchase_ledger, committed="1000.00", state=BudgetState.DRAFT)

    with pytest.raises(AppError) as excinfo:
        budgets_service.revise_budget(db, budget)

    assert excinfo.value.code == "BUDGET_NOT_CONFIRMED"
    assert excinfo.value.status_code == 409


def test_a_budget_can_be_revised_only_once(db, purchase_ledger):
    budget = _budget(db, purchase_ledger, committed="1000.00")
    budgets_service.revise_budget(db, budget)

    with pytest.raises(AppError) as excinfo:
        budgets_service.revise_budget(db, budget)

    assert excinfo.value.code == "ALREADY_REVISED"
    assert excinfo.value.status_code == 409


def test_a_confirmed_budget_cannot_be_edited(db, purchase_ledger):
    budget = _budget(db, purchase_ledger, committed="1000.00")

    with pytest.raises(AppError) as excinfo:
        budgets_service.assert_editable(budget)

    assert excinfo.value.status_code == 409
    assert "revise" in excinfo.value.message.lower()


# --- Scenario: drilling into an achieved amount ----------------------------


def test_source_documents_sum_to_the_achieved_amount(db, purchase_ledger):
    budget = _budget(db, purchase_ledger, committed="200000.00")
    analytic_id = purchase_ledger["project_one"].id
    _bill(
        db,
        purchase_ledger,
        amount="6000.00",
        when=date(2026, 1, 10),
        analytic_id=analytic_id,
    )
    _bill(
        db,
        purchase_ledger,
        amount="4000.00",
        when=date(2026, 1, 20),
        analytic_id=analytic_id,
    )

    rows = budgets_service.list_source_documents(db, budget.lines[0])
    achievement = budgets_service.compute_achievement(db, budget.lines[0])

    assert len(rows) == 2
    assert sum(r["line_total"] for r in rows) == achievement.achieved_amount
    assert all(r["document_type"] == "vendor_bill" for r in rows)
