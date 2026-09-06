"""Budget HTTP layer (SPEC.md §9 budgets).

Achievement figures on every line are computed live by services/budgets.py on
each read, and are null while the budget is draft (§7.9).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import BudgetState
from app.core.errors import AppError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.core.search import fk_matches, ilike_any, like_pattern
from app.database import get_db
from app.models.analytic import AnalyticAccount
from app.models.budget import Budget, BudgetLine
from app.models.partner import Partner
from app.models.user import User
from app.schemas.budget import (
    BudgetCreate,
    BudgetLineIn,
    BudgetOut,
    BudgetRow,
    BudgetUpdate,
    SourceDocumentRow,
)
from app.schemas.common import Page
from app.services import budgets as budgets_service

router = APIRouter(prefix="/budgets", tags=["budgets"])

LEDGER_ROLES = ("admin", "accountant")


@router.get("", response_model=Page[BudgetRow])
def list_budgets(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    state: BudgetState | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> Page[BudgetRow]:
    """Both an original and its revision stay visible in this list (§10.7)."""
    stmt = select(Budget)
    if state is not None:
        stmt = stmt.where(Budget.state == state)
    if search:
        pattern = like_pattern(search)
        stmt = stmt.where(
            or_(
                ilike_any(pattern, Budget.name),
                fk_matches(
                    Budget.responsible_id,
                    Partner.id,
                    ilike_any(pattern, Partner.name),
                ),
            )
        )
    # id tiebreaker: created_at alone isn't unique (rows from one bulk
    # transaction share a timestamp), which lets LIMIT/OFFSET pagination
    # duplicate/skip rows across pages — see routers/sales_orders.py.
    stmt = stmt.order_by(Budget.created_at.desc(), Budget.id.desc())

    rows, total = paginate(db, stmt, page, page_size)
    names = _partner_names(db, [r.responsible_id for r in rows])

    return Page(
        items=[
            BudgetRow(
                id=b.id,
                name=b.name,
                start_date=b.start_date,
                end_date=b.end_date,
                state=b.state,
                responsible_name=names.get(b.responsible_id),
                revision_of_id=b.revision_of_id,
                revised_with_id=b.revised_with_id,
            )
            for b in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{budget_id}", response_model=BudgetOut)
def get_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> BudgetOut:
    return _to_out(db, _get_or_404(db, budget_id))


@router.post("", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> BudgetOut:
    if payload.responsible_id is not None:
        if db.get(Partner, payload.responsible_id) is None:
            raise AppError(404, "NOT_FOUND", "Responsible contact not found.")

    budget = Budget(
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        responsible_id=payload.responsible_id,
        state=BudgetState.DRAFT,
    )
    _replace_lines(db, budget, payload.lines)

    db.add(budget)
    db.commit()
    db.refresh(budget)
    return _to_out(db, budget)


@router.put("/{budget_id}", response_model=BudgetOut)
def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> BudgetOut:
    """Draft only. A confirmed budget is revised, not edited (§10.7)."""
    budget = _get_or_404(db, budget_id)
    budgets_service.assert_editable(budget)

    if payload.name is not None:
        budget.name = payload.name
    if payload.start_date is not None:
        budget.start_date = payload.start_date
    if payload.end_date is not None:
        budget.end_date = payload.end_date
    if payload.responsible_id is not None:
        budget.responsible_id = payload.responsible_id
    if payload.lines is not None:
        _replace_lines(db, budget, payload.lines)

    if budget.end_date < budget.start_date:
        raise AppError(
            422, "VALIDATION_ERROR", "end_date must be on or after start_date."
        )

    db.commit()
    db.refresh(budget)
    return _to_out(db, budget)


@router.post("/{budget_id}/confirm", response_model=BudgetOut)
def confirm_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> BudgetOut:
    """Draft -> confirmed. Achievement figures become visible from here."""
    budget = _get_or_404(db, budget_id)
    budgets_service.confirm_budget(db, budget)
    db.commit()
    db.refresh(budget)
    return _to_out(db, budget)


@router.post(
    "/{budget_id}/revise", response_model=BudgetOut, status_code=status.HTTP_201_CREATED
)
def revise_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> BudgetOut:
    """Create the linked draft copy and mark the original revised (§10.7)."""
    budget = _get_or_404(db, budget_id)
    revision = budgets_service.revise_budget(db, budget)
    db.commit()
    db.refresh(revision)
    return _to_out(db, revision)


@router.post("/{budget_id}/cancel", response_model=BudgetOut)
def cancel_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> BudgetOut:
    budget = _get_or_404(db, budget_id)
    budgets_service.cancel_budget(db, budget)
    db.commit()
    db.refresh(budget)
    return _to_out(db, budget)


@router.get(
    "/{budget_id}/lines/{line_id}/source-documents",
    response_model=list[SourceDocumentRow],
)
def budget_line_source_documents(
    budget_id: int,
    line_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*LEDGER_ROLES)),
) -> list[SourceDocumentRow]:
    """The documents behind one line's achieved amount (§10.7)."""
    budget = _get_or_404(db, budget_id)
    line = db.get(BudgetLine, line_id)
    if line is None or line.budget_id != budget.id:
        raise AppError(404, "NOT_FOUND", "Budget line not found on this budget.")

    rows = budgets_service.list_source_documents(db, line)
    names = _partner_names(db, [r["partner_id"] for r in rows])

    return [
        SourceDocumentRow(
            document_type=r["document_type"],
            number=r["number"],
            date=r["date"],
            partner_id=r["partner_id"],
            partner_name=names.get(r["partner_id"]),
            line_total=r["line_total"],
        )
        for r in rows
    ]


