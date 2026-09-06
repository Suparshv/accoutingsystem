"""Purchase cycle business logic (SPEC.md §8.2, §10.5, §10.8).

The important function here is ``confirm_vendor_bill``. It is the first place
in the system where a document and a journal entry must become true together,
and the whole transaction discipline of the project shows up in it:

  * the posting engine flushes, it never commits (R3);
  * this service issues exactly ONE commit, after both the bill's state change
    and its journal entry are in the session;
  * nothing catches the engine's exceptions, so a failed post aborts the whole
    request and the bill stays draft with no orphan entry (§10.5 atomicity).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    AccountType,
    BudgetLineType,
    BudgetState,
    DocumentState,
    JournalType,
)
from app.core.errors import AppError
from app.models.account import Account, Journal
from app.models.budget import Budget, BudgetLine
from app.models.purchase import PurchaseOrder, VendorBill, VendorBillLine
from app.services import budgets as budgets_service
from app.services.accounting import LineInput, post_journal_entry
from app.services.sequences import _lock_sequence_row

ZERO = Decimal("0.00")
SEQUENCE_STEP = 10

PURCHASE_ORDER_SEQUENCE = "purchase_order"
PURCHASE_ORDER_PREFIX = "P"
VENDOR_BILL_SEQUENCE = "vendor_bill"
VENDOR_BILL_PREFIX = "BILL"


# --- numbering --------------------------------------------------------------


def next_purchase_order_number(db: Session) -> str:
    """P00001 — prefix plus five digits, no year component (§12.4).

    services/sequences.py owns the row-lock, but its formatter only produces
    the PREFIX/YYYY/NNNN shape, and this task may not modify that module. So
    this reuses its locking helper — the concurrency-critical part — and does
    only the formatting here. When sequences.py can be touched, this belongs
    there as next_purchase_order_number(); see the summary.
    """
    today = date.today()
    row = _lock_sequence_row(
        db,
        name=PURCHASE_ORDER_SEQUENCE,
        prefix=PURCHASE_ORDER_PREFIX,
        year=today.year,
    )
    row.last_number += 1
    db.flush()
    return f"{PURCHASE_ORDER_PREFIX}{row.last_number:05d}"


def next_vendor_bill_number(db: Session) -> str:
    """BILL/2026/0001 — resets yearly, per §12.4."""
    today = date.today()
    row = _lock_sequence_row(
        db, name=VENDOR_BILL_SEQUENCE, prefix=VENDOR_BILL_PREFIX, year=today.year
    )
    if row.year != today.year:
        row.year = today.year
        row.last_number = 0
    row.last_number += 1
    db.flush()
    return f"{VENDOR_BILL_PREFIX}/{row.year}/{row.last_number:04d}"


# --- line maths -------------------------------------------------------------


def compute_line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    """quantity x unit_price, in Decimal, server-side, always.

    Any line_total the client sent is discarded before this is called (R6).

    Rounded here rather than left to the NUMERIC(14,2) column, and rounded the
    same way as services/sales.py::compute_line_total — the two cycles used to
    settle a half-paise tie differently, and the forms now show this product
    live while you type (lib/money.ts::multiplyMinorUnits), so a disagreement
    would show up as a figure that changes on save.
    """
    return (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def recompute_total(lines) -> Decimal:
    """A document's total is the sum of its lines. Never client-supplied."""
    return sum((line.line_total for line in lines), ZERO)


# --- purchase orders --------------------------------------------------------


def confirm_purchase_order(db: Session, order: PurchaseOrder) -> PurchaseOrder:
    """Draft -> confirmed. Deliberately produces NO journal entry.

    A purchase order is a commitment, not a financial event. Nothing has been
    bought yet, so nothing hits the ledger (§10.5). The bill is where money
    becomes real.
    """
    if order.state is not DocumentState.DRAFT:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            f"Only a draft purchase order can be confirmed; "
            f"this one is {order.state.value}.",
        )

    order.state = DocumentState.CONFIRMED
    db.flush()
    return order


def cancel_purchase_order(db: Session, order: PurchaseOrder) -> PurchaseOrder:
    """A purchase order itself has no ledger effect in any state, but a
    linked vendor bill might — so cancelling the order must resolve that
    link rather than ignore it (mirrors services.sales.cancel_sales_order
    exactly):

    - no linked bill, or the bill is already cancelled: cancel the PO,
      nothing else to do.
    - the bill is still draft (journal_entry_id is null — no ledger effect
      posted yet): cascade-cancel it in the same transaction. Safe, since
      nothing has been posted for it.
    - the bill is confirmed (its journal entry is posted and immutable,
      R4): refuse. Undoing a posted entry needs a reversal (the P2 path,
      not built) — silently cancelling the PO here would leave the ledger
      asserting an expense/liability for a purchase the business now says
      never happened.

    Raises:
        AppError(409, INVALID_STATE_TRANSITION): a confirmed bill exists for
            this order.
    """
    bill = db.execute(
        select(VendorBill).where(VendorBill.source_po_id == order.id)
    ).scalar_one_or_none()

    if bill is not None:
        if bill.state == DocumentState.CONFIRMED:
            raise AppError(
                409,
                "INVALID_STATE_TRANSITION",
                "Cannot cancel: bill already confirmed and posted. Reverse "
                "the bill's journal entry instead.",
            )
        if bill.state == DocumentState.DRAFT:
            cancel_vendor_bill(db, bill)

    order.state = DocumentState.CANCELLED
    db.flush()
    return order


