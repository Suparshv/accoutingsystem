"""Sales cycle business logic (SPEC.md §7.7, §8.2, §10.6).

Layering rule (AGENTS.md §3): routers parse, authorise, call one service
function and shape the response. All business logic lives here; the router
owns db.commit() so that, for confirm_customer_invoice, the invoice's state
change and its journal entry land in a single transaction (R3/P3) — exactly
the shape services/accounting.py and routers/journal_entries.py already use.

Numbering: sales_order ("S00001") and customer_invoice ("INV/2026/0001") are
sequences this module owns. services/sequences.py is off-limits to modify
(its only public entry point covers journal_entry numbering, whose format
string is hardcoded for that one shape), so the row-locking algorithm from
§12.4 is duplicated here rather than reaching into that module's private
helpers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import DocumentState, JournalType
from app.core.errors import AppError, NotFoundError
from app.models.account import Account, Journal
from app.models.sales import (
    CustomerInvoice,
    CustomerInvoiceLine,
    SalesOrder,
    SalesOrderLine,
)
from app.models.sequence import Sequence
from app.services.accounting import LineInput, post_journal_entry

ZERO = Decimal("0.00")

# The canonical control accounts and journal this module reads by convention,
# matching the chart of accounts every §10 scenario and seed.py assume
# (§10.1 background: code 1200 = Debtors A/c).
DEBTORS_ACCOUNT_CODE = "1200"

SALES_ORDER_SEQUENCE = "sales_order"
SALES_ORDER_PREFIX = "S"
CUSTOMER_INVOICE_SEQUENCE = "customer_invoice"
CUSTOMER_INVOICE_PREFIX = "INV"


# --- sequences ---------------------------------------------------------------


def _reserve_sequence_number(
    db: Session, *, name: str, prefix: str, year_scoped: bool
) -> str:
    """Reserve the next number for a named sequence (§12.4 algorithm).

    SELECT ... FOR UPDATE locks the row; a concurrent caller blocks until this
    transaction commits, so two simultaneous confirms can never receive the
    same number (§10.11).
    """
    stmt = select(Sequence).where(Sequence.name == name).with_for_update()
    row = db.execute(stmt).scalar_one_or_none()
    year = date.today().year if year_scoped else 0

    if row is None:
        try:
            with db.begin_nested():
                row = Sequence(name=name, prefix=prefix, year=year, last_number=0)
                db.add(row)
                db.flush()
        except IntegrityError:
            # Lost the race to create the row — re-read the winner's row.
            row = db.execute(stmt).scalar_one()

    if year_scoped and row.year != year:
        row.year = year
        row.last_number = 0

    row.last_number += 1
    db.flush()

    if year_scoped:
        return f"{row.prefix}/{row.year}/{row.last_number:04d}"
    return f"{row.prefix}{row.last_number:05d}"


def _next_sales_order_number(db: Session) -> str:
    return _reserve_sequence_number(
        db, name=SALES_ORDER_SEQUENCE, prefix=SALES_ORDER_PREFIX, year_scoped=False
    )


def _next_customer_invoice_number(db: Session) -> str:
    return _reserve_sequence_number(
        db,
        name=CUSTOMER_INVOICE_SEQUENCE,
        prefix=CUSTOMER_INVOICE_PREFIX,
        year_scoped=True,
    )


# --- control lookups -----------------------------------------------------


def _get_debtors_account_id(db: Session) -> int:
    account = db.execute(
        select(Account).where(Account.code == DEBTORS_ACCOUNT_CODE)
    ).scalar_one_or_none()
    if account is None:
        raise NotFoundError(
            f"No control account with code '{DEBTORS_ACCOUNT_CODE}' (Debtors) "
            "is configured. Seed the chart of accounts first."
        )
    return account.id


def _get_sales_journal(db: Session) -> Journal:
    journal = (
        db.execute(select(Journal).where(Journal.journal_type == JournalType.SALES))
        .scalars()
        .first()
    )
    if journal is None:
        raise NotFoundError("No Sales journal is configured. Seed the journals first.")
    return journal


def _get_sales_journal_default_account_id(db: Session) -> int:
    return _get_sales_journal(db).default_account_id


# --- line/total helpers -------------------------------------------------


def compute_line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    """quantity x unit_price, rounded to the money precision (R6, §11).

    Half away from zero, stated explicitly rather than left to a default:
    Decimal.quantize defaults to ROUND_HALF_EVEN while Postgres NUMERIC
    rounds half away from zero, so the two cycles used to round a half-paise
    tie in opposite directions. The document forms now show this same product
    live while you type (lib/money.ts::multiplyMinorUnits), which makes any
    disagreement visible as a figure that changes on save.
    """
    return (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def recompute_total(lines: list) -> Decimal:
    """A document's total is the sum of its lines. Never client-supplied."""
    return sum((line.line_total for line in lines), ZERO)


# --- sales orders ----------------------------------------------------------


