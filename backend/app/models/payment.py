"""Payments (SPEC.md §7.8).

ONE table for both directions. The mockup's Bill Payment and Invoice Payment
screens are the same form with ``payment_type`` flipped, so modelling them as
two tables would duplicate every column and every query.

A payment has no ledger effect until it is confirmed. While draft it is a
record of intent — the target document's amount_due is unchanged and it does
not appear in the trial balance (§10.6).

NOTE FOR THE MERGE: ``invoice_id`` is deliberately declared WITHOUT its
foreign key for now. See the comment on the column — the FK is specified by
§7.8 and must be restored once models/sales.py lands.
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
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PaymentState, PaymentType
from app.database import Base
from app.models.base import TimestampedBase

MONEY = Numeric(14, 2)


class Payment(Base, TimestampedBase):
    """Money moving in either direction, against exactly one document."""

    __tablename__ = "payments"

    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)

    payment_type: Mapped[PaymentType] = mapped_column(
        SAEnum(
            PaymentType,
            name="payment_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    partner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    # Mockup "Payment Via". Must be a bank or cash journal — enforced in the
    # service, because the journal's type lives on another table and a CHECK
    # cannot reach it.
    journal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("journals.id", ondelete="RESTRICT"), nullable=False
    )

    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    state: Mapped[PaymentState] = mapped_column(
        SAEnum(
            PaymentState,
            name="payment_state",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=PaymentState.DRAFT,
        server_default=PaymentState.DRAFT.value,
    )

    # RESTORE THE FOREIGN KEY AT THE SALES MERGE:
    #     ForeignKey("customer_invoices.id", ondelete="RESTRICT")
    # §7.8 specifies it, and it belongs here. It is left off for now because
    # SQLAlchemy resolves foreign keys on every flush, not only at create_all
    # — so declaring it against a table models/sales.py has not defined yet
    # makes EVERY payment insert fail with NoReferencedTableError, not just
    # schema creation. The two CHECK constraints below still guarantee that a
    # payment targets exactly one document and in the right direction; only
    # referential integrity on this column is missing until the merge.
    invoice_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bill_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("vendor_bills.id", ondelete="RESTRICT"), nullable=True
    )

    journal_entry_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )

    bill: Mapped["VendorBill | None"] = relationship(  # noqa: F821
        "VendorBill", foreign_keys=[bill_id]
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        # A payment settles exactly one document. Full cross-document
        # reconciliation is deliberately out of scope (§7.8.1); partial
        # payments against one document ARE supported.
        CheckConstraint(
            "(invoice_id IS NOT NULL AND bill_id IS NULL) "
            "OR (invoice_id IS NULL AND bill_id IS NOT NULL)",
            name="ck_payments_exactly_one_target",
        ),
        # You cannot 'send' money to settle a customer invoice.
        CheckConstraint(
            "(payment_type = 'receive' AND invoice_id IS NOT NULL) "
            "OR (payment_type = 'send' AND bill_id IS NOT NULL)",
            name="ck_payments_direction_matches_target",
        ),
        # amount_paid aggregates filter on both columns.
        Index("ix_payments_invoice_state", "invoice_id", "state"),
        Index("ix_payments_bill_state", "bill_id", "state"),
        Index("ix_payments_partner", "partner_id"),
    )

    def __repr__(self) -> str:
        return f"<Payment {self.number} {self.payment_type.value} {self.amount}>"
