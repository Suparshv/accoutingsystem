"""Column conventions every table shares (SPEC.md §7 preamble).

"All tables have id BIGSERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL
DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()."

Defaults are ``server_default=func.now()`` rather than a Python value so the
database clock is the single source of truth, and rows written by seed scripts
or psql get the same treatment as rows written by the API.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampedBase:
    """Mixin supplying the three columns every table in §7 carries."""

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
