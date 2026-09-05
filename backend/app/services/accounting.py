r"""★ The posting engine (SPEC.md §8).

This module contains the ONLY code in the repository that INSERTs into
``journal_entries`` or ``journal_entry_lines``. No router, no other service, no
script. That is rule R1 in AGENTS.md, and it buys three things:

* one place to enforce "total debits == total credits",
* one place to test it (tests/test_posting_engine.py),
* one place to fix it if it is ever wrong.

Verify the rule holds::

    grep -rn "JournalEntry(\|JournalEntryLine(" backend/app/ --include=*.py
    # expected: hits only in this file (and tests/)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence as SequenceABC
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import JournalEntryState
from app.core.errors import (
    AccountArchivedError,
    AccountNotFoundError,
    InvalidLineError,
    JournalNotFoundError,
    UnbalancedEntryError,
)
from app.models.account import Account, Journal
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.services import sequences

ZERO = Decimal("0.00")

# Lines are numbered 10, 20, 30... so a line can later be inserted between two
# existing ones without renumbering the rest.
SEQUENCE_STEP = 10


@dataclass(frozen=True)
class LineInput:
    """One line as handed to the engine (§8.1 line_input_shape).

    A plain dataclass, not a Pydantic model, so that services can call the
    engine without importing anything HTTP-shaped.
    """

    account_id: int
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    partner_id: int | None = None
    label: str | None = None


def post_journal_entry(
    db: Session,
    *,
    entry_date: date,
    journal_id: int,
    lines: SequenceABC[LineInput],
    partner_id: int | None = None,
    reference: str | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
    number: str | None = None,
) -> JournalEntry:
    """Validate and post a balanced journal entry. The one writer to the ledger.

    Runs the eleven ordered steps of §8.1. Every failure raises before anything
    is added to the session, so a rejected entry leaves no trace whatsoever —
    not a header, not a line.

    Note that this does NOT commit. See step 10.
    """
    # Steps 1-3.
    _validate_lines(lines)

    # Steps 4-5.
    total_debit, total_credit = _assert_balanced(lines)

    # Step 6.
    _resolve_accounts(db, lines)

    # Step 7.
    journal = db.get(Journal, journal_id)
    if journal is None:
        raise JournalNotFoundError(
            f"Journal {journal_id} does not exist.",
            details={"journal_id": journal_id},
        )

    # Step 8.
    entry_number = number or sequences.next_journal_entry_number(db)

    # Step 9.
    entry = JournalEntry(
        number=entry_number,
        entry_date=entry_date,
        journal_id=journal_id,
        partner_id=partner_id,
        reference=reference,
        state=JournalEntryState.POSTED,
        source_type=source_type,
        source_id=source_id,
        total_amount=total_debit,
    )
    for index, line in enumerate(lines):
        entry.lines.append(
            JournalEntryLine(
                account_id=line.account_id,
                partner_id=line.partner_id,
                label=line.label,
                debit=line.debit,
                credit=line.credit,
                sequence=(index + 1) * SEQUENCE_STEP,
            )
        )
    db.add(entry)

    # Step 10. flush, NEVER commit — the CALLER owns the transaction boundary.
    # The invoice service commits once, after both the invoice and its entry
    # are in the session. A commit here would break that atomicity (R3).
    db.flush()

    # Step 11.
    return entry


# --- private helpers --------------------------------------------------------


def _validate_lines(lines: SequenceABC[LineInput]) -> None:
    """Steps 1-3: line count and the shape of each individual line."""
    # Step 1.
    if not lines:
        raise UnbalancedEntryError("A journal entry must have at least two lines")

    # Step 2. A single-line entry cannot balance by definition.
    if len(lines) < 2:
        raise UnbalancedEntryError("A journal entry must have at least two lines")

    # Step 3. The index is 0-based so the frontend can highlight the row.
    for index, line in enumerate(lines):
        if line.debit < ZERO or line.credit < ZERO:
            raise InvalidLineError(
                "Debit and credit must not be negative.", line_index=index
            )
        if line.debit > ZERO and line.credit > ZERO:
            raise InvalidLineError(
                "A line carries either a debit or a credit, never both.",
                line_index=index,
            )
        if line.debit == ZERO and line.credit == ZERO:
            raise InvalidLineError(
                "A line must carry either a debit or a credit.", line_index=index
            )


def _assert_balanced(lines: SequenceABC[LineInput]) -> tuple[Decimal, Decimal]:
    """Steps 4-5: sum both sides in Decimal and demand exact equality."""
    # Step 4. Decimal sums, never float, and never rounded mid-sum.
    total_debit = sum((line.debit for line in lines), ZERO)
    total_credit = sum((line.credit for line in lines), ZERO)

    # Step 5. Decimal equality is exact — no epsilon. If you ever feel the need
    # to write abs(a - b) < 0.01 here, a float has crept into the money path;
    # go and find it rather than loosening this comparison.
    if total_debit != total_credit:
        raise UnbalancedEntryError(
            total_debit=total_debit,
            total_credit=total_credit,
            difference=total_debit - total_credit,
        )

    return total_debit, total_credit


def _resolve_accounts(db: Session, lines: Iterable[LineInput]) -> dict[int, Account]:
    """Step 6: every account exists and none is archived.

    One query with an IN clause, not one query per line — a 200-line entry
    would otherwise issue 200 round trips.
    """
    wanted = {line.account_id for line in lines}
    found = {
        account.id: account
        for account in db.execute(
            select(Account).where(Account.id.in_(wanted))
        ).scalars()
    }

    missing = sorted(wanted - found.keys())
    if missing:
        raise AccountNotFoundError(
            f"Account(s) {', '.join(str(i) for i in missing)} do not exist.",
            details={"account_ids": missing},
        )

    archived = sorted(a.id for a in found.values() if a.is_archived)
    if archived:
        raise AccountArchivedError(
            f"Account(s) {', '.join(str(i) for i in archived)} are archived.",
            details={"account_ids": archived},
        )

    return found
