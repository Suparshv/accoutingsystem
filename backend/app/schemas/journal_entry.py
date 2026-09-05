"""Pydantic schemas for the ledger (SPEC.md §7.5, §9)."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import JournalEntryState
from app.schemas.common import Money


class JournalEntryLineCreate(BaseModel):
    """One submitted line. Shape only — the balance rule lives in the engine."""

    account_id: int
    partner_id: int | None = None
    label: str | None = Field(default=None, max_length=255)
    debit: Money = Field(default=0)
    credit: Money = Field(default=0)


class JournalEntryCreate(BaseModel):
    """POST /journal-entries body.

    Note what is NOT here: number, state, total_amount, source_type, source_id.
    The server owns every one of them; accepting them from a client would let
    the caller forge a posted entry (R6).
    """

    entry_date: date
    journal_id: int
    partner_id: int | None = None
    reference: str | None = Field(default=None, max_length=120)
    lines: list[JournalEntryLineCreate]


class JournalEntryLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    account_name: str | None = None
    partner_id: int | None = None
    partner_name: str | None = None
    label: str | None = None
    debit: Money
    credit: Money
    sequence: int


class JournalEntryRead(BaseModel):
    """Detail view: header plus lines with account and partner names resolved."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    entry_date: date
    journal_id: int
    journal_name: str | None = None
    partner_id: int | None = None
    partner_name: str | None = None
    reference: str | None = None
    state: JournalEntryState
    source_type: str | None = None
    source_id: int | None = None
    total_amount: Money
    lines: list[JournalEntryLineRead] = []


class JournalEntryListRow(BaseModel):
    """Exactly the columns in the mockup's Journal Entries list view (§9)."""

    id: int
    date: date
    number: str
    partner_name: str | None = None
    journal_name: str
    total_amount: Money
    state: JournalEntryState
