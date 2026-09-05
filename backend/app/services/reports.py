"""Financial reports, derived entirely from the ledger (SPEC.md §6.4, §10.9).

No report reads a stored balance, an invoice total, or a bill total — every
figure here is an aggregate over journal_entry_lines, scoped to posted
entries. That is the whole point of the architecture (AGENTS.md §0): nothing
stores a balance, every report is an aggregation over journal entries.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AccountType, JournalEntryState
from app.core.errors import AppError
from app.models.account import Account
from app.models.journal_entry import JournalEntry, JournalEntryLine

ZERO = Decimal("0.00")

# The balance-sheet section labels, matching the exact seeded chart of
# accounts every §10 scenario assumes (§10.1 background): one account per
# type. If a business ever adds a second account of the same type, this
# still produces a correct GROUP BY total for that type — it just shares one
# label across both accounts, which is the same simplification the mockup
# itself makes.
BALANCE_SHEET_ASSET_TYPES: dict[AccountType, str] = {
    AccountType.BANK: "Bank",
    AccountType.CASH: "Cash",
    AccountType.ASSET: "Debtors",
}
BALANCE_SHEET_LIABILITY_TYPES: dict[AccountType, str] = {
    AccountType.CAPITAL: "Capital",
    AccountType.LIABILITY: "Creditors",
}


def _aggregate_by_account_type(
    db: Session, *, start_date: date, end_date: date
) -> dict[AccountType, tuple[Decimal, Decimal]]:
    """SUM(debit), SUM(credit) grouped by account_type, over posted lines
    only (§6.4 scope), within an inclusive date range. One query, not one
    per account_type."""
    stmt = (
        select(
            Account.account_type,
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
        .select_from(JournalEntryLine)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .where(JournalEntry.state == JournalEntryState.POSTED)
        .where(JournalEntry.entry_date >= start_date)
        .where(JournalEntry.entry_date <= end_date)
        .group_by(Account.account_type)
    )

    rows = db.execute(stmt).all()
    return {row[0]: (Decimal(row[1]), Decimal(row[2])) for row in rows}


def _last_day_of_month(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def resolve_period(
    *,
    year: int | None = None,
    month: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[date, date]:
    """Turn the /reports/profit-and-loss query params into one inclusive
    date range (§9).

    Precedence, most specific first:
      1. start_date + end_date — an explicit range, used as given.
      2. month (+ optional year, defaulting to the current year) — that
         single calendar month.
      3. year alone (or nothing) — the whole fiscal year, defaulting to the
         current year. This is the original, backward-compatible behaviour.
    """
    if start_date is not None or end_date is not None:
        if start_date is None or end_date is None:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "start_date and end_date must both be supplied together.",
            )
        if end_date < start_date:
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "end_date must not be before start_date.",
            )
        return start_date, end_date

    resolved_year = year or date.today().year

    if month is not None:
        if not 1 <= month <= 12:
            raise AppError(422, "VALIDATION_ERROR", "month must be between 1 and 12.")
        return date(resolved_year, month, 1), _last_day_of_month(resolved_year, month)

    return date(resolved_year, 1, 1), date(resolved_year, 12, 31)


def profit_and_loss(
    db: Session,
    *,
    year: int | None = None,
    month: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Income and expenses for a period (§6.4, §9).

    Defaults to the full fiscal year (`year`, itself defaulting to the
    current year) for backward compatibility. Pass `month` (optionally with
    `year`) for one calendar month, or `start_date`/`end_date` together for
    an arbitrary range — see resolve_period() for the exact precedence.
    """
    period_start, period_end = resolve_period(
        year=year, month=month, start_date=start_date, end_date=end_date
    )
    totals = _aggregate_by_account_type(
        db, start_date=period_start, end_date=period_end
    )
    return _pnl_from_totals(totals)


