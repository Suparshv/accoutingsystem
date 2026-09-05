"""Dashboard summary endpoint (SPEC.md §9 dashboard section).

Single endpoint, single round trip, per the mockup's App Dashboard tiles.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import DocumentState
from app.database import get_db
from app.models.budget import Budget
from app.models.purchase import PurchaseOrder
from app.models.sales import SalesOrder
from app.models.user import User
from app.services import budgets as budgets_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _document_counts(db: Session, model) -> dict[str, int]:
    """all/confirmed/draft counts for a document model — the same three
    numbers for both sales orders and purchase orders."""
    total = db.execute(select(func.count()).select_from(model)).scalar_one()
    confirmed = db.execute(
        select(func.count())
        .select_from(model)
        .where(model.state == DocumentState.CONFIRMED)
    ).scalar_one()
    draft = db.execute(
        select(func.count())
        .select_from(model)
        .where(model.state == DocumentState.DRAFT)
    ).scalar_one()
    return {"all": total, "confirmed": confirmed, "draft": draft}


def _budget_counts(db: Session) -> dict[str, int]:
    """§9 only names the three fields, not their exact meaning, so this is a
    documented interpretation rather than a guess dressed up as certainty:
      - budget: total budgets, any state
      - committed: budgets actually committed to (confirmed or revised)
      - achieved: budget LINES, among committed budgets, that have reached
        or exceeded their target (achieved_percent >= 100) — "how many of
        our targets have we actually hit"
    """
    budget_total = db.execute(select(func.count()).select_from(Budget)).scalar_one()
    committed_budgets = (
        db.execute(
            select(Budget).where(
                Budget.state.in_(budgets_service.ACHIEVEMENT_VISIBLE_STATES)
            )
        )
        .scalars()
        .all()
    )
    achieved_lines = 0
    for budget in committed_budgets:
        for line in budget.lines:
            if budgets_service.compute_achievement(db, line).achieved_percent >= 100:
                achieved_lines += 1

    return {
        "achieved": achieved_lines,
        "budget": budget_total,
        "committed": len(committed_budgets),
    }


@router.get("")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> dict:
    return {
        "sales": _document_counts(db, SalesOrder),
        "purchase": _document_counts(db, PurchaseOrder),
        "budget": _budget_counts(db),
    }
