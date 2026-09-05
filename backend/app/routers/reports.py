"""Financial reports HTTP layer (SPEC.md §9 reports section)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models.user import User
from app.schemas.report import BalanceSheetRead, ProfitAndLossRead, TrialBalanceRead
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
        None, description="Fiscal year; defaults to the current year"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> ProfitAndLossRead:
    return ProfitAndLossRead(
        **reports.profit_and_loss(db, year=year or date.today().year)
    )


@router.get("/trial-balance", response_model=TrialBalanceRead)
def get_trial_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> TrialBalanceRead:
    """The single most convincing 10 seconds of the demo (§9): grand_total_debit
    == grand_total_credit and is_balanced is the live proof of P1."""
    return TrialBalanceRead(**reports.trial_balance(db))
