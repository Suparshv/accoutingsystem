"""Shared Pydantic building blocks (SPEC.md §9 conventions)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, Field, PlainSerializer

# Money crosses the wire as a STRING, never a JSON number: JSON numbers are
# IEEE-754 doubles, which reintroduces the exact float problem Decimal exists
# to avoid (§9 money_wire_format). max_digits/decimal_places also make Pydantic
# REJECT a third decimal place rather than silently rounding it (§11).
Money = Annotated[
    Decimal,
    Field(max_digits=14, decimal_places=2),
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]

ItemT = TypeVar("ItemT")


class Page(BaseModel, Generic[ItemT]):
    """The list_envelope shape every list endpoint returns.

    No endpoint ever returns an unbounded array (§9).
    """

    items: list[ItemT]
    total: int
    page: int
    page_size: int