def create_bill_from_po(
    db: Session, order: PurchaseOrder, *, bill_date: date | None = None
) -> VendorBill:
    """Copy a confirmed PO into a fresh draft bill (§9, §10.5).

    Vendor, quantities, prices and analytic tags come across unchanged. The
    ledger account does not exist on a PO line, so each bill line is prefilled
    with Purchase Expense A/c, which the user may override before confirming.

    ``bill_date`` defaults to today, matching real usage (you convert a PO to
    a bill on the day you receive it, regardless of when it was placed).
    seed.py passes an explicit historical date so demo bills land inside the
    Jan-Mar 2026 window its budgets measure achievement against.
    """
    if order.state is not DocumentState.CONFIRMED:
        raise AppError(
            409,
            "PO_NOT_CONFIRMED",
            "Only a confirmed purchase order can be billed.",
        )

    existing = db.execute(
        select(VendorBill).where(VendorBill.source_po_id == order.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            409,
            "BILL_ALREADY_EXISTS",
            f"Purchase order {order.number} has already been billed "
            f"as {existing.number}.",
            {"vendor_bill_id": existing.id, "number": existing.number},
        )

    expense_account = _default_purchase_account(db)

    bill = VendorBill(
        number=next_vendor_bill_number(db),
        vendor_id=order.vendor_id,
        bill_date=bill_date or date.today(),
        state=DocumentState.DRAFT,
        source_po_id=order.id,
    )
    for line in order.lines:
        bill.lines.append(
            VendorBillLine(
                product_id=line.product_id,
                account_id=expense_account.id,
                analytic_account_id=line.analytic_account_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=compute_line_total(line.quantity, line.unit_price),
                sequence=line.sequence,
            )
        )
    bill.total_amount = recompute_total(bill.lines)

    db.add(bill)
    db.flush()
    return bill


# --- vendor bills -----------------------------------------------------------


def confirm_vendor_bill(db: Session, bill: VendorBill) -> tuple[VendorBill, list[dict]]:
    """★ Confirm a bill and post its journal entry, atomically (§8.2, §10.5).

    Returns the bill and any non-blocking warnings.

    The debit side is built by grouping the bill's lines by account_id and
    summing within each group — one ledger line per distinct account, not one
    per document line. Most bills use Purchase Expense A/c throughout and
    produce a single debit line; a bill mixing goods and freight produces two.
    Grouping handles both without a special case (§8.2).

    The credit side is exactly one line to Creditors for the bill total, with
    the vendor attached, because that is what the business now owes them.
    """
    if bill.state is DocumentState.CONFIRMED:
        raise AppError(
            409, "ALREADY_CONFIRMED", "This bill has already been confirmed."
        )
    if bill.state is DocumentState.CANCELLED:
        raise AppError(
            409, "INVALID_STATE_TRANSITION", "A cancelled bill cannot be confirmed."
        )
    if not bill.lines:
        raise AppError(422, "NO_LINES", "A bill needs at least one line to confirm.")

    # A cancelled PO can leave behind a still-draft bill (cancel_purchase_order
    # only cascades when the bill is draft AND blocks when it's confirmed —
    # this closes the remaining gap: nothing previously stopped that orphaned
    # draft bill from later being confirmed and posted for a purchase the
    # business has already said never happened).
    if bill.source_po_id is not None:
        source_po = db.get(PurchaseOrder, bill.source_po_id)
        if source_po is not None and source_po.state == DocumentState.CANCELLED:
            raise AppError(
                409,
                "INVALID_STATE_TRANSITION",
                "Cannot confirm: source purchase order has been cancelled.",
            )

    # Computed BEFORE the state change, so the bill being confirmed does not
    # count itself as already-achieved (§10.8 names the remaining amount
    # excluding this document).
    warnings = _budget_warnings(db, bill)

    journal = _purchase_journal(db)
    creditors = _creditors_account(db)

    grouped: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for line in bill.lines:
        grouped[line.account_id] += line.line_total

    total = recompute_total(bill.lines)
    bill.total_amount = total

    lines = [
        LineInput(
            account_id=account_id,
            debit=amount,
            partner_id=bill.vendor_id,
            label=bill.number,
        )
        for account_id, amount in grouped.items()
    ]
    lines.append(
        LineInput(
            account_id=creditors.id,
            credit=total,
            partner_id=bill.vendor_id,
            label=bill.number,
        )
    )

    # Not wrapped in try/except on purpose. If the engine rejects this entry,
    # the exception propagates, the router never reaches its commit, and the
    # request's transaction rolls back whole — bill still draft, no entry, no
    # lines (§8.3, §10.5).
    entry = post_journal_entry(
        db,
        entry_date=bill.bill_date,
        journal_id=journal.id,
        lines=lines,
        partner_id=bill.vendor_id,
        source_type="vendor_bill",
        source_id=bill.id,
        # The entry reuses the bill's number, so the two are obviously the
        # same event when read in the Journal Entries list (§12.4).
        number=bill.number,
    )

    bill.state = DocumentState.CONFIRMED
    bill.journal_entry_id = entry.id
    db.flush()

    return bill, warnings


def cancel_vendor_bill(db: Session, bill: VendorBill) -> VendorBill:
    """Only a draft bill may be cancelled.

    A confirmed bill has a posted journal entry, and posted entries are
    immutable (R4). Undoing one means posting a reversal, which is the P2 path.
    """
    if bill.state is DocumentState.CONFIRMED:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            "A confirmed bill cannot be cancelled; its journal entry is posted "
            "and immutable. Reverse the entry instead.",
        )

    bill.state = DocumentState.CANCELLED
    db.flush()
    return bill


