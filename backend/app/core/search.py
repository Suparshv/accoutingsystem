"""Shared text search for list endpoints (SPEC.md §9 standard_query_params).

Two things every `?search=` filter needs and none of them had:

1.  **More than one column.** §9 describes search as "ILIKE on the resource's
    primary text field", which for a document is its `number`. In practice a
    list shows the customer/vendor name next to that number, so typing a name
    — the obvious thing to do — matched nothing while typing a number worked.
    Each endpoint now searches the text columns its list view actually shows.

2.  **Escaped wildcards.** `f"%{search}%"` hands the user's own `%` and `_`
    to LIKE as wildcards, so a search for "50%" silently matches everything.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import InstrumentedAttribute

# Backslash, doubled for LIKE's own ESCAPE clause rather than for Python.
ESCAPE = "\\"


def like_pattern(search: str) -> str:
    """A contains-pattern with the user's LIKE metacharacters neutralised."""
    escaped = (
        search.strip()
        .replace(ESCAPE, ESCAPE * 2)
        .replace("%", f"{ESCAPE}%")
        .replace("_", f"{ESCAPE}_")
    )
    return f"%{escaped}%"


def ilike_any(pattern: str, *columns: InstrumentedAttribute) -> ColumnElement[bool]:
    """True where any of `columns` contains `pattern`, case-insensitively."""
    return or_(*(column.ilike(pattern, escape=ESCAPE) for column in columns))


def fk_matches(
    fk_column: InstrumentedAttribute,
    pk_column: InstrumentedAttribute,
    criterion: ColumnElement[bool],
) -> ColumnElement[bool]:
    """True where a foreign key points at a row satisfying `criterion`.

    A subquery rather than a join: several of these models eager-load the same
    related table with `lazy="joined"`, and adding a second join for filtering
    would fight that eager load for the same alias.
    """
    return fk_column.in_(select(pk_column).where(criterion))
