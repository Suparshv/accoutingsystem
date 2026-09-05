"""★ Posting engine tests — every scenario in SPEC.md §10.4.

These are the highest-value tests in the repository. The posting engine is the
one writer to the ledger, so every guarantee the system makes about financial
correctness is a guarantee about this module.

Each test names the scenario it covers.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.enums import JournalEntryState
from app.core.errors import (
    AccountArchivedError,
    AccountNotFoundError,
    InvalidLineError,
    JournalNotFoundError,
    UnbalancedEntryError,
)
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.services.accounting import LineInput, post_journal_entry

TODAY = date(2026, 2, 1)


def _count_entries(db) -> int:
    return db.execute(select(func.count()).select_from(JournalEntry)).scalar_one()


def _count_lines(db) -> int:
    return db.execute(select(func.count()).select_from(JournalEntryLine)).scalar_one()


def _balanced_lines(ledger, amount: str = "100.00") -> list[LineInput]:
    return [
        LineInput(account_id=ledger["debtors"].id, debit=Decimal(amount)),
        LineInput(account_id=ledger["bank"].id, credit=Decimal(amount)),
    ]


# --- Scenario: A balanced two-line entry posts successfully ------------------


def test_balanced_two_line_entry_posts(db, ledger):
    entry = post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        partner_id=ledger["partner_id"],
        lines=[
            LineInput(
                account_id=ledger["debtors"].id,
                debit=Decimal("10000.00"),
                partner_id=ledger["partner_id"],
            ),
            LineInput(account_id=ledger["bank"].id, credit=Decimal("10000.00")),
        ],
    )

    assert entry.state is JournalEntryState.POSTED
    assert entry.total_amount == Decimal("10000.00")
    assert entry.number
    assert len(entry.lines) == 2
    # Lines are numbered 10, 20, 30...
    assert [line.sequence for line in entry.lines] == [10, 20]


def test_entry_numbers_are_unique(db, ledger):
    """And the entry has a unique number — two entries, two distinct numbers."""
    first = post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        lines=_balanced_lines(ledger),
    )
    second = post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        lines=_balanced_lines(ledger),
    )

    assert first.number != second.number
    assert first.number.startswith("JE/")


def test_trial_balance_holds_after_posting(db, ledger):
    """GET /reports/trial-balance reports is_balanced = true.

    The reports endpoint is a later phase, so this asserts the invariant it
    will read: across every posted line, SUM(debit) == SUM(credit).
    """
    post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        lines=[
            LineInput(account_id=ledger["debtors"].id, debit=Decimal("10000.00")),
            LineInput(account_id=ledger["bank"].id, credit=Decimal("10000.00")),
        ],
    )

    totals = db.execute(
        select(
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        )
    ).one()

    assert totals[0] == totals[1]


# --- Scenario: An unbalanced entry is rejected entirely ----------------------


def test_unbalanced_entry_is_rejected_with_no_partial_write(db, ledger):
    """The word "entirely" is the point — a partial write is the worst outcome."""
    entries_before = _count_entries(db)
    lines_before = _count_lines(db)

    with pytest.raises(UnbalancedEntryError) as excinfo:
        post_journal_entry(
            db,
            entry_date=TODAY,
            journal_id=ledger["journal"].id,
            lines=[
                LineInput(account_id=ledger["debtors"].id, debit=Decimal("10000.00")),
                LineInput(account_id=ledger["bank"].id, credit=Decimal("9000.00")),
            ],
        )

    assert excinfo.value.code == "UNBALANCED_ENTRY"
    assert excinfo.value.status_code == 422
    assert excinfo.value.details == {
        "total_debit": "10000.00",
        "total_credit": "9000.00",
        "difference": "1000.00",
    }

    # NO journal entry row and NO journal entry line row was created.
    db.flush()
    assert _count_entries(db) == entries_before
    assert _count_lines(db) == lines_before


# --- Scenario: A balanced entry with more than two lines posts ---------------


def test_three_line_entry_posts(db, ledger):
    entry = post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        lines=[
            LineInput(
                account_id=ledger["purchase_expense"].id, debit=Decimal("6000.00")
            ),
            LineInput(account_id=ledger["other_expense"].id, debit=Decimal("1000.00")),
            LineInput(account_id=ledger["creditors"].id, credit=Decimal("7000.00")),
        ],
    )

    assert len(entry.lines) == 3
    assert entry.total_amount == Decimal("7000.00")


# --- Scenario: A line cannot carry both a debit and a credit ----------------


def test_line_with_both_sides_is_rejected(db, ledger):
    with pytest.raises(InvalidLineError) as excinfo:
        post_journal_entry(
            db,
            entry_date=TODAY,
            journal_id=ledger["journal"].id,
            lines=[
                LineInput(account_id=ledger["debtors"].id, debit=Decimal("500.00")),
                LineInput(
                    account_id=ledger["bank"].id,
                    debit=Decimal("500.00"),
                    credit=Decimal("500.00"),
                ),
            ],
        )

    assert excinfo.value.code == "INVALID_LINE"
    # The payload names the 0-based index of the offending line.
    assert excinfo.value.details == {"line_index": 1}


# --- Scenario: A line cannot be zero on both sides --------------------------


def test_line_with_both_sides_zero_is_rejected(db, ledger):
    with pytest.raises(InvalidLineError) as excinfo:
        post_journal_entry(
            db,
            entry_date=TODAY,
            journal_id=ledger["journal"].id,
            lines=[
                LineInput(account_id=ledger["debtors"].id, debit=Decimal("100.00")),
                LineInput(account_id=ledger["bank"].id, credit=Decimal("100.00")),
                LineInput(account_id=ledger["other_expense"].id),
            ],
        )

    assert excinfo.value.code == "INVALID_LINE"
    assert excinfo.value.details == {"line_index": 2}


# --- Scenario: Negative amounts are rejected --------------------------------


def test_negative_debit_is_rejected(db, ledger):
    with pytest.raises(InvalidLineError) as excinfo:
        post_journal_entry(
            db,
            entry_date=TODAY,
            journal_id=ledger["journal"].id,
            lines=[
                LineInput(account_id=ledger["debtors"].id, debit=Decimal("-500.00")),
                LineInput(account_id=ledger["bank"].id, credit=Decimal("-500.00")),
            ],
        )

    assert excinfo.value.details == {"line_index": 0}


def test_negative_credit_is_rejected(db, ledger):
    with pytest.raises(InvalidLineError) as excinfo:
        post_journal_entry(
            db,
            entry_date=TODAY,
            journal_id=ledger["journal"].id,
            lines=[
                LineInput(account_id=ledger["debtors"].id, debit=Decimal("500.00")),
                LineInput(account_id=ledger["bank"].id, credit=Decimal("-500.00")),
            ],
        )

    assert excinfo.value.details == {"line_index": 1}


# --- The three CHECK constraints are real, not just app-level checks ---------
# These bypass the engine deliberately: they assert the database itself would
# refuse the row even if some future code forgot to validate.


def _posted_entry_id(db, ledger) -> int:
    entry = post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        lines=_balanced_lines(ledger, "1.00"),
    )
    return entry.id


def _insert_raw_line(db, ledger, *, debit: str, credit: str) -> None:
    entry_id = _posted_entry_id(db, ledger)
    with db.begin_nested():
        db.execute(
            JournalEntryLine.__table__.insert().values(
                journal_entry_id=entry_id,
                account_id=ledger["bank"].id,
                debit=Decimal(debit),
                credit=Decimal(credit),
                sequence=10,
            )
        )


def test_database_rejects_a_two_sided_line(db, ledger):
    """ck_jel_one_side_only."""
    with pytest.raises(IntegrityError) as excinfo:
        _insert_raw_line(db, ledger, debit="500.00", credit="500.00")

    assert "ck_jel_one_side_only" in str(excinfo.value.orig)


def test_database_rejects_a_negative_line(db, ledger):
    """ck_jel_non_negative."""
    with pytest.raises(IntegrityError) as excinfo:
        _insert_raw_line(db, ledger, debit="-500.00", credit="0.00")

    assert "ck_jel_non_negative" in str(excinfo.value.orig)


def test_database_rejects_a_zero_line(db, ledger):
    """ck_jel_not_both_zero."""
    with pytest.raises(IntegrityError) as excinfo:
        _insert_raw_line(db, ledger, debit="0.00", credit="0.00")

    assert "ck_jel_not_both_zero" in str(excinfo.value.orig)


# --- Scenario: A single-line entry is rejected ------------------------------


def test_single_line_entry_is_rejected(db, ledger):
    with pytest.raises(UnbalancedEntryError) as excinfo:
        post_journal_entry(
            db,
            entry_date=TODAY,
            journal_id=ledger["journal"].id,
            lines=[LineInput(account_id=ledger["debtors"].id, debit=Decimal("100.00"))],
        )

    assert excinfo.value.code == "UNBALANCED_ENTRY"
    assert "at least two lines" in excinfo.value.message


# --- Scenario: An entry with no lines is rejected ---------------------------


def test_empty_entry_is_rejected(db, ledger):
    with pytest.raises(UnbalancedEntryError) as excinfo:
        post_journal_entry(
            db, entry_date=TODAY, journal_id=ledger["journal"].id, lines=[]
        )

    assert excinfo.value.message == "A journal entry must have at least two lines"


# --- Scenario: Posting to an archived account is rejected -------------------


def test_archived_account_is_rejected(db, ledger):
    with pytest.raises(AccountArchivedError) as excinfo:
        post_journal_entry(
            db,
            entry_date=TODAY,
            journal_id=ledger["journal"].id,
            lines=[
                LineInput(account_id=ledger["archived"].id, debit=Decimal("100.00")),
                LineInput(account_id=ledger["bank"].id, credit=Decimal("100.00")),
            ],
        )

    assert excinfo.value.code == "ACCOUNT_ARCHIVED"
    assert excinfo.value.status_code == 422


def test_unknown_account_is_rejected(db, ledger):
    with pytest.raises(AccountNotFoundError) as excinfo:
        post_journal_entry(
            db,
            entry_date=TODAY,
            journal_id=ledger["journal"].id,
            lines=[
                LineInput(account_id=999_999, debit=Decimal("100.00")),
                LineInput(account_id=ledger["bank"].id, credit=Decimal("100.00")),
            ],
        )

    assert excinfo.value.code == "ACCOUNT_NOT_FOUND"


def test_unknown_journal_is_rejected(db, ledger):
    with pytest.raises(JournalNotFoundError) as excinfo:
        post_journal_entry(
            db,
            entry_date=TODAY,
            journal_id=999_999,
            lines=_balanced_lines(ledger),
        )

    assert excinfo.value.code == "JOURNAL_NOT_FOUND"


# --- Scenario: Decimal precision survives a round trip ----------------------


def test_decimal_precision_survives_round_trip(db, ledger):
    """199.99 in, exactly 199.99 back out of Postgres. Guards against floats."""
    entry = post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        lines=[
            LineInput(account_id=ledger["debtors"].id, debit=Decimal("199.99")),
            LineInput(account_id=ledger["bank"].id, credit=Decimal("199.99")),
        ],
    )
    entry_id = entry.id
    db.flush()
    db.expire_all()

    reloaded = db.get(JournalEntry, entry_id)
    assert isinstance(reloaded.lines[0].debit, Decimal)
    assert reloaded.lines[0].debit == Decimal("199.99")
    assert str(reloaded.lines[0].debit) == "199.99"
    assert reloaded.total_amount == Decimal("199.99")


# --- Scenario: Many small lines still sum exactly ---------------------------


def test_ten_small_lines_sum_exactly(db, ledger):
    """10 x 199.99 == 1999.90 exactly. In float this drifts and would 422."""
    lines = [
        LineInput(account_id=ledger["purchase_expense"].id, debit=Decimal("199.99"))
        for _ in range(10)
    ]
    lines.append(
        LineInput(account_id=ledger["creditors"].id, credit=Decimal("1999.90"))
    )

    entry = post_journal_entry(
        db, entry_date=TODAY, journal_id=ledger["journal"].id, lines=lines
    )

    assert len(entry.lines) == 11
    assert entry.total_amount == Decimal("1999.90")
    assert [line.sequence for line in entry.lines][:3] == [10, 20, 30]


# --- Scenario: A posted entry cannot be deleted or edited -------------------


def test_no_delete_route_for_journal_entries(client, ledger, db):
    """DELETE /journal-entries/{id} is 405 — immutability by absence of API."""
    entry = post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        lines=_balanced_lines(ledger),
    )
    db.flush()

    response = client.delete(f"/api/journal-entries/{entry.id}")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_no_put_route_for_journal_entries(client, ledger, db):
    """No PUT route exists either. The entry cannot be edited through the API."""
    entry = post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        lines=_balanced_lines(ledger),
    )
    db.flush()

    response = client.put(f"/api/journal-entries/{entry.id}", json={})

    assert response.status_code == 405


# --- The engine flushes, the caller commits ---------------------------------


def test_engine_does_not_commit(db, ledger):
    """R3: post_journal_entry flushes; the CALLER owns the commit.

    Rolling back straight after the call must leave nothing behind. If the
    engine had committed, the row would survive this rollback — which is
    exactly the bug that silently produces confirmed documents with no ledger
    entry.
    """
    post_journal_entry(
        db,
        entry_date=TODAY,
        journal_id=ledger["journal"].id,
        lines=[
            LineInput(account_id=ledger["debtors"].id, debit=Decimal("42.00")),
            LineInput(account_id=ledger["bank"].id, credit=Decimal("42.00")),
        ],
    )

    assert _count_entries(db) == 1
    db.rollback()
    assert _count_entries(db) == 0


# --- The HTTP layer end to end ----------------------------------------------


def test_post_journal_entry_endpoint_creates_a_posted_entry(client, ledger):
    """POST /journal-entries: 201, state posted, money as strings on the wire."""
    response = client.post(
        "/api/journal-entries",
        json={
            "entry_date": "2026-02-01",
            "journal_id": ledger["journal"].id,
            "partner_id": ledger["partner_id"],
            "reference": "Opening balance",
            "lines": [
                {
                    "account_id": ledger["debtors"].id,
                    "partner_id": ledger["partner_id"],
                    "debit": "10000.00",
                    "credit": "0.00",
                },
                {
                    "account_id": ledger["bank"].id,
                    "debit": "0.00",
                    "credit": "10000.00",
                },
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "posted"
    assert body["number"].startswith("JE/")
    # Money is a STRING on the wire, and carries exactly two decimal places.
    assert body["total_amount"] == "10000.00"
    assert body["lines"][0]["debit"] == "10000.00"
    assert body["lines"][0]["account_name"] == "Debtors A/c"
    assert body["lines"][0]["partner_name"] == "Mr Rahul"
    assert body["journal_name"] == "Bank"
    assert "999" not in body["total_amount"]


def test_post_unbalanced_entry_endpoint_returns_the_error_envelope(client, ledger):
    """422 UNBALANCED_ENTRY in the §12.1 envelope, and nothing was written."""
    response = client.post(
        "/api/journal-entries",
        json={
            "entry_date": "2026-02-01",
            "journal_id": ledger["journal"].id,
            "lines": [
                {"account_id": ledger["debtors"].id, "debit": "10000.00"},
                {"account_id": ledger["bank"].id, "credit": "9000.00"},
            ],
        },
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "UNBALANCED_ENTRY"
    assert error["details"] == {
        "total_debit": "10000.00",
        "total_credit": "9000.00",
        "difference": "1000.00",
    }
    assert error["correlation_id"]

    assert client.get("/api/journal-entries").json()["total"] == 0


def test_post_rejects_a_third_decimal_place(client, ledger):
    """Reject rather than silently round — a client bug should surface (§11)."""
    response = client.post(
        "/api/journal-entries",
        json={
            "entry_date": "2026-02-01",
            "journal_id": ledger["journal"].id,
            "lines": [
                {"account_id": ledger["debtors"].id, "debit": "100.005"},
                {"account_id": ledger["bank"].id, "credit": "100.005"},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_journal_entries_endpoint_returns_the_mockup_columns(client, ledger):
    """GET /journal-entries: exactly the columns in the mockup's list view."""
    client.post(
        "/api/journal-entries",
        json={
            "entry_date": "2026-02-01",
            "journal_id": ledger["journal"].id,
            "partner_id": ledger["partner_id"],
            "lines": [
                {"account_id": ledger["debtors"].id, "debit": "10000.00"},
                {"account_id": ledger["bank"].id, "credit": "10000.00"},
            ],
        },
    )

    response = client.get("/api/journal-entries")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20

    row = body["items"][0]
    assert set(row) == {
        "id",
        "date",
        "number",
        "partner_name",
        "journal_name",
        "total_amount",
        "state",
    }
    assert row["date"] == "2026-02-01"
    assert row["partner_name"] == "Mr Rahul"
    assert row["journal_name"] == "Bank"
    assert row["total_amount"] == "10000.00"
    assert row["state"] == "posted"


def test_get_journal_entry_detail_resolves_names(client, ledger):
    created = client.post(
        "/api/journal-entries",
        json={
            "entry_date": "2026-02-01",
            "journal_id": ledger["journal"].id,
            "lines": [
                {"account_id": ledger["purchase_expense"].id, "debit": "6000.00"},
                {"account_id": ledger["creditors"].id, "credit": "6000.00"},
            ],
        },
    ).json()

    response = client.get(f"/api/journal-entries/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert [line["account_name"] for line in body["lines"]] == [
        "Purchase Expense A/c",
        "Creditors A/c",
    ]
    assert body["source_type"] == "manual"


def test_missing_journal_entry_returns_404_not_500(client, ledger):
    response = client.get("/api/journal-entries/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
