"""Contacts — customers and vendors (SPEC.md §7.3, table `partners`)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import PartnerType
from app.database import Base


class Partner(Base):
    __tablename__ = "partners"
    __table_args__ = (
        Index(
            "ix_partners_email_unique",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        Index("ix_partners_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    partner_type: Mapped[PartnerType] = mapped_column(
        Enum(PartnerType, name="partner_type", native_enum=True),
        nullable=False,
        default=PartnerType.customer,
    )
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # P1 — file upload is out of scope for this slice; column reserved so the
    # schema matches SPEC.md §7.3 without requiring upload plumbing now.
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
