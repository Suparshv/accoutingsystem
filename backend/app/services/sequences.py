"""Document numbering (SPEC.md §12.4).

The rule this module exists to obey: never ``SELECT MAX(number) + 1``. Two
users clicking Confirm in the same instant would read the same maximum and
produce the same number; the UNIQUE constraint would catch it, but as a 500
rather than as correct behaviour.

Instead each sequence is a row, and a caller takes a row-level lock on it:

    SELECT ... FOR UPDATE   -- second caller blocks here until the first commits
    last_number += 1
    format and return

The lock is released by the CALLER's commit, which is also why nothing in this
module commits.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.sequence import Sequence

JOURNAL_ENTRY_SEQUENCE = "journal_entry"
JOURNAL_ENTRY_PREFIX = "JE"


def next_journal_entry_number(db: Session) -> str:
    """Return the next manual journal entry number, e.g. ``JE/2026/0001``.

    Only manual entries use this. An entry created by confirming a document
    reuses that document's number instead (§12.4), which is why the posting
    engine takes an optional ``number`` argument.
    """
    return _next_number(db, name=JOURNAL_ENTRY_SEQUENCE, prefix=JOURNAL_ENTRY_PREFIX)


def _next_number(db: Session, *, name: str, prefix: str) -> str:
    """Increment a named sequence under a row lock and format the result."""
    year = date.today().year
    row = _lock_sequence_row(db, name=name, prefix=prefix, year=year)

    # The counter resets at the start of each year (§12.4 "resets yearly").
    if row.year != year:
        row.year = year
        row.last_number = 0

    row.last_number += 1
    db.flush()

    return f"{prefix}/{row.year}/{row.last_number:04d}"


def _lock_sequence_row(db: Session, *, name: str, prefix: str, year: int) -> Sequence:
    """SELECT ... FOR UPDATE the sequence row, creating it on first use.

    Two callers can race to create the row the very first time a sequence is
    used. The loser of that race hits the UNIQUE constraint on ``name``; the
    savepoint lets us absorb that and re-read the winner's row rather than
    failing the whole request.
    """
    stmt = select(Sequence).where(Sequence.name == name).with_for_update()
    row = db.execute(stmt).scalar_one_or_none()
    if row is not None:
        return row

    try:
        with db.begin_nested():
            row = Sequence(name=name, prefix=prefix, year=year, last_number=0)
            db.add(row)
            db.flush()
    except IntegrityError:
        row = db.execute(stmt).scalar_one()

    return row
