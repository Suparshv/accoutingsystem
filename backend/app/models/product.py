"""Product categories and products (SPEC.md §7.3)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ProductType
from app.database import Base


class ProductCategory(Base):
    """Mockup: 'Category can be created and saved on the fly (Many2one field)'."""

    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "sales_price >= 0", name="ck_products_sales_price_non_negative"
        ),
        CheckConstraint("cost_price >= 0", name="ck_products_cost_price_non_negative"),
        Index("ix_products_name", "name"),
        Index("ix_products_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType, name="product_type", native_enum=True),
        nullable=False,
        default=ProductType.goods,
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_categories.id", ondelete="SET NULL"), nullable=True
    )
    sales_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    cost_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    # P1 — file upload is out of scope for this slice; see Partner.image_path.
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
