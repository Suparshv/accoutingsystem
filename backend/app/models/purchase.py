"""Purchase cycle — orders and vendor bills (SPEC.md §7.6).

A purchase order produces NO journal entry. It is a commitment, not a
financial event: nothing has been bought yet, so nothing hits the ledger.
The bill is where money becomes real.

Note what is absent from VendorBill: amount_paid, amount_due and
payment_status. All three are derived on read from confirmed payments
(services/payments.py), never stored (R5).
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

from app.core.enums import DocumentState
from app.database import Base
from app.models.base import TimestampedBase

MONEY = Numeric(14, 2)


def _document_state_column() -> SAEnum:
    return SAEnum(
        DocumentState,
        name="document_state",
        values_callable=lambda e: [m.value for m in e],
    )


class PurchaseOrder(Base, TimestampedBase):
    """A commitment to buy. Format P00001 (§12.4). No ledger effect."""

    __tablename__ = "purchase_orders"

    number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    vendor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)

    state: Mapped[DocumentState] = mapped_column(
        _document_state_column(),
        nullable=False,
        default=DocumentState.DRAFT,
        server_default=DocumentState.DRAFT.value,
    )

    # Recomputed server-side on every write from the sum of line_total.
    total_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default="0.00"
    )

    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        "PurchaseOrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.sequence",
    )

    __table_args__ = (
        Index("ix_purchase_orders_vendor", "vendor_id"),
        Index("ix_purchase_orders_state", "state"),
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder {self.number} {self.state.value}>"


class PurchaseOrderLine(Base, TimestampedBase):
    """One ordered product. line_total is computed server-side, always."""

    __tablename__ = "purchase_order_lines"

    purchase_order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # The budget dimension. Optional, and independent of the ledger (§6.5).
    analytic_account_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("analytic_accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )

    quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # quantity * unit_price, recomputed server-side on save. Any client value
    # is discarded (R6).
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )

    order: Mapped[PurchaseOrder] = relationship("PurchaseOrder", back_populates="lines")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_pol_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_pol_unit_price_non_negative"),
        Index("ix_pol_order", "purchase_order_id"),
    )


class VendorBill(Base, TimestampedBase):
    """A liability incurred. Confirming one posts to the ledger (§8.2)."""

    __tablename__ = "vendor_bills"

    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    vendor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    # The vendor's own document number, e.g. ABC-26-001.
    bill_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)

    bill_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    state: Mapped[DocumentState] = mapped_column(
        _document_state_column(),
        nullable=False,
        default=DocumentState.DRAFT,
        server_default=DocumentState.DRAFT.value,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default="0.00"
    )

    # Non-null only for bills created from a PO. The mockup shows the "PO"
    # button exactly when this is set, and hides it on bills created fresh.
    source_po_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Set on confirm, null while draft. RESTRICT because a posted entry is
    # immutable and must not be deleted out from under the bill (R4).
    journal_entry_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )

    lines: Mapped[list[VendorBillLine]] = relationship(
        "VendorBillLine",
        back_populates="bill",
        cascade="all, delete-orphan",
        order_by="VendorBillLine.sequence",
    )
    source_po: Mapped[PurchaseOrder | None] = relationship("PurchaseOrder")

    __table_args__ = (
        CheckConstraint(
            "due_date IS NULL OR due_date >= bill_date", name="ck_bills_due_after_bill"
        ),
        Index("ix_vendor_bills_vendor", "vendor_id"),
        Index("ix_vendor_bills_state", "state"),
        Index("ix_vendor_bills_source_po", "source_po_id"),
    )

    def __repr__(self) -> str:
        return f"<VendorBill {self.number} {self.state.value}>"


class VendorBillLine(Base, TimestampedBase):
    """One billed product, carrying BOTH classifications (§6.5).

    ``account_id`` is the real ledger account and drives the Balance Sheet and
    P&L. ``analytic_account_id`` is a project tag and drives budgets only. They
    are independent — the analytic dimension never touches the ledger.
    """

    __tablename__ = "vendor_bill_lines"

    vendor_bill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vendor_bills.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # Prefilled with Purchase Expense A/c; the user may override.
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    analytic_account_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("analytic_accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )

    quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )

    bill: Mapped[VendorBill] = relationship("VendorBill", back_populates="lines")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_vbl_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_vbl_unit_price_non_negative"),
        Index("ix_vbl_bill", "vendor_bill_id"),
        # Budget achievement scans bill lines by analytic. Without this index
        # it is a sequential scan on every budget read.
        Index("ix_vbl_analytic", "analytic_account_id"),
    )
