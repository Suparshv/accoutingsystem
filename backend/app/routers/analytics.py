"""Analytic account CRUD — SPEC.md §9 masters.

The /analytic-accounts/{id}/budgets sub-resource is NOT implemented here: it
reads the budgets table, which belongs to the budgets module (next round).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.core.errors import AppError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.database import get_db
from app.models.analytic import AnalyticAccount
from app.models.user import User
from app.schemas.analytic import (
    AnalyticAccountCreate,
    AnalyticAccountOut,
    AnalyticAccountUpdate,
)
from app.schemas.common import Page

router = APIRouter(prefix="/analytic-accounts", tags=["analytics"])


def _get_active_analytic(db: Session, analytic_id: int) -> AnalyticAccount:
    analytic = db.get(AnalyticAccount, analytic_id)
    if analytic is None or not analytic.is_active:
        raise AppError(404, "NOT_FOUND", "Analytic account not found.")
    return analytic


def _assert_name_available(
    db: Session, name: str, exclude_id: int | None = None
) -> None:
    stmt = select(AnalyticAccount).where(AnalyticAccount.name == name)
    if exclude_id is not None:
        stmt = stmt.where(AnalyticAccount.id != exclude_id)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise AppError(
            409, "NAME_TAKEN", "An analytic account with this name already exists."
        )


@router.get("", response_model=Page[AnalyticAccountOut])
def list_analytic_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[AnalyticAccountOut]:
    stmt = select(AnalyticAccount).where(AnalyticAccount.is_active.is_(True))
    if search:
        stmt = stmt.where(AnalyticAccount.name.ilike(f"%{search}%"))
    # id tiebreaker: created_at alone isn't unique (rows from one bulk
    # transaction share a timestamp), which lets LIMIT/OFFSET pagination
    # duplicate/skip rows across pages — see routers/sales_orders.py.
    stmt = stmt.order_by(AnalyticAccount.created_at.desc(), AnalyticAccount.id.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return Page(items=rows, total=total, page=page, page_size=page_size)


@router.get("/{analytic_id}", response_model=AnalyticAccountOut)
def get_analytic_account(
    analytic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyticAccount:
    return _get_active_analytic(db, analytic_id)


@router.post("", response_model=AnalyticAccountOut, status_code=201)
def create_analytic_account(
    body: AnalyticAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> AnalyticAccount:
    _assert_name_available(db, body.name)
    analytic = AnalyticAccount(name=body.name)
    db.add(analytic)
    db.commit()
    db.refresh(analytic)
    return analytic


@router.put("/{analytic_id}", response_model=AnalyticAccountOut)
def update_analytic_account(
    analytic_id: int,
    body: AnalyticAccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> AnalyticAccount:
    analytic = _get_active_analytic(db, analytic_id)
    if body.name is not None:
        _assert_name_available(db, body.name, exclude_id=analytic_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(analytic, field, value)
    db.commit()
    db.refresh(analytic)
    return analytic


@router.delete("/{analytic_id}", status_code=204, response_model=None)
def delete_analytic_account(
    analytic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> None:
    analytic = _get_active_analytic(db, analytic_id)
    analytic.is_active = False
    db.commit()