# --- budget warnings (§10.8) ------------------------------------------------


def _budget_warnings(db: Session, bill: VendorBill) -> list[dict]:
    """EXCEEDS_BUDGET warnings for this bill's analytic tags.

    Non-blocking by design: the business may legitimately overspend, so the
    system informs and gets out of the way. A warning must never leave a
    document confirmed but unposted (§10.8).

    The achieved figure comes from services/budgets.py::compute_achievement —
    the same function the budget screen calls. Duplicating that query here is
    how the warning and the budget report start disagreeing.
    """
    contributions: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for line in bill.lines:
        # Untagged lines belong to no budget and never warn.
        if line.analytic_account_id is not None:
            contributions[line.analytic_account_id] += line.line_total

    if not contributions:
        return []

    budget_lines = (
        db.execute(
            select(BudgetLine)
            .join(Budget, Budget.id == BudgetLine.budget_id)
            .where(
                BudgetLine.analytic_account_id.in_(contributions.keys()),
                BudgetLine.line_type == BudgetLineType.EXPENSE,
                Budget.state.in_([BudgetState.CONFIRMED, BudgetState.REVISED]),
                Budget.start_date <= bill.bill_date,
                Budget.end_date >= bill.bill_date,
            )
        )
        .scalars()
        .all()
    )

    warnings = []
    for budget_line in budget_lines:
        achievement = budgets_service.compute_achievement(db, budget_line)
        remaining = achievement.amount_to_achieve
        contribution = contributions[budget_line.analytic_account_id]

        if contribution > remaining:
            warnings.append(
                {
                    "code": "EXCEEDS_BUDGET",
                    "message": (
                        "Exceeds Approved Budget — the entered amount is higher "
                        "than the remaining budget amount for this budget line. "
                        "Consider adjusting the value or revise the budget."
                    ),
                    "details": {
                        "budget_id": budget_line.budget_id,
                        "budget_line_id": budget_line.id,
                        "analytic_account_id": budget_line.analytic_account_id,
                        "remaining_amount": f"{remaining:.2f}",
                        "attempted_amount": f"{contribution:.2f}",
                    },
                }
            )

    return warnings


# --- lookups ----------------------------------------------------------------


def _purchase_journal(db: Session) -> Journal:
    journal = (
        db.execute(select(Journal).where(Journal.journal_type == JournalType.PURCHASE))
        .scalars()
        .first()
    )
    if journal is None:
        raise AppError(
            422,
            "JOURNAL_NOT_FOUND",
            "No Purchase journal exists. Seed the chart of accounts first.",
        )
    return journal


def _creditors_account(db: Session) -> Account:
    """Creditors A/c — what the business owes its vendors (account_type=liability)."""
    account = (
        db.execute(
            select(Account)
            .where(
                Account.account_type == AccountType.LIABILITY,
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
            "No Creditors (liability) account exists. Seed the chart of accounts first.",
        )
    return account


def _default_purchase_account(db: Session) -> Account:
    """Purchase Expense A/c — the prefill for a bill line's ledger account."""
    account = (
        db.execute(
            select(Account)
            .where(
                Account.account_type == AccountType.EXPENSE,
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
            "No Purchase Expense account exists. Seed the chart of accounts first.",
        )
    return account
