"""Document numbering counters (SPEC.md §12.4).

One row per sequence name. The row itself is the lock: a caller takes
``SELECT ... FOR UPDATE`` on it, increments, and holds the lock until its own
transaction commits, so two concurrent callers can never read the same
``last_number``.
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampedBase


class Sequence(Base, TimestampedBase):
    """A named, year-scoped counter. See services/sequences.py."""

    __tablename__ = "sequences"

    # e.g. "journal_entry", "customer_invoice"
    name: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    def __repr__(self) -> str:
        return f"<Sequence {self.name} {self.year}:{self.last_number}>"
