"""Budgets and budget lines (SPEC.md §7.9).

Nothing here stores achievement. `achieved_amount`, `achieved_percent` and
`amount_to_achieve` are computed on read by services/budgets.py — storing them
would create five separate invalidation paths (a bill confirmed, an invoice
confirmed, a document cancelled, an analytic retagged, a period edited) and
any one of them being missed leaves the number silently wrong (§7.9.1, R5).
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BudgetLineType, BudgetState
from app.database import Base
from app.models.base import TimestampedBase

MONEY = Numeric(14, 2)


class Budget(Base, TimestampedBase):
    """A committed spend/earn plan for a period, per analytic account.

    The two nullable self-references form a doubly-linked revision chain: the
    original points forward with ``revised_with_id``, the revision points back
    with ``revision_of_id``. The mockup needs to navigate both ways, and a
    single link would only support one direction.
    """

    __tablename__ = "budgets"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Mockup: "Select from Contacts created".
    responsible_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("partners.id", ondelete="SET NULL"), nullable=True
    )

    state: Mapped[BudgetState] = mapped_column(
        SAEnum(
            BudgetState,
            name="budget_state",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=BudgetState.DRAFT,
        server_default=BudgetState.DRAFT.value,
    )

    # Set on the NEW budget, pointing back to the original.
    revision_of_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("budgets.id", ondelete="SET NULL"), nullable=True
    )
    # Set on the ORIGINAL, pointing forward to the revision.
    revised_with_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("budgets.id", ondelete="SET NULL"), nullable=True
    )

    lines: Mapped[list[BudgetLine]] = relationship(
        "BudgetLine",
        back_populates="budget",
        cascade="all, delete-orphan",
        order_by="BudgetLine.sequence",
    )

    # remote_side disambiguates which end of the self-join each link follows;
    # without it SQLAlchemy cannot tell these two FKs apart.
    revision_of: Mapped[Budget | None] = relationship(
        "Budget",
        remote_side="Budget.id",
        foreign_keys=[revision_of_id],
        post_update=True,
    )
    revised_with: Mapped[Budget | None] = relationship(
        "Budget",
        remote_side="Budget.id",
        foreign_keys=[revised_with_id],
        post_update=True,
    )

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_budgets_dates_ordered"),
        CheckConstraint(
            "revision_of_id IS NULL OR revision_of_id <> id",
            name="ck_budget_not_self_revision",
        ),
        Index("ix_budgets_state", "state"),
        Index("ix_budgets_period", "start_date", "end_date"),
    )

    def __repr__(self) -> str:
        return f"<Budget {self.name} {self.state.value}>"


class BudgetLine(Base, TimestampedBase):
    """One analytic account's committed amount, for one direction of money."""

    __tablename__ = "budget_lines"

    budget_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    analytic_account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("analytic_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    line_type: Mapped[BudgetLineType] = mapped_column(
        SAEnum(
            BudgetLineType,
            name="budget_line_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    committed_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )

    budget: Mapped[Budget] = relationship("Budget", back_populates="lines")

    __table_args__ = (
        CheckConstraint("committed_amount > 0", name="ck_budget_line_amount_positive"),
        # Two lines for the same analytic and type would double-count
        # achievement — the same bills would be summed into both.
        UniqueConstraint(
            "budget_id",
            "analytic_account_id",
            "line_type",
            name="uq_budget_line_analytic",
        ),
        Index("ix_budget_lines_budget", "budget_id"),
        Index("ix_budget_lines_analytic", "analytic_account_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<BudgetLine analytic={self.analytic_account_id} {self.line_type.value}>"
        )
