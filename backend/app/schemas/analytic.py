"""Analytic account schemas — SPEC.md §7.3."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AnalyticAccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)


class AnalyticAccountUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)


class AnalyticAccountOut(BaseModel):
    id: int
    name: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
