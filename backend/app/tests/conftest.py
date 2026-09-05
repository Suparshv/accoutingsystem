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
from sqlalchemy import BigInteger, Column, String, Table, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  — registers every model with Base.metadata
from app.config import settings
from app.core.enums import AccountGroup, AccountType, JournalType
from app.database import Base, get_db
from app.main import app
from app.models.account import Account, Journal

# A separate database, so a test run never touches development data.
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "urbanfurniture_test")

# TEMPORARY: models/partner.py is owned by a teammate and lands in the next
# merge. journal_entries.partner_id and journal_entry_lines.partner_id carry
# real foreign keys to partners.id, so SQLAlchemy needs a "partners" table in
# Base.metadata before it can emit the ledger DDL.
#
# The guard means this disappears by itself: once models/partner.py defines the
# real Partner, "partners" is already in the metadata and this block is skipped.
# Delete it at that merge.
if "partners" not in Base.metadata.tables:
    Table(
        "partners",
        Base.metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("name", String(200), nullable=False),
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


@pytest.fixture()
def client(db: Session) -> TestClient:
    """A TestClient whose requests share the test's transaction.

    get_db is overridden so that a router's db.commit() commits inside the
    outer transaction this fixture opened — the router behaves exactly as it
    does in production, and the fixture's rollback still undoes everything.
    """
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
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

    partner_id = db.execute(
        text("INSERT INTO partners (name) VALUES ('Mr Rahul') RETURNING id")
    ).scalar_one()

    return {
        "debtors": debtors,
        "bank": bank,
        "creditors": creditors,
        "purchase_expense": purchase_expense,
        "other_expense": other_expense,
        "archived": archived,
        "journal": bank_journal,
        "partner_id": partner_id,
        "ten_thousand": Decimal("10000.00"),
    }
