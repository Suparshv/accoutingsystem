"""Shared response shapes (SPEC.md §9 conventions)."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

ItemT = TypeVar("ItemT")


class Page(BaseModel, Generic[ItemT]):
    """The list_envelope shape every list endpoint returns."""

    items: list[ItemT]
    total: int
    page: int
    page_size: int
