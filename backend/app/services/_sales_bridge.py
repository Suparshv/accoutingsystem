"""TEMPORARY read-only handles on the sales tables.

models/sales.py is owned by a teammate and does not exist yet, but two things
this slice must do already read customer invoices:

  * budget achievement on an ``income`` line sums customer invoice lines;
  * a ``receive`` payment settles a customer invoice, so its state, total and
    amount due have to be readable.

These are plain Core tables in their OWN MetaData, so ``create_all`` never sees
them and never tries to create them — they describe tables the sales module
will own.

DELETE THIS MODULE at the sales merge, and replace the imports in
services/budgets.py and services/payments.py with the real CustomerInvoice and
CustomerInvoiceLine models. The queries change shape only; the logic in both
callers stays exactly as it is.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, MetaData, Numeric, String, Table

sales_metadata = MetaData()

customer_invoices = Table(
    "customer_invoices",
    sales_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("number", String(30)),
    Column("customer_id", BigInteger),
    Column("invoice_date", Date),
    Column("state", String(20)),
    Column("total_amount", Numeric(14, 2)),
)

customer_invoice_lines = Table(
    "customer_invoice_lines",
    sales_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("customer_invoice_id", BigInteger),
    Column("analytic_account_id", BigInteger),
    Column("line_total", Numeric(14, 2)),
)
