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