def create_sales_order(
    db: Session, *, customer_id: int, order_date: date, lines: list[dict]
) -> SalesOrder:
    """Create a draft sales order. Every line_total is computed here, not
    trusted from the caller's dict, however it was built (§10.5's rule
    mirrored on the sales side)."""
    so = SalesOrder(
        number=_next_sales_order_number(db),
        customer_id=customer_id,
        order_date=order_date,
        state=DocumentState.DRAFT,
    )
    for index, line in enumerate(lines):
        quantity = line["quantity"]
        unit_price = line["unit_price"]
        so.lines.append(
            SalesOrderLine(
                product_id=line["product_id"],
                analytic_account_id=line.get("analytic_account_id"),
                quantity=quantity,
                unit_price=unit_price,
                line_total=compute_line_total(quantity, unit_price),
                sequence=(index + 1) * 10,
            )
        )
    so.total_amount = recompute_total(so.lines)
    db.add(so)
    db.flush()
    return so


def confirm_sales_order(db: Session, *, sales_order_id: int) -> SalesOrder:
    """State change ONLY — a sales order produces no journal entry (§7.7).

    Raises:
        NotFoundError: no such sales order.
        AppError(409, ALREADY_CONFIRMED): the order is not in draft.
        AppError(422, NO_LINES): the order has no lines to confirm.
    """
    so = db.get(SalesOrder, sales_order_id)
    if so is None:
        raise NotFoundError(f"Sales order {sales_order_id} does not exist.")
    if so.state != DocumentState.DRAFT:
        raise AppError(
            409,
            "ALREADY_CONFIRMED",
            "This sales order is already confirmed or cancelled.",
        )
    if not so.lines:
        raise AppError(422, "NO_LINES", "At least one line is required to confirm.")

    so.state = DocumentState.CONFIRMED
    db.flush()
    return so


