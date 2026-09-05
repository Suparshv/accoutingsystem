"""Login identity and authorisation role (SPEC.md §7.2)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole
from app.database import Base

if TYPE_CHECKING:
    from app.models.partner import Partner


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "char_length(login_id) BETWEEN 6 AND 12", name="ck_users_login_length"
        ),
        CheckConstraint(
            "role <> 'contact' OR partner_id IS NOT NULL",
            name="ck_users_contact_needs_partner",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    login_id: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True),
        nullable=False,
        default=UserRole.accountant,
    )
    partner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("partners.id", ondelete="SET NULL"), nullable=True
    )
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

    partner: Mapped["Partner | None"] = relationship("Partner")
