"""Test fixtures.

Tests run against a real Postgres database, not SQLite. The things most worth
testing here — the three CHECK constraints, NUMERIC(14,2) precision, native
enum types, SELECT ... FOR UPDATE — either do not exist or behave differently
on SQLite, so testing there would prove nothing about production.

The test database is dropped and rebuilt at the start of every run, so the
schema always matches the models exactly and no stale table can survive a
schema change. Within a run, each test gets a transaction that is rolled back
at the end, so tests cannot see each other's rows.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    Numeric,
    String,
    Table,
    create_engine,
    text,
)
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  — registers every model with Base.metadata
from app.config import settings
from app.core.enums import (
    AccountGroup,
    AccountType,
    JournalType,
    PartnerType,
    UserRole,
)
from app.core.security import encode_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models.account import Account, Journal
from app.models.partner import Partner
from app.models.user import User

# A separate database, so a test run never touches development data.
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "urbanfurniture_test")


# TEMPORARY: models/sales.py is owned by a teammate and does not exist yet.
# payments.invoice_id carries a real FK to customer_invoices.id (§7.8), and
# budget achievement on an income line reads customer_invoice_lines, so both
# tables must exist in Base.metadata before create_all can emit the DDL.
#
# Guarded so it removes itself: once models/sales.py defines the real tables,
# "customer_invoices" is already in the metadata and this block is skipped.
# Delete it at that merge.
if "customer_invoices" not in Base.metadata.tables:
    Table(
        "customer_invoices",
        Base.metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("number", String(30)),
        Column("customer_id", BigInteger),
        Column("invoice_date", Date),
        Column("state", String(20)),
        Column("total_amount", Numeric(14, 2)),
    )
    Table(
        "customer_invoice_lines",
        Base.metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("customer_invoice_id", BigInteger),
        Column("analytic_account_id", BigInteger),
        Column("line_total", Numeric(14, 2)),
    )


def _test_database_url() -> str:
    """The configured DATABASE_URL with the database name swapped out."""
    return settings.database_url.rsplit("/", 1)[0] + "/" + TEST_DB_NAME


@pytest.fixture(scope="session")
def engine():
    """Drop, recreate and populate the test database's schema once per run."""
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :n AND pid <> pg_backend_pid()"
            ),
            {"n": TEST_DB_NAME},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    test_engine = create_engine(_test_database_url(), future=True)
    Base.metadata.create_all(bind=test_engine)

    yield test_engine
    test_engine.dispose()


