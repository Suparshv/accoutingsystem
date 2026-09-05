"""Financial reports HTTP layer (SPEC.md §9 reports section)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.database import get_db
from app.models.user import User
from app.schemas.common import Page
from app.schemas.report import (
    BalanceSheetRead,
    BudgetSummaryRow,
    ProfitAndLossRead,
    TrialBalanceRead,
)
from app.services import budgets as budgets_service
from app.services import reports

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/balance-sheet", response_model=BalanceSheetRead)
def get_balance_sheet(
    year: int | None = Query(
        None, description="Fiscal year; defaults to the current year"
    ),
    as_of: date | None = Query(None, description="Cut-off date; defaults to unbounded"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> BalanceSheetRead:
    return BalanceSheetRead(
        **reports.balance_sheet(db, year=year or date.today().year, as_of=as_of)
    )


@router.get("/profit-and-loss", response_model=ProfitAndLossRead)
def get_profit_and_loss(
    year: int | None = Query(
        None,
        description=(
            "Fiscal year; defaults to the current year. Ignored if "
            "start_date/end_date are given."
        ),
    ),
    month: int | None = Query(
        None,
        ge=1,
        le=12,
        description=(
            "1-12; combined with year (defaulting to the current year) for a "
            "single calendar month's figures. Ignored if start_date/end_date "
            "are given."
        ),
    ),
    start_date: date | None = Query(
        None, description="Range start (inclusive); requires end_date."
    ),
    end_date: date | None = Query(
        None, description="Range end (inclusive); requires start_date."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> ProfitAndLossRead:
    return ProfitAndLossRead(
        **reports.profit_and_loss(
            db, year=year, month=month, start_date=start_date, end_date=end_date
        )
    )


@router.get("/trial-balance", response_model=TrialBalanceRead)
def get_trial_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> TrialBalanceRead:
    """The single most convincing 10 seconds of the demo (§9): grand_total_debit
    == grand_total_credit and is_balanced is the live proof of P1."""
    return TrialBalanceRead(**reports.trial_balance(db))


@router.get("/budget-summary", response_model=Page[BudgetSummaryRow])
def get_budget_summary(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Page[BudgetSummaryRow]:
    """Committed vs achieved per confirmed/revised budget, for the pie
    chart (§9). The dataset is small (a handful of budgets), so pagination
    is applied in Python over the already-computed rows rather than via SQL.
    """
    all_rows = budgets_service.budget_summary(db)
    start = (page - 1) * page_size
    page_rows = all_rows[start : start + page_size]
    return Page[BudgetSummaryRow](
        items=[BudgetSummaryRow(**row) for row in page_rows],
        total=len(all_rows),
        page=page,
        page_size=page_size,
    )
