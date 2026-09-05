"""Budget lifecycle and achievement (SPEC.md §7.9, §10.7).

Achievement is computed here, live, on every read. It is never stored.

Storing it would mean recalculating whenever an invoice is confirmed, a bill is
confirmed, a document is cancelled, an analytic tag is changed, or a budget
period is edited — five invalidation paths, any one of which can be missed,
each leaving a number that looks authoritative and is wrong. Computing on read
has one code path and cannot drift (§7.9.1).

``compute_achievement`` is the ONLY place the analytic-sum query lives. The
vendor bill confirmation flow calls it for its over-budget warning rather than
rolling its own version, so the warning and the budget screen can never
disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import BudgetLineType, BudgetState, DocumentState
from app.core.errors import AppError
from app.models.budget import Budget, BudgetLine
from app.models.purchase import VendorBill, VendorBillLine
from app.models.sales import CustomerInvoice, CustomerInvoiceLine

ZERO = Decimal("0.00")

# States in which achievement figures are meaningful. A draft budget has not
# been committed to, so measuring against it says nothing (§10.7).
ACHIEVEMENT_VISIBLE_STATES = (BudgetState.CONFIRMED, BudgetState.REVISED)


@dataclass(frozen=True)
class Achievement:
    """The three derived figures the mockup shows against a budget line."""

    achieved_amount: Decimal
    achieved_percent: Decimal
    # committed - achieved. Goes NEGATIVE when over budget, deliberately:
    # over-budget is a real state and must be representable, not clamped.
    amount_to_achieve: Decimal


def compute_achievement(db: Session, line: BudgetLine) -> Achievement:
    """Sum the confirmed documents this budget line's analytic tag earned/spent.

    Income lines read customer invoice lines; expense lines read vendor bill
    lines. They never cross: per the mockup, invoice lines map to Income and
    bill lines map to Expense, so a bill contributes nothing to an income line
    even when it carries the same analytic tag (§10.7).
    """
    budget = line.budget
    achieved = compute_achieved_amount(
        db,
        analytic_account_id=line.analytic_account_id,
        line_type=line.line_type,
        start_date=budget.start_date,
        end_date=budget.end_date,
    )

    committed = line.committed_amount or ZERO
    if committed == ZERO:
        # Guarded even though a CHECK constraint forbids committed_amount = 0 —
        # a constraint protects the table, not a future caller of this function.
        percent = ZERO
    else:
        percent = (achieved / committed * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return Achievement(
        achieved_amount=achieved,
        achieved_percent=percent,
        amount_to_achieve=committed - achieved,
    )


def compute_achieved_amount(
    db: Session,
    *,
    analytic_account_id: int,
    line_type: BudgetLineType,
    start_date: date,
    end_date: date,
) -> Decimal:
    """The raw sum behind achievement. One indexed aggregate, no Python loop.

    Three filters do the work, and each maps to a §10.7 scenario:
      * document state = 'confirmed'  -> drafts are excluded
      * document date within period   -> documents outside it contribute 0.00
      * analytic_account_id matches   -> untagged lines (NULL) never match
    """
    if line_type is BudgetLineType.EXPENSE:
        stmt = (
            select(func.coalesce(func.sum(VendorBillLine.line_total), ZERO))
            .join(VendorBill, VendorBill.id == VendorBillLine.vendor_bill_id)
            .where(
                VendorBillLine.analytic_account_id == analytic_account_id,
                VendorBill.state == "confirmed",
                VendorBill.bill_date >= start_date,
                VendorBill.bill_date <= end_date,
            )
        )
    else:
        stmt = (
            select(func.coalesce(func.sum(CustomerInvoiceLine.line_total), ZERO))
            .select_from(CustomerInvoiceLine)
            .join(
                CustomerInvoice,
                CustomerInvoice.id == CustomerInvoiceLine.customer_invoice_id,
            )
            .where(
                CustomerInvoiceLine.analytic_account_id == analytic_account_id,
                CustomerInvoice.state == DocumentState.CONFIRMED,
                CustomerInvoice.invoice_date >= start_date,
                CustomerInvoice.invoice_date <= end_date,
            )
        )

    return Decimal(db.execute(stmt).scalar_one() or ZERO)


def achievement_or_none(db: Session, line: BudgetLine) -> Achievement | None:
    """Achievement, but only once the budget is committed to (§7.9)."""
    if line.budget.state not in ACHIEVEMENT_VISIBLE_STATES:
        return None
    return compute_achievement(db, line)


def list_source_documents(db: Session, line: BudgetLine) -> list[dict]:
    """The documents behind one line's achieved amount.

    Mockup: clicking the Achieved Amount opens the list of invoices/bills
    sharing this analytic within the budget period. The contributing amounts
    sum to achieved_amount by construction — same filters, no aggregation.
    """
    budget = line.budget

    if line.line_type is BudgetLineType.EXPENSE:
        stmt = (
            select(
                VendorBill.number,
                VendorBill.bill_date.label("document_date"),
                VendorBill.vendor_id.label("partner_id"),
                VendorBillLine.line_total,
            )
            .join(VendorBill, VendorBill.id == VendorBillLine.vendor_bill_id)
            .where(
                VendorBillLine.analytic_account_id == line.analytic_account_id,
                VendorBill.state == "confirmed",
                VendorBill.bill_date >= budget.start_date,
                VendorBill.bill_date <= budget.end_date,
            )
            .order_by(VendorBill.bill_date)
        )
        document_type = "vendor_bill"
    else:
        stmt = (
            select(
                CustomerInvoice.number,
                CustomerInvoice.invoice_date.label("document_date"),
                CustomerInvoice.customer_id.label("partner_id"),
                CustomerInvoiceLine.line_total,
            )
            .select_from(CustomerInvoiceLine)
            .join(
                CustomerInvoice,
                CustomerInvoice.id == CustomerInvoiceLine.customer_invoice_id,
            )
            .where(
                CustomerInvoiceLine.analytic_account_id == line.analytic_account_id,
                CustomerInvoice.state == DocumentState.CONFIRMED,
                CustomerInvoice.invoice_date >= budget.start_date,
                CustomerInvoice.invoice_date <= budget.end_date,
            )
            .order_by(CustomerInvoice.invoice_date)
        )
        document_type = "customer_invoice"

    return [
        {
            "document_type": document_type,
            "number": row.number,
            "date": row.document_date,
            "partner_id": row.partner_id,
            "line_total": row.line_total,
        }
        for row in db.execute(stmt).all()
    ]


# --- lifecycle --------------------------------------------------------------


def confirm_budget(db: Session, budget: Budget) -> Budget:
    """Draft -> confirmed. Achievement figures become visible from here on."""
    if budget.state is not BudgetState.DRAFT:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            f"Only a draft budget can be confirmed; this one is {budget.state.value}.",
        )

    budget.state = BudgetState.CONFIRMED
    db.flush()
    return budget


def revise_budget(db: Session, budget: Budget) -> Budget:
    """Create a linked draft copy and mark the original as revised (§10.7).

    A confirmed budget is never edited in place — the committed figures are a
    record of what was agreed. Revising preserves that record and supersedes
    it, with links in both directions so the UI can navigate either way.
    """
    if budget.state is BudgetState.REVISED or budget.revised_with_id is not None:
        raise AppError(409, "ALREADY_REVISED", "This budget has already been revised.")
    if budget.state is not BudgetState.CONFIRMED:
        raise AppError(
            409,
            "BUDGET_NOT_CONFIRMED",
            "Only a confirmed budget can be revised.",
        )

    revision = Budget(
        name=f"{budget.name} Revised",
        start_date=budget.start_date,
        end_date=budget.end_date,
        responsible_id=budget.responsible_id,
        state=BudgetState.DRAFT,
        revision_of_id=budget.id,
    )
    for line in budget.lines:
        revision.lines.append(
            BudgetLine(
                analytic_account_id=line.analytic_account_id,
                line_type=line.line_type,
                committed_amount=line.committed_amount,
                sequence=line.sequence,
            )
        )

    db.add(revision)
    # Flush so the revision has an id before the original links forward to it.
    db.flush()

    budget.state = BudgetState.REVISED
    budget.revised_with_id = revision.id
    db.flush()

    return revision


def cancel_budget(db: Session, budget: Budget) -> Budget:
    """Cancel a budget. A revised budget is history and stays as it is."""
    if budget.state is BudgetState.REVISED:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            "A revised budget cannot be cancelled; cancel its revision instead.",
        )

    budget.state = BudgetState.CANCELLED
    db.flush()
    return budget


def assert_editable(budget: Budget) -> None:
    """A confirmed budget cannot be edited — revise it instead (§10.7)."""
    if budget.state is not BudgetState.DRAFT:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            "Only a draft budget can be edited. Revise the budget instead.",
        )