@pytest.fixture()
def db(engine) -> Session:
    """One transaction per test, rolled back at the end. Nothing persists."""
    connection = engine.connect()
    transaction = connection.begin()
    # create_savepoint means a db.rollback() inside a test rolls back to a
    # SAVEPOINT rather than tearing down the fixture's outer transaction,
    # so a test may exercise rollback behaviour without breaking teardown.
    session = sessionmaker(
        bind=connection,
        autocommit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


def _make_user(
    db: Session, *, role: UserRole, login_id: str, partner_id: int | None = None
) -> User:
    user = User(
        name=f"Test {role.value}",
        login_id=login_id,
        email=f"{login_id}@example.com",
        password_hash=hash_password("Passw0rd!x"),
        role=role,
        partner_id=partner_id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def accountant(db: Session) -> User:
    """The role the ledger endpoints are built for (SPEC.md §9 roles)."""
    return _make_user(db, role=UserRole.accountant, login_id="acct01")


@pytest.fixture()
def client(db: Session, accountant: User) -> TestClient:
    """A TestClient authenticated as an accountant.

    get_db is overridden so that a router's db.commit() commits inside the
    outer transaction this fixture opened — the router behaves exactly as it
    does in production, and the fixture's rollback still undoes everything.

    Auth is NOT overridden. The client carries a real signed JWT and every
    request goes through get_current_user and require_role exactly as a
    browser's would, so the tests exercise the actual authorisation path
    rather than a stub of it (§12.2).
    """
    app.dependency_overrides[get_db] = lambda: db
    token = encode_token(
        user_id=accountant.id, role=accountant.role.value, partner_id=None
    )
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def anonymous_client(db: Session) -> TestClient:
    """A TestClient with no credentials at all."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def contact_client(db: Session) -> TestClient:
    """A TestClient authenticated as a portal (contact) user.

    §9's role table gives a contact read access to its own invoices and bills
    and nothing else, so the ledger endpoints must refuse it.
    """
    partner = Partner(name="Portal Co", partner_type=PartnerType.customer)
    db.add(partner)
    db.flush()
    user = _make_user(
        db, role=UserRole.contact, login_id="portal01", partner_id=partner.id
    )

    app.dependency_overrides[get_db] = lambda: db
    token = encode_token(user_id=user.id, role=user.role.value, partner_id=partner.id)
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def ledger(db: Session) -> dict:
    """A minimal chart of accounts, a journal, and one partner.

    Inserted directly rather than through the API because masters and seed.py
    are owned in parallel. Swap for the real seed data once they land.
    """
    debtors = Account(
        code="1200",
        name="Debtors A/c",
        account_group=AccountGroup.BALANCE_SHEET,
        account_type=AccountType.ASSET,
    )
    bank = Account(
        code="1000",
        name="Bank A/c",
        account_group=AccountGroup.BALANCE_SHEET,
        account_type=AccountType.BANK,
    )
    creditors = Account(
        code="2000",
        name="Creditors A/c",
        account_group=AccountGroup.BALANCE_SHEET,
        account_type=AccountType.LIABILITY,
    )
    purchase_expense = Account(
        code="5000",
        name="Purchase Expense A/c",
        account_group=AccountGroup.PROFIT_AND_LOSS,
        account_type=AccountType.EXPENSE,
    )
    other_expense = Account(
        code="5100",
        name="Other Expense A/c",
        account_group=AccountGroup.PROFIT_AND_LOSS,
        account_type=AccountType.OTHER_EXPENSE,
    )
    archived = Account(
        code="5900",
        name="Archived Expense A/c",
        account_group=AccountGroup.PROFIT_AND_LOSS,
        account_type=AccountType.OTHER_EXPENSE,
        is_archived=True,
    )
    db.add_all([debtors, bank, creditors, purchase_expense, other_expense, archived])
    db.flush()

    bank_journal = Journal(
        name="Bank", journal_type=JournalType.BANK, default_account_id=bank.id
    )
    db.add(bank_journal)
    db.flush()

    partner = Partner(name="Mr Rahul", partner_type=PartnerType.customer)
    db.add(partner)
    db.flush()

    return {
        "debtors": debtors,
        "bank": bank,
        "creditors": creditors,
        "purchase_expense": purchase_expense,
        "other_expense": other_expense,
        "archived": archived,
        "journal": bank_journal,
        "partner_id": partner.id,
        "ten_thousand": Decimal("10000.00"),
    }


@pytest.fixture()
def purchase_ledger(db: Session, ledger: dict) -> dict:
    """The purchase-cycle seed: a Purchase journal, a product, an analytic tag.

    Builds on the `ledger` fixture's chart of accounts so the two suites share
    one definition of Debtors/Creditors/Bank rather than drifting apart.
    """
    from app.core.enums import JournalType, ProductType
    from app.models.account import Journal
    from app.models.analytic import AnalyticAccount
    from app.models.product import Product

    purchase_journal = Journal(
        name="Purchase",
        journal_type=JournalType.PURCHASE,
        default_account_id=ledger["purchase_expense"].id,
    )
    db.add(purchase_journal)

    table = Product(
        name="Table", product_type=ProductType.goods, sales_price=0, cost_price=0
    )
    freight = Product(
        name="Freight", product_type=ProductType.service, sales_price=0, cost_price=0
    )
    db.add_all([table, freight])

    project_one = AnalyticAccount(name="Project 1")
    project_two = AnalyticAccount(name="Project 2")
    db.add_all([project_one, project_two])
    db.flush()

    return {
        **ledger,
        "purchase_journal": purchase_journal,
        "table": table,
        "freight": freight,
        "project_one": project_one,
        "project_two": project_two,
    }
