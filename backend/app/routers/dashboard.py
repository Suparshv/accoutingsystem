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
from app.models.sales import SalesOrder
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _sales_counts(db: Session) -> dict[str, int]:
    total = db.execute(select(func.count()).select_from(SalesOrder)).scalar_one()
    confirmed = db.execute(
        select(func.count())
        .select_from(SalesOrder)
        .where(SalesOrder.state == DocumentState.CONFIRMED)
    ).scalar_one()
    draft = db.execute(
        select(func.count())
        .select_from(SalesOrder)
        .where(SalesOrder.state == DocumentState.DRAFT)
    ).scalar_one()
    return {"all": total, "confirmed": confirmed, "draft": draft}


def _purchase_counts() -> dict[str, int]:
    """Zeroed until the purchase module (owned separately) lands — that
    model does not exist in this tree yet, and this task is explicitly
    scoped to not create it."""
    return {"all": 0, "confirmed": 0, "draft": 0}


def _budget_counts() -> dict[str, int]:
    """Zeroed until the budgets module (owned separately) lands, for the
    same reason as _purchase_counts."""
    return {"achieved": 0, "budget": 0, "committed": 0}


@router.get("")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> dict:
    return {
        "sales": _sales_counts(db),
        "purchase": _purchase_counts(),
        "budget": _budget_counts(),
    }