def _pnl_from_totals(totals: dict[AccountType, tuple[Decimal, Decimal]]) -> dict:
    """The income/expenses/net_income shape, given totals already aggregated
    over whatever date range the caller wants (§6.4). Shared by
    profit_and_loss() and balance_sheet(), so the latter never re-queries
    the ledger just to get the net-income figure it already has the totals
    for.
    """
    income_debit, income_credit = totals.get(AccountType.INCOME, (ZERO, ZERO))
    income_from_sales = income_credit - income_debit
    total_income = income_from_sales

    expense_debit, expense_credit = totals.get(AccountType.EXPENSE, (ZERO, ZERO))
    purchase_expense = expense_debit - expense_credit

    other_debit, other_credit = totals.get(AccountType.OTHER_EXPENSE, (ZERO, ZERO))
    other_expense = other_debit - other_credit

    total_expenses = purchase_expense + other_expense
    net_income = total_income - total_expenses

    return {
        "income": {
            "income_from_sales": income_from_sales,
            "total_income": total_income,
        },
        "expenses": {
            "purchase_expense": purchase_expense,
            "other_expense": other_expense,
            "total_expenses": total_expenses,
        },
        "net_income": net_income,
    }


def balance_sheet(db: Session, *, year: int, as_of: date | None = None) -> dict:
    """Assets, liabilities and the balancing identity (§6.4, §10.9).

    IMPLEMENTATION REQUIREMENT (§10.9): includes a computed "Current Period
    Earnings" row on the liabilities/capital side, equal to the period's net
    income. Without it, total_assets and total_liabilities differ by exactly
    that period's profit or loss and the report never balances — this is the
    one piece of accounting the mockup does not spell out, and the detail
    this whole function exists to get right.
    """
    # Same calendar-year scope profit_and_loss's year mode uses, capped at
    # `as_of` when it falls inside the year (preserves the exact pre-existing
    # "this year, up to a cutoff" semantics now that the shared aggregate
    # takes a plain date range instead of a year+as_of pair).
    period_end = date(year, 12, 31)
    if as_of is not None and as_of < period_end:
        period_end = as_of
    totals = _aggregate_by_account_type(
        db, start_date=date(year, 1, 1), end_date=period_end
    )

    assets = []
    total_assets = ZERO
    for account_type, label in BALANCE_SHEET_ASSET_TYPES.items():
        debit, credit = totals.get(account_type, (ZERO, ZERO))
        balance = debit - credit
        assets.append(
            {"label": label, "account_type": account_type.value, "balance": balance}
        )
        total_assets += balance

    liabilities = []
    total_liabilities = ZERO
    for account_type, label in BALANCE_SHEET_LIABILITY_TYPES.items():
        debit, credit = totals.get(account_type, (ZERO, ZERO))
        balance = credit - debit
        liabilities.append(
            {"label": label, "account_type": account_type.value, "balance": balance}
        )
        total_liabilities += balance

    net_income = _pnl_from_totals(totals)["net_income"]
    liabilities.append(
        {
            "label": "Current Period Earnings",
            "account_type": AccountType.CAPITAL.value,
            "balance": net_income,
        }
    )
    total_liabilities += net_income

    return {
        "assets": assets,
        "liabilities": liabilities,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "is_balanced": total_assets == total_liabilities,
    }


def trial_balance(db: Session) -> dict:
    """Every account's debit/credit totals, plus the grand totals and the
    system-wide integrity check (§9, §10.9): this can only fail to balance
    if the posting engine's balance rule (P1/P6) was somehow violated.
    """
    stmt = (
        select(
            Account.code,
            Account.name,
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
        .select_from(JournalEntryLine)
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
        .join(Account, Account.id == JournalEntryLine.account_id)
        .where(JournalEntry.state == JournalEntryState.POSTED)
        .group_by(Account.code, Account.name)
        .order_by(Account.code)
    )
    rows = db.execute(stmt).all()

    result_rows = [
        {
            "account_code": code,
            "account_name": name,
            "total_debit": Decimal(debit),
            "total_credit": Decimal(credit),
        }
        for code, name, debit, credit in rows
    ]
    grand_total_debit = sum((r["total_debit"] for r in result_rows), ZERO)
    grand_total_credit = sum((r["total_credit"] for r in result_rows), ZERO)

    return {
        "rows": result_rows,
        "grand_total_debit": grand_total_debit,
        "grand_total_credit": grand_total_credit,
        "is_balanced": grand_total_debit == grand_total_credit,
    }
