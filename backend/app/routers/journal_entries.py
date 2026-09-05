"""Ledger HTTP layer (SPEC.md §9 accounting.journal_entries).

Note what is absent: there is no PUT and no DELETE route. A posted entry is
immutable (R4), and the cleanest way to guarantee that at the API boundary is
for the method simply not to exist — FastAPI answers 405 for a path that
matches with a method that does not. Immutability by absence of API.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import BigInteger, Column, MetaData, String, Table, func, select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import JournalEntryState
from app.core.errors import NotFoundError
from app.database import get_db
from app.models.account import Account, Journal
from app.models.journal_entry import JournalEntry
from app.models.user import User
from app.schemas.common import Page
from app.schemas.journal_entry import (
    JournalEntryCreate,
    JournalEntryLineRead,
    JournalEntryListRow,
    JournalEntryRead,
)
from app.services.accounting import LineInput, post_journal_entry

router = APIRouter(prefix="/journal-entries", tags=["journal-entries"])

# TEMPORARY: a read-only handle on the partners table so the list and detail
# views can resolve partner_name. models/partner.py is owned by a teammate and
# lands in the next merge; replace this with a relationship to Partner then.
# Held in its own MetaData so create_all never sees it.
_partners = Table(
    "partners",
    MetaData(),
    Column("id", BigInteger, primary_key=True),
    Column("name", String(200)),
)


@router.get("", response_model=Page[JournalEntryListRow])
def list_journal_entries(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    state: JournalEntryState | None = None,
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Page[JournalEntryListRow]:
    """Exactly the columns in the mockup's Journal Entries list view.

    One query with joins, not one lookup per row — a list view that issues a
    query per row is the classic N+1 the Performance criterion penalises.
    """
    stmt = (
        select(
            JournalEntry.id,
            JournalEntry.entry_date,
            JournalEntry.number,
            _partners.c.name.label("partner_name"),
            Journal.name.label("journal_name"),
            JournalEntry.total_amount,
            JournalEntry.state,
        )
        .join(Journal, Journal.id == JournalEntry.journal_id)
        .outerjoin(_partners, _partners.c.id == JournalEntry.partner_id)
    )
    if state is not None:
        stmt = stmt.where(JournalEntry.state == state)
    if search:
        stmt = stmt.where(JournalEntry.number.ilike(f"%{search}%"))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    rows = db.execute(
        stmt.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return Page[JournalEntryListRow](
        items=[
            JournalEntryListRow(
                id=row.id,
                date=row.entry_date,
                number=row.number,
                partner_name=row.partner_name,
                journal_name=row.journal_name,
                total_amount=row.total_amount,
                state=row.state,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{entry_id}", response_model=JournalEntryRead)
def get_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> JournalEntryRead:
    """Header plus lines, with account_name and partner_name resolved."""
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise NotFoundError(f"Journal entry {entry_id} does not exist.")
    return _to_read_model(db, entry)


@router.post("", response_model=JournalEntryRead, status_code=status.HTTP_201_CREATED)
def create_journal_entry(
    payload: JournalEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> JournalEntryRead:
    """Post a manual journal entry.

    The router does not build a JournalEntry — it hands the lines to the engine
    and commits what comes back. The commit is here, in the caller, because the
    caller owns the transaction boundary (R3); for a manual entry there is
    nothing else in the transaction, but the shape stays the same as the
    invoice and bill flows that will follow.

    If the engine raises, nothing is committed and no partial entry survives.
    The exception is deliberately not caught (§8.3).
    """
    entry = post_journal_entry(
        db,
        entry_date=payload.entry_date,
        journal_id=payload.journal_id,
        lines=[
            LineInput(
                account_id=line.account_id,
                debit=line.debit,
                credit=line.credit,
                partner_id=line.partner_id,
                label=line.label,
            )
            for line in payload.lines
        ],
        partner_id=payload.partner_id,
        reference=payload.reference,
        source_type="manual",
    )
    db.commit()
    db.refresh(entry)
    return _to_read_model(db, entry)


def _to_read_model(db: Session, entry: JournalEntry) -> JournalEntryRead:
    """Shape one entry for the wire, resolving account and partner names."""
    partner_names = _partner_names(db, entry)
    account_names = _account_names(db, entry)

    return JournalEntryRead(
        id=entry.id,
        number=entry.number,
        entry_date=entry.entry_date,
        journal_id=entry.journal_id,
        journal_name=entry.journal.name,
        partner_id=entry.partner_id,
        partner_name=partner_names.get(entry.partner_id),
        reference=entry.reference,
        state=entry.state,
        source_type=entry.source_type,
        source_id=entry.source_id,
        total_amount=entry.total_amount,
        lines=[
            JournalEntryLineRead(
                id=line.id,
                account_id=line.account_id,
                account_name=account_names.get(line.account_id),
                partner_id=line.partner_id,
                partner_name=partner_names.get(line.partner_id),
                label=line.label,
                debit=line.debit,
                credit=line.credit,
                sequence=line.sequence,
            )
            for line in entry.lines
        ],
    )


def _account_names(db: Session, entry: JournalEntry) -> dict[int, str]:
    ids = {line.account_id for line in entry.lines}
    if not ids:
        return {}
    rows = db.execute(select(Account.id, Account.name).where(Account.id.in_(ids))).all()
    return {row.id: row.name for row in rows}


def _partner_names(db: Session, entry: JournalEntry) -> dict[int, str]:
    ids = {line.partner_id for line in entry.lines if line.partner_id is not None}
    if entry.partner_id is not None:
        ids.add(entry.partner_id)
    if not ids:
        return {}
    rows = db.execute(
        select(_partners.c.id, _partners.c.name).where(_partners.c.id.in_(ids))
    ).all()
    return {row.id: row.name for row in rows}