# --- helpers ----------------------------------------------------------------


def _get_or_404(db: Session, budget_id: int) -> Budget:
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise AppError(404, "NOT_FOUND", f"Budget {budget_id} does not exist.")
    return budget


def _replace_lines(db: Session, budget: Budget, lines: list[BudgetLineIn]) -> None:
    """Rebuild the line set, rejecting duplicate analytic+type pairs.

    uq_budget_line_analytic enforces this in the database too, but a raw
    IntegrityError is not a presentable message — this gives the client the
    DUPLICATE_BUDGET_LINE code §10.7 asks for.
    """
    seen: set[tuple[int, str]] = set()
    budget.lines.clear()

    for index, line in enumerate(lines):
        key = (line.analytic_account_id, line.line_type.value)
        if key in seen:
            raise AppError(
                422,
                "DUPLICATE_BUDGET_LINE",
                "The same analytic account cannot appear twice with the same "
                "type — achievement would be double-counted.",
                {
                    "analytic_account_id": line.analytic_account_id,
                    "line_type": line.line_type.value,
                },
            )
        seen.add(key)

        if db.get(AnalyticAccount, line.analytic_account_id) is None:
            raise AppError(404, "NOT_FOUND", "Analytic account not found.")

        budget.lines.append(
            BudgetLine(
                analytic_account_id=line.analytic_account_id,
                line_type=line.line_type,
                committed_amount=line.committed_amount,
                sequence=(index + 1) * 10,
            )
        )


def _partner_names(db: Session, ids: list[int | None]) -> dict[int, str]:
    unique = {i for i in ids if i is not None}
    if not unique:
        return {}
    rows = db.execute(
        select(Partner.id, Partner.name).where(Partner.id.in_(unique))
    ).all()
    return {r.id: r.name for r in rows}


def _analytic_names(db: Session, ids: list[int]) -> dict[int, str]:
    unique = {i for i in ids if i is not None}
    if not unique:
        return {}
    rows = db.execute(
        select(AnalyticAccount.id, AnalyticAccount.name).where(
            AnalyticAccount.id.in_(unique)
        )
    ).all()
    return {r.id: r.name for r in rows}


def _to_out(db: Session, budget: Budget) -> BudgetOut:
    partner_names = _partner_names(db, [budget.responsible_id])
    analytic_names = _analytic_names(
        db, [ln.analytic_account_id for ln in budget.lines]
    )

    lines = []
    for line in budget.lines:
        # Null while draft — achievement is meaningless before commitment.
        achievement = budgets_service.achievement_or_none(db, line)
        lines.append(
            {
                "id": line.id,
                "analytic_account_id": line.analytic_account_id,
                "analytic_account_name": analytic_names.get(line.analytic_account_id),
                "line_type": line.line_type,
                "committed_amount": line.committed_amount,
                "sequence": line.sequence,
                "achieved_amount": (
                    achievement.achieved_amount if achievement else None
                ),
                "achieved_percent": (
                    achievement.achieved_percent if achievement else None
                ),
                "amount_to_achieve": (
                    achievement.amount_to_achieve if achievement else None
                ),
            }
        )

    return BudgetOut(
        id=budget.id,
        name=budget.name,
        start_date=budget.start_date,
        end_date=budget.end_date,
        responsible_id=budget.responsible_id,
        responsible_name=partner_names.get(budget.responsible_id),
        state=budget.state,
        revision_of_id=budget.revision_of_id,
        revised_with_id=budget.revised_with_id,
        lines=lines,
    )
