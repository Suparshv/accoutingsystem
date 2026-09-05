"""Shared pagination for list endpoints (SPEC.md §9 standard_query_params).

Only the documented defaults are implemented — arbitrary `sort` overrides are
not, since no §10 scenario exercises them. Every list endpoint orders by
created_at desc, matching the spec's stated default.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def paginate(
    db: Session, stmt: Select, page: int, page_size: int
) -> tuple[list[Any], int]:
    page_size = min(page_size, MAX_PAGE_SIZE)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return rows, total
