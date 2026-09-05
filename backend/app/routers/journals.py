"""Journals HTTP layer (SPEC.md §9 accounting.journals)."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import JournalType
from app.core.errors import NotFoundError
from app.database import get_db
from app.models.account import Account, Journal
from app.schemas.account import JournalCreate, JournalRead
from app.schemas.common import Page

router = APIRouter(prefix="/journals", tags=["journals"])


@router.get("", response_model=Page[JournalRead])
def list_journals(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    journal_type: JournalType | None = None,
) -> Page[JournalRead]:
    stmt = select(Journal)
    if journal_type is not None:
        stmt = stmt.where(Journal.journal_type == journal_type)
    if search:
        stmt = stmt.where(Journal.name.ilike(f"%{search}%"))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    rows = db.execute(
        stmt.order_by(Journal.name).offset((page - 1) * page_size).limit(page_size)
    ).scalars()

    return Page[JournalRead](
        items=[JournalRead.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=JournalRead, status_code=status.HTTP_201_CREATED)
def create_journal(
    payload: JournalCreate, db: Session = Depends(get_db)
) -> JournalRead:
    """The default account must exist — every FK is verified before write (§11)."""
    if db.get(Account, payload.default_account_id) is None:
        raise NotFoundError(
            f"Account {payload.default_account_id} does not exist.",
            details={"account_id": payload.default_account_id},
        )

    journal = Journal(**payload.model_dump())
    db.add(journal)
    db.commit()
    db.refresh(journal)
    return JournalRead.model_validate(journal)
