"""Product and product-category CRUD — SPEC.md §9 masters, §10.3, §11."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.core.enums import ProductType
from app.core.errors import AppError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.database import get_db
from app.models.product import Product, ProductCategory
from app.models.user import User
from app.schemas.common import Page
from app.schemas.product import (
    ProductCategoryCreate,
    ProductCategoryOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)

router = APIRouter(tags=["products"])


def _get_active_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise AppError(404, "NOT_FOUND", "Product not found.")
    return product


def _assert_category_exists(db: Session, category_id: int | None) -> None:
    if category_id is not None and db.get(ProductCategory, category_id) is None:
        raise AppError(404, "NOT_FOUND", "Product category not found.")


# --- product categories (create-on-the-fly from the product form) ---


@router.get("/product-categories", response_model=list[ProductCategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProductCategory]:
    return list(
        db.execute(select(ProductCategory).order_by(ProductCategory.name)).scalars()
    )


@router.post("/product-categories", response_model=ProductCategoryOut, status_code=201)
def create_category(
    body: ProductCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> ProductCategory:
    existing = db.execute(
        select(ProductCategory).where(ProductCategory.name == body.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            409, "CATEGORY_NAME_TAKEN", "A category with this name already exists."
        )
    category = ProductCategory(name=body.name)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


# --- products ---


@router.get("/products", response_model=Page[ProductOut])
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    category_id: int | None = None,
    product_type: ProductType | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[ProductOut]:
    stmt = select(Product).where(Product.is_active.is_(True))
    if search:
        stmt = stmt.where(Product.name.ilike(f"%{search}%"))
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if product_type is not None:
        stmt = stmt.where(Product.product_type == product_type)
    stmt = stmt.order_by(Product.created_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return Page(items=rows, total=total, page=page, page_size=page_size)


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Product:
    return _get_active_product(db, product_id)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(
    body: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Product:
    _assert_category_exists(db, body.category_id)
    product = Product(**body.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    body: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Product:
    product = _get_active_product(db, product_id)
    if body.category_id is not None:
        _assert_category_exists(db, body.category_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204, response_model=None)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> None:
    product = _get_active_product(db, product_id)
    product.is_active = False
    db.commit()
