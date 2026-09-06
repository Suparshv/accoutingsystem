"""Product validation — SPEC.md §10.3, §11.

The prices are a pair: the CHECK constraints keep each of them non-negative
on its own, but nothing stopped a product being saved that costs more to buy
than it is offered for. That is always a data-entry slip, and it silently
turns every sale of the product into a loss in the P&L.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.enums import ProductType
from app.models.product import Product


def _create(client, **overrides) -> tuple[int, dict]:
    body = {
        "name": "Dining Table",
        "product_type": "goods",
        "sales_price": "2000.00",
        "cost_price": "1500.00",
    }
    body.update(overrides)
    response = client.post("/api/products", json=body)
    return response.status_code, response.json()


def test_cost_price_below_sales_price_is_accepted(client):
    """§10.3's own worked example: sales 2000.00, cost 1500.00."""
    status_code, body = _create(client)
    assert status_code == 201, body
    assert body["sales_price"] == "2000.00"


def test_equal_prices_are_accepted(client):
    """Selling at cost is break-even, not an error."""
    status_code, body = _create(client, sales_price="1500.00", cost_price="1500.00")
    assert status_code == 201, body


def test_cost_price_above_sales_price_is_rejected(client):
    status_code, body = _create(client, sales_price="1000.00", cost_price="1500.00")
    assert status_code == 422
    assert body["error"]["code"] == "COST_ABOVE_SALES_PRICE"


def test_cost_price_above_the_default_sales_price_is_rejected(client):
    """sales_price defaults to 0.00, so an omitted one is still compared."""
    response = client.post(
        "/api/products",
        json={"name": "Dining Table", "product_type": "goods", "cost_price": "1500.00"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "COST_ABOVE_SALES_PRICE"


def test_negative_price_is_still_rejected(client):
    """The pre-existing §10.3 scenario must keep failing on its own terms."""
    status_code, _ = _create(client, sales_price="-100.00")
    assert status_code == 422


@pytest.fixture()
def saved_product(db: Session) -> Product:
    product = Product(
        name="Chair",
        product_type=ProductType.goods,
        sales_price=Decimal("1000.00"),
        cost_price=Decimal("600.00"),
    )
    db.add(product)
    db.flush()
    return product


def test_update_cannot_raise_cost_above_the_stored_sales_price(
    client, saved_product: Product
):
    """A partial update sends only cost_price; the rule still has to hold."""
    response = client.put(
        f"/api/products/{saved_product.id}", json={"cost_price": "1200.00"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "COST_ABOVE_SALES_PRICE"


def test_update_cannot_drop_sales_price_below_the_stored_cost_price(
    client, saved_product: Product
):
    """The mirror image — lowering the sales price under the stored cost."""
    response = client.put(
        f"/api/products/{saved_product.id}", json={"sales_price": "500.00"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "COST_ABOVE_SALES_PRICE"


def test_update_raising_both_prices_together_is_accepted(
    client, saved_product: Product
):
    response = client.put(
        f"/api/products/{saved_product.id}",
        json={"sales_price": "2000.00", "cost_price": "1200.00"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cost_price"] == "1200.00"
