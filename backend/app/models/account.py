"""Chart of accounts and journals (SPEC.md §7.4)."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ACCOUNT_TYPES_BY_GROUP,
    AccountGroup,
    AccountType,
    JournalType,
)
from app.database import Base
from app.models.base import TimestampedBase


def _group_type_check_sql() -> str:
    """Build ck_accounts_group_type_consistent from ACCOUNT_TYPES_BY_GROUP.

    Generating the SQL from the same dict the Pydantic validator reads means
    the database CHECK and the API validation cannot disagree — adding an
    account type in one place updates both.
    """
    clauses = []
    for group, types in ACCOUNT_TYPES_BY_GROUP.items():
        allowed = ", ".join(f"'{t.value}'" for t in types)
        clauses.append(
            f"(account_group = '{group.value}' AND account_type IN ({allowed}))"
        )
    return " OR ".join(clauses)


class Account(Base, TimestampedBase):
    """A bucket money flows into and out of. Archive, never delete (§7.4)."""

    __tablename__ = "accounts"

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)

    account_group: Mapped[AccountGroup] = mapped_column(
        SAEnum(
            AccountGroup,
            name="account_group",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    account_type: Mapped[AccountType] = mapped_column(
        SAEnum(
            AccountType,
            name="account_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    # Mockup has an 'Archived' button on the Chart of Accounts list view.
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        CheckConstraint(
            _group_type_check_sql(),
            name="ck_accounts_group_type_consistent",
        ),
        Index("ix_accounts_account_type", "account_type"),
    )

    def __repr__(self) -> str:
        return f"<Account {self.code} {self.name}>"


class Journal(Base, TimestampedBase):
    """Groups entries by nature and supplies a default account (§7.4)."""

    __tablename__ = "journals"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    journal_type: Mapped[JournalType] = mapped_column(
        SAEnum(
            JournalType,
            name="journal_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    # RESTRICT: an account that a journal points at must not vanish underneath it.
    default_account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    default_account: Mapped[Account] = relationship(Account, lazy="joined")

    def __repr__(self) -> str:
        return f"<Journal {self.name} ({self.journal_type.value})>"
