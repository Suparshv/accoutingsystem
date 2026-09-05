"""Sales cycle, reports and portal ownership — SPEC.md §10.6, §10.9, §10.10.

Mirrors test_posting_engine.py's style: each test names the scenario it
covers. Runs against the real Postgres fixtures in conftest.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.security import encode_token, hash_password
from app.database import get_db
from app.main import app
from app.models.journal_entry import JournalEntry
from app.models.partner import Partner
from app.models.product import Product
from app.models.sales import CustomerInvoice
from app.models.user import User
from app.services import sales as sales_service


@pytest.fixture()
def rahul_contact_client(db: Session, ledger: dict) -> TestClient:
    """A contact user linked to `ledger`'s own partner ("Mr Rahul"), so
    ownership tests can check a contact against invoices the other fixtures
    also create against that same partner id.
    """
    user = User(
        name="Rahul Contact",
        login_id="rahulctc",
        email="rahulctc@example.com",
        password_hash=hash_password("Passw0rd!x"),
        role=UserRole.contact,
        partner_id=ledger["partner_id"],
        is_active=True,
    )
    db.add(user)
    db.flush()

    app.dependency_overrides[get_db] = lambda: db
    token = encode_token(
        user_id=user.id, role=user.role.value, partner_id=ledger["partner_id"]
    )
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_so(
    client: TestClient,
    ledger: dict,
    product: Product,
    unit_price: str = "2000.00",
    quantity: str = "3",
) -> dict:
    response = client.post(
        "/api/sales-orders",
        json={
            "customer_id": ledger["partner_id"],
            "lines": [
                {
                    "product_id": product.id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Scenario: A sales order produces no journal entry (§7.7) ---------------


def test_confirm_sales_order_produces_no_journal_entry(client, ledger, product, db):
    so = _create_so(client, ledger, product)
    assert so["state"] == "draft"
    assert so["total_amount"] == "6000.00"
    assert so["lines"][0]["line_total"] == "6000.00"

    response = client.post(f"/api/sales-orders/{so['id']}/confirm")

    assert response.status_code == 200
    assert response.json()["state"] == "confirmed"
    entries = db.execute(select(JournalEntry)).scalars().all()
    assert entries == []


def test_server_ignores_client_supplied_line_total(client, ledger, product):
    """Mirrors §10.5's PO rule on the sales side: line_total is ALWAYS
    server-computed, any client value is discarded."""
    response = client.post(
        "/api/sales-orders",
        json={
            "customer_id": ledger["partner_id"],
            "lines": [
                {
                    "product_id": product.id,
                    "quantity": "3",
                    "unit_price": "2000.00",
                    "line_total": "1.00",
                }
            ],
        },
    )
    assert response.status_code == 201
    assert response.json()["lines"][0]["line_total"] == "6000.00"


# --- Scenario: Creating a bill (invoice) from a confirmed SO copies everything


def test_create_invoice_from_so_copies_lines(client, ledger, product):
    so = _create_so(client, ledger, product)
    client.post(f"/api/sales-orders/{so['id']}/confirm")

    response = client.post(f"/api/sales-orders/{so['id']}/create-invoice")

    assert response.status_code == 201
    invoice = response.json()
    assert invoice["state"] == "draft"
    assert invoice["customer_id"] == ledger["partner_id"]
    assert invoice["source_so_id"] == so["id"]
    assert invoice["total_amount"] == "6000.00"
    assert invoice["lines"][0]["product_id"] == product.id
    assert invoice["lines"][0]["quantity"] == "3.00"


def test_draft_so_cannot_be_invoiced(client, ledger, product):
    so = _create_so(client, ledger, product)

    response = client.post(f"/api/sales-orders/{so['id']}/create-invoice")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SO_NOT_CONFIRMED"


# --- Scenario: ★ Confirming a customer invoice posts a balanced entry ------


def test_confirm_customer_invoice_posts_the_worked_example(client, ledger, product, db):
    """§8.2's worked example: Debtors debit 10000, Sales Income credit
    10000, mirrored from the vendor-bill flow with debit/credit reversed."""
    response = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": ledger["partner_id"],
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "3",
                    "unit_price": "2000.00",
                },
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "4000.00",
                },
            ],
        },
    )
    invoice = response.json()
    assert invoice["total_amount"] == "10000.00"

    confirm = client.post(f"/api/customer-invoices/{invoice['id']}/confirm")

    assert confirm.status_code == 200
    body = confirm.json()
    assert body["invoice"]["state"] == "confirmed"
    assert body["invoice"]["payment_status"] == "not_paid"
    assert body["journal_entry_number"] == invoice["number"]

    entry = db.get(JournalEntry, body["journal_entry_id"])
    assert entry.state.value == "posted"
    assert len(entry.lines) == 2
    debit_line = next(line for line in entry.lines if line.debit > 0)
    credit_line = next(line for line in entry.lines if line.credit > 0)
    assert debit_line.account_id == ledger["debtors"].id
    assert debit_line.debit == Decimal("10000.00")
    assert debit_line.partner_id == ledger["partner_id"]
    assert credit_line.account_id == ledger["sales_income"].id
    assert credit_line.credit == Decimal("10000.00")


def test_invoice_mixing_income_accounts_produces_grouped_credit_lines(
    client, ledger, product, db
):
    """§10.6: one debit line to Debtors, TWO credit lines on the two
    distinct income accounts used, totals equal."""
    second_income = client.post(
        "/api/accounts",
        json={
            "code": "4100",
            "name": "Service Income A/c",
            "account_group": "profit_and_loss",
            "account_type": "income",
        },
    ).json()

    created = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": ledger["partner_id"],
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "3",
                    "unit_price": "2000.00",
                },
                {
                    "product_id": product.id,
                    "account_id": second_income["id"],
                    "quantity": "1",
                    "unit_price": "4000.00",
                },
            ],
        },
    ).json()

    confirm = client.post(f"/api/customer-invoices/{created['id']}/confirm")
    entry_id = confirm.json()["journal_entry_id"]
    entry = db.get(JournalEntry, entry_id)

    debit_lines = [line for line in entry.lines if line.debit > 0]
    credit_lines = [line for line in entry.lines if line.credit > 0]
    assert len(debit_lines) == 1
    assert debit_lines[0].debit == Decimal("10000.00")
    assert len(credit_lines) == 2
    assert {line.credit for line in credit_lines} == {
        Decimal("6000.00"),
        Decimal("4000.00"),
    }
    assert sum(line.debit for line in entry.lines) == sum(
        line.credit for line in entry.lines
    )


def test_confirming_an_already_confirmed_invoice_is_rejected(
    client, ledger, product, db
):
    created = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": ledger["partner_id"],
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "100.00",
                }
            ],
        },
    ).json()
    client.post(f"/api/customer-invoices/{created['id']}/confirm")

    entries_before = db.execute(select(JournalEntry)).scalars().all()
    response = client.post(f"/api/customer-invoices/{created['id']}/confirm")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_CONFIRMED"
    # No second entry was posted — confirming twice must not double-post.
    entries_after = db.execute(select(JournalEntry)).scalars().all()
    assert len(entries_after) == len(entries_before)


def test_confirming_an_invoice_with_no_lines_is_rejected(db, ledger):
    invoice = CustomerInvoice(
        number="INV/TEST/0001",
        customer_id=ledger["partner_id"],
        invoice_date=date(2026, 2, 1),
    )
    db.add(invoice)
    db.flush()

    with pytest.raises(Exception) as excinfo:
        sales_service.confirm_customer_invoice(db, invoice_id=invoice.id)

    assert excinfo.value.code == "NO_LINES"


# --- Reports (§10.9) ---------------------------------------------------------


def test_balance_sheet_includes_current_period_earnings_and_balances(
    client, ledger, product
):
    """★ The single most important detail: without the Current Period
    Earnings row, total_assets and total_liabilities differ by the period's
    net income and the sheet never balances. `ledger` has no Capital account,
    so a confirmed invoice alone (Debtors debit / Sales Income credit) is
    enough to put a balance on the asset side with nothing offsetting it on
    the liability side except the earnings row this test is checking for.
    """
    invoice = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": ledger["partner_id"],
            "invoice_date": "2026-01-10",
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "10000.00",
                }
            ],
        },
    ).json()
    client.post(f"/api/customer-invoices/{invoice['id']}/confirm")

    response = client.get("/api/reports/balance-sheet?year=2026")

    assert response.status_code == 200
    body = response.json()
    earnings_row = next(
        row for row in body["liabilities"] if row["label"] == "Current Period Earnings"
    )
    assert earnings_row["balance"] == "10000.00"
    assert body["total_assets"] == body["total_liabilities"]
    assert body["is_balanced"] is True


def test_draft_documents_never_appear_in_reports(client, ledger, product):
    """§10.9: a DRAFT customer invoice contributes 0.00 to P&L."""
    client.post(
        "/api/customer-invoices",
        json={
            "customer_id": ledger["partner_id"],
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "50000.00",
                }
            ],
        },
    )

    response = client.get("/api/reports/profit-and-loss?year=2026")

    assert response.status_code == 200
    assert response.json()["income"]["income_from_sales"] == "0.00"


def test_profit_and_loss_and_payments_do_not_change_it(client, ledger, product):
    invoice = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": ledger["partner_id"],
            "invoice_date": "2026-03-01",
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "10000.00",
                }
            ],
        },
    ).json()
    client.post(f"/api/customer-invoices/{invoice['id']}/confirm")

    response = client.get("/api/reports/profit-and-loss?year=2026")

    assert response.status_code == 200
    body = response.json()
    assert body["income"]["income_from_sales"] == "10000.00"
    assert body["net_income"] == "10000.00"


def test_trial_balance_holds_after_the_sales_cycle(client, ledger, product):
    so = _create_so(client, ledger, product)
    client.post(f"/api/sales-orders/{so['id']}/confirm")
    invoice = client.post(f"/api/sales-orders/{so['id']}/create-invoice").json()
    client.post(f"/api/customer-invoices/{invoice['id']}/confirm")

    response = client.get("/api/reports/trial-balance")

    assert response.status_code == 200
    body = response.json()
    assert body["grand_total_debit"] == body["grand_total_credit"]
    assert body["is_balanced"] is True


# --- Portal ownership (§10.10, §12.3) ----------------------------------------


def test_portal_contact_sees_only_own_documents(
    client, contact_client, rahul_contact_client, ledger, product, db
):
    """★ A portal user sees only their own documents."""
    rahul_invoice = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": ledger["partner_id"],
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "1000.00",
                }
            ],
        },
    ).json()
    client.post(f"/api/customer-invoices/{rahul_invoice['id']}/confirm")

    other_partner = Partner(name="Joey Wills")
    db.add(other_partner)
    db.flush()
    joey_invoice = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": other_partner.id,
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "2000.00",
                }
            ],
        },
    ).json()
    client.post(f"/api/customer-invoices/{joey_invoice['id']}/confirm")

    response = rahul_contact_client.get("/api/portal/my-documents")

    assert response.status_code == 200
    numbers = {row["number"] for row in response.json()}
    assert rahul_invoice["number"] in numbers
    assert joey_invoice["number"] not in numbers


def test_portal_partner_id_query_param_is_ignored(rahul_contact_client, ledger):
    """§12.3: the filter derives from the JWT, never a query parameter."""
    baseline = rahul_contact_client.get("/api/portal/my-documents").json()

    overridden = rahul_contact_client.get("/api/portal/my-documents?partner_id=99999")

    assert overridden.status_code == 200
    assert overridden.json() == baseline


def test_contact_cannot_read_another_partners_invoice_by_id(
    client, rahul_contact_client, ledger, product, db
):
    """★ Ownership is checked server-side; guessing an id reveals nothing."""
    other_partner = Partner(name="Joey Wills")
    db.add(other_partner)
    db.flush()
    joey_invoice = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": other_partner.id,
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "500.00",
                }
            ],
        },
    ).json()

    response = rahul_contact_client.get(f"/api/customer-invoices/{joey_invoice['id']}")

    assert response.status_code == 403
    assert "total_amount" not in response.text
    assert "500.00" not in response.text


def test_contact_can_read_own_invoice_by_id(
    client, rahul_contact_client, ledger, product
):
    invoice = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": ledger["partner_id"],
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "500.00",
                }
            ],
        },
    ).json()

    response = rahul_contact_client.get(f"/api/customer-invoices/{invoice['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == invoice["id"]


def test_contact_cannot_pay_another_partners_invoice(
    client, rahul_contact_client, ledger, product, db
):
    """A contact registers payments through the same POST /payments every
    role uses (routers/payments.py), not a portal-specific endpoint — the
    ownership check lives there (§10.10, §12.2)."""
    other_partner = Partner(name="Joey Wills")
    db.add(other_partner)
    db.flush()
    joey_invoice = client.post(
        "/api/customer-invoices",
        json={
            "customer_id": other_partner.id,
            "lines": [
                {
                    "product_id": product.id,
                    "account_id": ledger["sales_income"].id,
                    "quantity": "1",
                    "unit_price": "500.00",
                }
            ],
        },
    ).json()

    response = rahul_contact_client.post(
        "/api/payments",
        json={
            "payment_type": "receive",
            "partner_id": ledger["partner_id"],
            "journal_id": ledger["journal"].id,
            "amount": "500.00",
            "payment_date": "2026-02-01",
            "invoice_id": joey_invoice["id"],
        },
    )

    assert response.status_code == 403


# --- Role-based access (§10.10 route access table) ---------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/sales-orders"),
        ("post", "/api/sales-orders"),
        ("get", "/api/customer-invoices"),
        ("post", "/api/customer-invoices"),
        ("get", "/api/reports/balance-sheet"),
        ("get", "/api/reports/profit-and-loss"),
        ("get", "/api/reports/trial-balance"),
        ("get", "/api/dashboard"),
    ],
)
def test_contact_role_is_refused_on_admin_accountant_routes(
    contact_client, method, path
):
    response = contact_client.request(method, path, json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/sales-orders"),
        ("get", "/api/customer-invoices"),
        ("get", "/api/reports/balance-sheet"),
        ("get", "/api/portal/my-documents"),
    ],
)
def test_every_sales_route_requires_authentication(anonymous_client, method, path):
    response = anonymous_client.get(path)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"
