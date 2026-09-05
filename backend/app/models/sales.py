"""Sales cycle: sales orders and customer invoices (SPEC.md §7.7).

Structurally the mirror of the purchase cycle (§7.6): same shapes, opposite
ledger direction. A sales order produces NO journal entry — nothing has been
sold yet, it is a commitment only. Confirming a customer invoice is what
reaches the ledger (§8.2), via services/sales.py calling the one writer to
the ledger, services/accounting.py::post_journal_entry.
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
from app.models.account import Account
from app.models.analytic import AnalyticAccount
from app.models.base import TimestampedBase
from app.models.partner import Partner
from app.models.product import Product

# Every money column here, matching the ledger's own convention (§7 preamble).
MONEY = Numeric(14, 2)

_DOCUMENT_STATE_TYPE = SAEnum(
    DocumentState, name="document_state", values_callable=lambda e: [m.value for m in e]
)


class SalesOrder(Base, TimestampedBase):
    """Mockup: Sales Order. Produces NO journal entry — a commitment only."""

    __tablename__ = "sales_orders"

    number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[DocumentState] = mapped_column(
        _DOCUMENT_STATE_TYPE,
        nullable=False,
        default=DocumentState.DRAFT,
        server_default=DocumentState.DRAFT.value,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default="0.00"
    )

    customer: Mapped[Partner] = relationship(Partner, lazy="joined")
    lines: Mapped[list[SalesOrderLine]] = relationship(
        "SalesOrderLine",
        back_populates="sales_order",
        cascade="all, delete-orphan",
        order_by="SalesOrderLine.sequence",
    )

    __table_args__ = (
        Index("ix_sales_orders_customer_id", "customer_id"),
        Index("ix_sales_orders_state", "state"),
    )

    @property
    def customer_name(self) -> str | None:
        """Read by Pydantic's from_attributes — customer is eager-loaded."""
        return self.customer.name if self.customer else None

    def __repr__(self) -> str:
        return f"<SalesOrder {self.number} {self.state.value}>"


class SalesOrderLine(Base, TimestampedBase):
    __tablename__ = "sales_order_lines"

    sales_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    analytic_account_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("analytic_accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # ALWAYS computed server-side from quantity * unit_price (R6) — a client
    # value here is discarded, never trusted (§10.5 "the server ignores a
    # client-supplied line total").
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )

    sales_order: Mapped[SalesOrder] = relationship("SalesOrder", back_populates="lines")
    product: Mapped[Product] = relationship(Product, lazy="joined")
    analytic_account: Mapped[AnalyticAccount | None] = relationship(
        AnalyticAccount, lazy="joined"
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sol_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sol_unit_price_non_negative"),
    )

    @property
    def product_name(self) -> str | None:
        return self.product.name if self.product else None

    @property
    def analytic_account_name(self) -> str | None:
        return self.analytic_account.name if self.analytic_account else None

    def __repr__(self) -> str:
        return f"<SalesOrderLine product={self.product_id} qty={self.quantity}>"


class CustomerInvoice(Base, TimestampedBase):
    __tablename__ = "customer_invoices"

    number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    state: Mapped[DocumentState] = mapped_column(
        _DOCUMENT_STATE_TYPE,
        nullable=False,
        default=DocumentState.DRAFT,
        server_default=DocumentState.DRAFT.value,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    # Mockup: the SO button is shown only when this is non-null (§10.5's bill
    # equivalent). Set by create_invoice_from_so, null for a directly-created
    # invoice.
    source_so_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sales_orders.id", ondelete="SET NULL"), nullable=True
    )
    # Set on confirm. Null while draft.
    journal_entry_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True
    )

    customer: Mapped[Partner] = relationship(Partner, lazy="joined")
    lines: Mapped[list[CustomerInvoiceLine]] = relationship(
        "CustomerInvoiceLine",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="CustomerInvoiceLine.sequence",
    )

    __table_args__ = (
        CheckConstraint(
            "due_date IS NULL OR due_date >= invoice_date",
            name="ck_ci_due_date_after_invoice_date",
        ),
        Index("ix_customer_invoices_customer_id", "customer_id"),
        Index("ix_customer_invoices_state", "state"),
        Index("ix_customer_invoices_source_so_id", "source_so_id"),
    )

    @property
    def customer_name(self) -> str | None:
        return self.customer.name if self.customer else None

    def __repr__(self) -> str:
        return f"<CustomerInvoice {self.number} {self.state.value}>"


class CustomerInvoiceLine(Base, TimestampedBase):
    __tablename__ = "customer_invoice_lines"

    customer_invoice_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("customer_invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    # Prefilled with Sales Income A/c by the service layer; the user may
    # override it, which is exactly why an invoice can produce more than one
    # grouped credit line on confirm (§8.2).
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

    invoice: Mapped[CustomerInvoice] = relationship(
        "CustomerInvoice", back_populates="lines"
    )
    product: Mapped[Product] = relationship(Product, lazy="joined")
    account: Mapped[Account] = relationship(Account, lazy="joined")
    analytic_account: Mapped[AnalyticAccount | None] = relationship(
        AnalyticAccount, lazy="joined"
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_cil_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_cil_unit_price_non_negative"),
        # Budget achievement scans invoice lines by analytic (§7.7); without
        # this it is a sequential scan once real volume exists.
        Index("ix_cil_analytic_account_id", "analytic_account_id"),
    )

    @property
    def product_name(self) -> str | None:
        return self.product.name if self.product else None

    @property
    def account_name(self) -> str | None:
        return self.account.name if self.account else None

    @property
    def analytic_account_name(self) -> str | None:
        return self.analytic_account.name if self.analytic_account else None

    def __repr__(self) -> str:
        return (
            f"<CustomerInvoiceLine product={self.product_id} total={self.line_total}>"
        )
