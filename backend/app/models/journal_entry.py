"""The general ledger — the two tables every financial report reads (§7.5).

Nothing in this module is written outside ``services/accounting.py``. That is
rule R1 in AGENTS.md, and it is what makes the balance rule enforceable in one
place.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import JournalEntryState
from app.database import Base
from app.models.account import Account, Journal
from app.models.base import TimestampedBase

# Every money column in the system. 14 digits total, 2 after the point —
# the database counterpart of Python's Decimal (AGENTS.md R2).
MONEY = Numeric(14, 2)


class JournalEntry(Base, TimestampedBase):
    """The ledger header. Every financial event in the system lands here.

    Immutable once posted (R4): no UPDATE, no DELETE, and no PUT or DELETE
    route exists for it. To undo, post a reversal.
    """

    __tablename__ = "journal_entries"

    # Copied from the source document's number, or JE/YYYY/NNNN if manual.
    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)

    # The mockup calls this 'Accounting Date'.
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)

    journal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("journals.id", ondelete="RESTRICT"), nullable=False
    )
    partner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=True
    )

    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    state: Mapped[JournalEntryState] = mapped_column(
        SAEnum(
            JournalEntryState,
            name="journal_entry_state",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=JournalEntryState.DRAFT,
        server_default=JournalEntryState.DRAFT.value,
    )

    # customer_invoice | vendor_bill | payment | manual
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Denormalised sum(debit), for the list view ONLY. The single permitted
    # exception to "derive, never store" (R5). No report reads this column —
    # reports always re-aggregate from journal_entry_lines.
    total_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default="0.00"
    )

    lines: Mapped[list[JournalEntryLine]] = relationship(
        "JournalEntryLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="JournalEntryLine.sequence",
    )

    journal: Mapped[Journal] = relationship(Journal, lazy="joined")

    __table_args__ = (
        Index("ix_journal_entries_entry_date", "entry_date"),
        # Reports filter state='posted' first, then a date range.
        Index("ix_journal_entries_state_entry_date", "state", "entry_date"),
        Index("ix_journal_entries_source", "source_type", "source_id"),
    )

    def __repr__(self) -> str:
        return f"<JournalEntry {self.number} {self.state.value}>"


class JournalEntryLine(Base, TimestampedBase):
    """The ledger detail. EVERY financial report reads only this table.

    The three CHECK constraints below are the strongest double-entry guarantee
    Postgres can express on a single row. The balance rule itself spans rows,
    so it lives in the posting engine instead (§7.5 balance_rule).
    """

    __tablename__ = "journal_entry_lines"

    journal_entry_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    partner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=True
    )

    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    debit: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    credit: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default="0.00"
    )

    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )

    entry: Mapped[JournalEntry] = relationship("JournalEntry", back_populates="lines")
    account: Mapped[Account] = relationship(Account, lazy="joined")

    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_jel_non_negative"),
        # A line is either a debit or a credit, never both.
        CheckConstraint("NOT (debit > 0 AND credit > 0)", name="ck_jel_one_side_only"),
        # A zero line carries no information and would pass a balance check silently.
        CheckConstraint("debit > 0 OR credit > 0", name="ck_jel_not_both_zero"),
        # Balance Sheet and P&L group by account; this keeps them fast at scale.
        Index("ix_jel_account_entry", "account_id", "journal_entry_id"),
        # Partner ledger / portal queries.
        Index("ix_jel_partner", "partner_id"),
        Index("ix_jel_journal_entry", "journal_entry_id"),
    )

    def __repr__(self) -> str:
        return f"<JournalEntryLine acct={self.account_id} {self.debit}/{self.credit}>"
