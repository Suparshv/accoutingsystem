"""Every enum in one place (SPEC.md §7.1 / file layout note in §4).

Two slices live here: the auth and masters enums (users, partners, products)
and the ledger enums (accounts, journals, journal entries). Append new ones
rather than starting a second file.

Every member's *value* is what Postgres stores, which is why the models pass
``values_callable`` to SQLAlchemy's Enum: without it SQLAlchemy would persist
the member *name* ("BALANCE_SHEET") instead of the value ("balance_sheet").
"""

from enum import Enum


# --- auth and masters -------------------------------------------------------


class UserRole(str, Enum):
    admin = "admin"
    accountant = "accountant"
    contact = "contact"


class PartnerType(str, Enum):
    customer = "customer"
    vendor = "vendor"
    both = "both"


class ProductType(str, Enum):
    goods = "goods"
    service = "service"
    combo = "combo"


# --- ledger -----------------------------------------------------------------


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