def create_invoice_from_so(
    db: Session, *, sales_order_id: int, invoice_date: date | None = None
) -> CustomerInvoice:
    """Copy vendor/lines/analytics/qty/price from a confirmed SO into a draft
    invoice, mirroring §10.5's create-bill behaviour on the sales side.

    ``invoice_date`` defaults to today, matching real usage (you invoice on
    the day you raise the invoice, regardless of when the order was placed).
    seed.py passes an explicit historical date so demo invoices land inside
    the period any income-side budget measures achievement against.

    Raises:
        NotFoundError: no such sales order.
        AppError(409, SO_NOT_CONFIRMED): the order is still draft.
        AppError(409, INVOICE_ALREADY_EXISTS): this SO already has an invoice.
    """
    so = db.get(SalesOrder, sales_order_id)
    if so is None:
        raise NotFoundError(f"Sales order {sales_order_id} does not exist.")
    if so.state != DocumentState.CONFIRMED:
        raise AppError(
            409,
            "SO_NOT_CONFIRMED",
            "The sales order must be confirmed before it can be invoiced.",
        )
    existing = db.execute(
        select(CustomerInvoice).where(CustomerInvoice.source_so_id == so.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            409, "INVOICE_ALREADY_EXISTS", "This sales order already has an invoice."
        )

    default_account_id = _get_sales_journal_default_account_id(db)

    invoice = CustomerInvoice(
        number=_next_customer_invoice_number(db),
        customer_id=so.customer_id,
        invoice_date=invoice_date or date.today(),
        state=DocumentState.DRAFT,
        source_so_id=so.id,
    )
    for line in so.lines:
        invoice.lines.append(
            CustomerInvoiceLine(
                product_id=line.product_id,
                account_id=default_account_id,
                analytic_account_id=line.analytic_account_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
                sequence=line.sequence,
            )
        )
    invoice.total_amount = recompute_total(invoice.lines)
    db.add(invoice)
    db.flush()
    return invoice


# --- customer invoices -------------------------------------------------------


def create_customer_invoice(
    db: Session,
    *,
    customer_id: int,
    invoice_reference: str | None,
    invoice_date: date,
    due_date: date | None,
    lines: list[dict],
) -> CustomerInvoice:
    """Create a draft invoice directly (no source sales order)."""
    invoice = CustomerInvoice(
        number=_next_customer_invoice_number(db),
        customer_id=customer_id,
        invoice_reference=invoice_reference,
        invoice_date=invoice_date,
        due_date=due_date,
        state=DocumentState.DRAFT,
        source_so_id=None,
    )
    for index, line in enumerate(lines):
        quantity = line["quantity"]
        unit_price = line["unit_price"]
        invoice.lines.append(
            CustomerInvoiceLine(
                product_id=line["product_id"],
                account_id=line["account_id"],
                analytic_account_id=line.get("analytic_account_id"),
                quantity=quantity,
                unit_price=unit_price,
                line_total=compute_line_total(quantity, unit_price),
                sequence=(index + 1) * 10,
            )
        )
    invoice.total_amount = recompute_total(invoice.lines)
    db.add(invoice)
    db.flush()
    return invoice


def confirm_customer_invoice(
    db: Session, *, invoice_id: int
) -> tuple[CustomerInvoice, object]:
    """★ Atomic: state=confirmed + a balanced journal entry posted (§8.2, P3).

    Builds exactly ONE debit line to Debtors for the invoice total, and ONE
    credit line PER DISTINCT account_id across the invoice's lines (grouped
    and summed) — the mirror image of confirm_vendor_bill, debit and credit
    sides reversed. Does not commit: the caller commits once so the state
    change and the journal entry land in one transaction (R3/P3).

    Raises:
        NotFoundError: no such invoice.
        AppError(409, ALREADY_CONFIRMED): the invoice is not in draft.
        AppError(422, NO_LINES): the invoice has no lines to confirm.
        AppError(409, INVALID_STATE_TRANSITION): the source sales order (if
            any) has been cancelled since this invoice was created.
        Whatever services.accounting.post_journal_entry raises if, somehow,
        the built lines fail to balance (they cannot, by construction, but
        the engine is still the one place that checks).
    """
    invoice = db.get(CustomerInvoice, invoice_id)
    if invoice is None:
        raise NotFoundError(f"Customer invoice {invoice_id} does not exist.")
    if invoice.state != DocumentState.DRAFT:
        raise AppError(
            409, "ALREADY_CONFIRMED", "This invoice is already confirmed or cancelled."
        )
    if not invoice.lines:
        raise AppError(422, "NO_LINES", "At least one line is required to confirm.")

    # A cancelled SO can leave behind a still-draft invoice (cancel_sales_order
    # only cascades when the invoice is draft AND blocks when it's confirmed —
    # this closes the remaining gap: nothing previously stopped that orphaned
    # draft invoice from later being confirmed and posted for a sale the
    # business has already said didn't happen).
    if invoice.source_so_id is not None:
        source_so = db.get(SalesOrder, invoice.source_so_id)
        if source_so is not None and source_so.state == DocumentState.CANCELLED:
            raise AppError(
                409,
                "INVALID_STATE_TRANSITION",
                "Cannot confirm: source sales order has been cancelled.",
            )

    debtors_account_id = _get_debtors_account_id(db)
    sales_journal = _get_sales_journal(db)

    grouped: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for line in invoice.lines:
        grouped[line.account_id] += line.line_total

    lines = [
        LineInput(
            account_id=debtors_account_id,
            debit=invoice.total_amount,
            partner_id=invoice.customer_id,
            label=invoice.number,
        )
    ]
    lines.extend(
        LineInput(account_id=account_id, credit=amount, partner_id=invoice.customer_id)
        for account_id, amount in grouped.items()
    )

    entry = post_journal_entry(
        db,
        entry_date=invoice.invoice_date,
        journal_id=sales_journal.id,
        lines=lines,
        partner_id=invoice.customer_id,
        reference=invoice.invoice_reference,
        source_type="customer_invoice",
        source_id=invoice.id,
        number=invoice.number,
    )

    invoice.state = DocumentState.CONFIRMED
    invoice.journal_entry_id = entry.id
    db.flush()

    return invoice, entry


def cancel_sales_order(db: Session, so: SalesOrder) -> SalesOrder:
    """A sales order itself has no ledger effect in any state, but a linked
    customer invoice might — so cancelling the order must resolve that link
    rather than ignore it (mirrors services.purchase.cancel_purchase_order
    exactly):

    - no linked invoice, or the invoice is already cancelled: cancel the SO,
      nothing else to do.
    - the invoice is still draft (journal_entry_id is null — no ledger
      effect posted yet): cascade-cancel it in the same transaction. Safe,
      since nothing has been posted for it.
    - the invoice is confirmed (its journal entry is posted and immutable,
      R4): refuse. Undoing a posted entry needs a reversal (the P2 path,
      not built) — silently cancelling the SO here would leave the ledger
      asserting income for a sale the business now says never happened.

    Raises:
        AppError(409, INVALID_STATE_TRANSITION): a confirmed invoice exists
            for this order.
    """
    invoice = db.execute(
        select(CustomerInvoice).where(CustomerInvoice.source_so_id == so.id)
    ).scalar_one_or_none()

    if invoice is not None:
        if invoice.state == DocumentState.CONFIRMED:
            raise AppError(
                409,
                "INVALID_STATE_TRANSITION",
                "Cannot cancel: invoice already confirmed and posted. "
                "Reverse the invoice's journal entry instead.",
            )
        if invoice.state == DocumentState.DRAFT:
            cancel_customer_invoice(db, invoice)

    so.state = DocumentState.CANCELLED
    db.flush()
    return so


def cancel_customer_invoice(db: Session, invoice: CustomerInvoice) -> CustomerInvoice:
    """Only a draft invoice may be cancelled.

    A confirmed invoice has a posted journal entry, and posted entries are
    immutable (R4) — mirrors services.purchase.cancel_vendor_bill exactly.
    """
    if invoice.state is DocumentState.CONFIRMED:
        raise AppError(
            409,
            "INVALID_STATE_TRANSITION",
            "A confirmed invoice cannot be cancelled; its journal entry is "
            "posted and immutable. Reverse the entry instead.",
        )

    invoice.state = DocumentState.CANCELLED
    db.flush()
    return invoice
