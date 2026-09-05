"""Product / product category schemas — SPEC.md §7.3, §11."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, condecimal

from app.core.enums import ProductType

Money = condecimal(max_digits=14, decimal_places=2, ge=0)


class ProductCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class ProductCategoryOut(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    product_type: ProductType = ProductType.goods
    category_id: int | None = None
    sales_price: Money = Decimal("0.00")
    cost_price: Money = Decimal("0.00")


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    product_type: ProductType | None = None
    category_id: int | None = None
    sales_price: Money | None = None
    cost_price: Money | None = None


class ProductOut(BaseModel):
    id: int
    name: str
    product_type: ProductType
    category_id: int | None
    sales_price: Decimal
    cost_price: Decimal
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
