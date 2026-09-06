"""List-view text search — SPEC.md §9 standard_query_params, §10.3.

Every `?search=` filter used to ILIKE a single column. On the document lists
that column was `number`, so searching for a customer or vendor name — the
name shown in the list's own second column — returned nothing while searching
for a number worked. These tests pin the widened behaviour, one per endpoint.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import (
    PartnerType,
    PaymentState,
    PaymentType,
    ProductType,
    UserRole,
)
from app.core.security import encode_token, hash_password
from app.database import get_db
from app.main import app
from app.models.partner import Partner
from app.models.payment import Payment
from app.models.product import Product, ProductCategory
from app.models.purchase import PurchaseOrder, VendorBill
from app.models.sales import CustomerInvoice, SalesOrder
from app.models.user import User


def _numbers(client: TestClient, path: str) -> list[str]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return [item["number"] for item in response.json()["items"]]


def _names(client: TestClient, path: str) -> list[str]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


@pytest.fixture()
def admin_client(db: Session) -> TestClient:
    """GET /users is admin-only; conftest's `client` is an accountant."""
    admin = User(
        name="Ada Admin",
        login_id="admin01",
        email="admin01@example.com",
        password_hash=hash_password("Passw0rd!x"),
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.flush()

    app.dependency_overrides[get_db] = lambda: db
    token = encode_token(user_id=admin.id, role=admin.role.value, partner_id=None)
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def two_partners(db: Session) -> dict[str, int]:
    """The pair from §10.3's search scenario, plus details to search on."""
    open_wood = Partner(
        name="Open Wood",
        partner_type=PartnerType.both,
        email="hello@openwood.example",
        phone="9876543210",
    )
    joey = Partner(
        name="Joey Wills",
        partner_type=PartnerType.both,
        email="joey@wills.example",
        phone="9000000001",
    )
    db.add_all([open_wood, joey])
    db.flush()
    return {"open_wood": open_wood.id, "joey": joey.id}


# --- masters -------------------------------------------------------------


def test_partner_search_matches_name_email_and_phone(client, two_partners):
    assert _names(client, "/api/partners?search=wood") == ["Open Wood"]
    # Email and phone are both columns of the Contacts list, so both search.
    assert _names(client, "/api/partners?search=joey@wills") == ["Joey Wills"]
    assert _names(client, "/api/partners?search=9876543210") == ["Open Wood"]


def test_product_search_matches_category_name(client, db: Session):
    category = ProductCategory(name="Furniture")
    db.add(category)
    db.flush()
    db.add_all(
        [
            Product(
                name="Dining Table",
                product_type=ProductType.goods,
                category_id=category.id,
                sales_price=Decimal("2000.00"),
                cost_price=Decimal("1500.00"),
            ),
            Product(
                name="Delivery",
                product_type=ProductType.service,
                sales_price=Decimal("100.00"),
                cost_price=Decimal("0.00"),
            ),
        ]
    )
    db.flush()

    assert _names(client, "/api/products?search=dining") == ["Dining Table"]
    # The list shows a Category column; searching it must work too.
    assert _names(client, "/api/products?search=furnit") == ["Dining Table"]


def test_account_search_matches_code_as_well_as_name(client, ledger):
    assert _names(client, "/api/accounts?search=debtors") == ["Debtors A/c"]
    assert _names(client, "/api/accounts?search=1200") == ["Debtors A/c"]


def test_user_search_matches_name_and_email_not_just_login_id(admin_client):
    # login_id worked before; name and email — the other two list columns —
    # did not.
    assert admin_client.get("/api/auth/users?search=admin01").json()["total"] == 1
    assert admin_client.get("/api/auth/users?search=Ada Admin").json()["total"] == 1
    assert (
        admin_client.get("/api/auth/users?search=admin01@example.com").json()["total"]
        == 1
    )


# --- documents -----------------------------------------------------------


def test_sales_order_search_matches_customer_name(client, db: Session, two_partners):
    db.add_all(
        [
            SalesOrder(
                number="SO/2026/0001",
                customer_id=two_partners["open_wood"],
                order_date=date(2026, 1, 5),
                total_amount=Decimal("100.00"),
            ),
            SalesOrder(
                number="SO/2026/0002",
                customer_id=two_partners["joey"],
                order_date=date(2026, 1, 6),
                total_amount=Decimal("200.00"),
            ),
        ]
    )
    db.flush()

    assert _numbers(client, "/api/sales-orders?search=0001") == ["SO/2026/0001"]
    assert _numbers(client, "/api/sales-orders?search=open wood") == ["SO/2026/0001"]
    assert _numbers(client, "/api/sales-orders?search=joey") == ["SO/2026/0002"]


def test_purchase_order_search_matches_vendor_name(client, db: Session, two_partners):
    db.add(
        PurchaseOrder(
            number="PO/2026/0001",
            vendor_id=two_partners["open_wood"],
            order_date=date(2026, 1, 5),
            total_amount=Decimal("100.00"),
        )
    )
    db.flush()

    assert _numbers(client, "/api/purchase-orders?search=open wood") == ["PO/2026/0001"]


def test_customer_invoice_search_matches_customer_name(
    client, db: Session, two_partners
):
    db.add(
        CustomerInvoice(
            number="INV/2026/0001",
            customer_id=two_partners["joey"],
            invoice_date=date(2026, 1, 5),
            total_amount=Decimal("100.00"),
        )
    )
    db.flush()

    assert _numbers(client, "/api/customer-invoices?search=wills") == ["INV/2026/0001"]


def test_vendor_bill_search_matches_vendor_name_and_bill_reference(
    client, db: Session, two_partners
):
    db.add(
        VendorBill(
            number="BILL/2026/0001",
            vendor_id=two_partners["open_wood"],
            bill_reference="OW-99321",
            bill_date=date(2026, 1, 5),
            total_amount=Decimal("100.00"),
        )
    )
    db.flush()

    assert _numbers(client, "/api/vendor-bills?search=open wood") == ["BILL/2026/0001"]
    assert _numbers(client, "/api/vendor-bills?search=OW-99321") == ["BILL/2026/0001"]


def test_payment_search_is_wired_up_at_all(client, db: Session, ledger, two_partners):
    """The Payments page always sent ?search=; the endpoint never read it."""
    invoices = [
        CustomerInvoice(
            number=f"INV/2026/010{i}",
            customer_id=partner_id,
            invoice_date=date(2026, 1, 5),
            total_amount=Decimal("500.00"),
        )
        for i, partner_id in enumerate(
            [two_partners["open_wood"], two_partners["joey"]]
        )
    ]
    db.add_all(invoices)
    db.flush()

    # A 'receive' payment must name the invoice it settles
    # (ck_payments_direction_matches_target).
    db.add_all(
        [
            Payment(
                number="PAY/2026/0001",
                payment_type=PaymentType.RECEIVE,
                partner_id=two_partners["open_wood"],
                journal_id=ledger["journal"].id,
                invoice_id=invoices[0].id,
                amount=Decimal("100.00"),
                payment_date=date(2026, 1, 5),
                state=PaymentState.CONFIRMED,
            ),
            Payment(
                number="PAY/2026/0002",
                payment_type=PaymentType.RECEIVE,
                partner_id=two_partners["joey"],
                journal_id=ledger["journal"].id,
                invoice_id=invoices[1].id,
                amount=Decimal("200.00"),
                payment_date=date(2026, 1, 6),
                state=PaymentState.CONFIRMED,
            ),
        ]
    )
    db.flush()

    assert _numbers(client, "/api/payments?search=open wood") == ["PAY/2026/0001"]
    assert _numbers(client, "/api/payments?search=0002") == ["PAY/2026/0002"]


# --- wildcards -----------------------------------------------------------


def test_like_metacharacters_are_matched_literally(client, db: Session):
    """`%` and `_` reached LIKE unescaped, so a search for "50%" matched all."""
    db.add_all(
        [
            Partner(name="50% Off Furnishings", partner_type=PartnerType.customer),
            Partner(name="Regular Timber", partner_type=PartnerType.customer),
        ]
    )
    db.flush()

    assert _names(client, "/api/partners?search=50%25") == ["50% Off Furnishings"]
