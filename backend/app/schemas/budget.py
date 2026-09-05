"""Pydantic schemas for budgets (SPEC.md §7.9, §9)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import BudgetLineType, BudgetState
from app.schemas.common import Money


class BudgetLineIn(BaseModel):
    analytic_account_id: int
    line_type: BudgetLineType
    committed_amount: Money = Field(gt=0)


class BudgetLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analytic_account_id: int
    analytic_account_name: str | None = None
    line_type: BudgetLineType
    committed_amount: Money
    sequence: int
    # Computed live on every read, never stored (§7.9.1). Null while the budget
    # is draft: achievement is meaningless until it has been committed to.
    achieved_amount: Money | None = None
    achieved_percent: Money | None = None
    # May be NEGATIVE when over budget. Deliberately not clamped (§10.7).
    amount_to_achieve: Money | None = None


class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    start_date: date
    end_date: date
    responsible_id: int | None = None
    lines: list[BudgetLineIn] = []

    @model_validator(mode="after")
    def check_period_and_lines(self) -> "BudgetCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class BudgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    start_date: date | None = None
    end_date: date | None = None
    responsible_id: int | None = None
    lines: list[BudgetLineIn] | None = None


class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    start_date: date
    end_date: date
    responsible_id: int | None = None
    responsible_name: str | None = None
    state: BudgetState
    # The doubly-linked revision chain — the mockup navigates both ways.
    revision_of_id: int | None = None
    revised_with_id: int | None = None
    lines: list[BudgetLineOut] = []


class BudgetRow(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date
    state: BudgetState
    responsible_name: str | None = None
    revision_of_id: int | None = None
    revised_with_id: int | None = None


class SourceDocumentRow(BaseModel):
    """One document behind a budget line's achieved amount (§10.7)."""

    document_type: str
    number: str
    date: date
    partner_id: int | None = None
    partner_name: str | None = None
    line_total: Money
