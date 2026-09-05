"""Enumerations shared across the ledger (SPEC.md §7.1).

Only the ledger enums live here so far. The masters enums (user_role,
partner_type, product_type) are being added in parallel — append, do not
reorganise.

Every member's *value* is what Postgres stores, which is why the models pass
``values_callable`` to SQLAlchemy's Enum: without it SQLAlchemy would persist
the member *name* ("BALANCE_SHEET") instead of the value ("balance_sheet").
"""

from enum import Enum


class AccountGroup(str, Enum):
    """Which report an account appears on (SPEC.md §6.1)."""

    BALANCE_SHEET = "balance_sheet"
    PROFIT_AND_LOSS = "profit_and_loss"


class AccountType(str, Enum):
    """The nature of an account. Decides the side it appears on in a report."""

    ASSET = "asset"
    LIABILITY = "liability"
    BANK = "bank"
    CAPITAL = "capital"
    CASH = "cash"
    INCOME = "income"
    EXPENSE = "expense"
    OTHER_EXPENSE = "other_expense"


class JournalType(str, Enum):
    """Groups entries by nature and supplies a default account."""

    SALES = "sales"
    PURCHASE = "purchase"
    BANK = "bank"
    CASH = "cash"


class JournalEntryState(str, Enum):
    """Lifecycle of a ledger header. Only 'posted' entries reach a report."""

    DRAFT = "draft"
    POSTED = "posted"
    CANCELLED = "cancelled"


# The group -> allowed types mapping behind ck_accounts_group_type_consistent
# (SPEC.md §7.4). The database CHECK constraint and the Pydantic validator are
# both generated from this dict, so the two layers can never drift apart.
ACCOUNT_TYPES_BY_GROUP: dict[AccountGroup, tuple[AccountType, ...]] = {
    AccountGroup.BALANCE_SHEET: (
        AccountType.ASSET,
        AccountType.LIABILITY,
        AccountType.BANK,
        AccountType.CAPITAL,
        AccountType.CASH,
    ),
    AccountGroup.PROFIT_AND_LOSS: (
        AccountType.INCOME,
        AccountType.EXPENSE,
        AccountType.OTHER_EXPENSE,
    ),
}


def is_group_type_consistent(group: AccountGroup, account_type: AccountType) -> bool:
    """True when this account_type is legal for this account_group."""
    return account_type in ACCOUNT_TYPES_BY_GROUP[group]
"""Every enum in one place (SPEC.md §7.1 / file layout note in §4).

This module only owns the enums for the auth and masters slice (users,
partners, products). Ledger-side enums (account_type, journal_type,
document_state, ...) belong to whoever builds models/account.py and
models/journal_entry.py — add them below rather than starting a second file.
"""

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    accountant = "accountant"
    contact = "contact"


class PartnerType(str, enum.Enum):
    customer = "customer"
    vendor = "vendor"
    both = "both"


class ProductType(str, enum.Enum):
    goods = "goods"
    service = "service"
    combo = "combo"
