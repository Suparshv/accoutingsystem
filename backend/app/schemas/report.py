"""Pydantic schemas for financial reports (SPEC.md §9 reports, §6.4)."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import Money


class BalanceSheetRow(BaseModel):
    label: str
    account_type: str
    balance: Money


class BalanceSheetRead(BaseModel):
    assets: list[BalanceSheetRow]
    liabilities: list[BalanceSheetRow]
    total_assets: Money
    total_liabilities: Money
    is_balanced: bool


class ProfitAndLossIncome(BaseModel):
    income_from_sales: Money
    total_income: Money


class ProfitAndLossExpenses(BaseModel):
    purchase_expense: Money
    other_expense: Money
    total_expenses: Money


class ProfitAndLossRead(BaseModel):
    income: ProfitAndLossIncome
    expenses: ProfitAndLossExpenses
    net_income: Money


class TrialBalanceRow(BaseModel):
    account_code: str
    account_name: str
    total_debit: Money
    total_credit: Money


class TrialBalanceRead(BaseModel):
    rows: list[TrialBalanceRow]
    grand_total_debit: Money
    grand_total_credit: Money
    is_balanced: bool
