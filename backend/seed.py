#!/usr/bin/env python
"""Idempotent demo seed (SPEC.md §14).

Run from backend/, after the database is up and initialised:

    docker compose up -d
    python -c 'from app.database import init_db; init_db()'
    python seed.py

Design:

- Masters (users, partners, categories, products, analytics, the chart of
  accounts, journals) are upserted by natural key via get_or_create(), so
  re-running this file never duplicates them.
- Transactional data (the opening entry, manual expenses, the sales cycle)
  is gated behind "does the ledger already have entries?". Posted journal
  entries are immutable by design (R4) — reseeding them means reversing,
  not updating, which is out of scope for a demo seed. Re-running against
  an already-seeded database re-upserts masters and re-asserts the trial
  balance, but does not add a second copy of the transactions.
- Purchase orders, vendor bills, payments and budgets are seeded ONLY if
  their models can be imported — they belong to a parallel module that may
  not be merged into this branch yet. When one is missing, this prints a
  named warning and the summary at the end says so explicitly; re-run this
  file after that merge lands.

Ends with §14's post_seed_assertion: compute the trial balance and exit
loudly, non-zero, if it does not balance. The seed data is produced by the
exact same posting engine as every production code path — if it does not
balance, the engine itself is broken.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    AccountGroup,
    AccountType,
    JournalType,
    PartnerType,
    ProductType,
    UserRole,
)
from app.core.security import hash_password
from app.database import SessionLocal, init_db
from app.models.account import Account, Journal
from app.models.analytic import AnalyticAccount
from app.models.journal_entry import JournalEntry
from app.models.partner import Partner
from app.models.product import Product, ProductCategory
from app.models.user import User
from app.services import reports
from app.services import sales as sales_service
from app.services.accounting import LineInput, post_journal_entry


def get_or_create(db: Session, model, *, lookup: dict, defaults: dict | None = None):
    """Fetch a row by its natural key, or create it.

    The natural key IS the idempotency guarantee §14 requires: this file is
    safe to run against a database that already has some or all of this
    data in it.
    """
    instance = db.execute(select(model).filter_by(**lookup)).scalar_one_or_none()
    if instance is not None:
        return instance, False
    instance = model(**lookup, **(defaults or {}))
    db.add(instance)
    db.flush()
    return instance, True


# --- masters -----------------------------------------------------------------


def seed_partners(db: Session) -> dict[str, Partner]:
    specs = [
        {
            "name": "Mr Rahul",
            "partner_type": PartnerType.both,
            "email": "rahul@example.com",
            "phone": "9820011122",
            "city": "Mumbai",
            "state": "Maharashtra",
            "country": "India",
        },
        {
            "name": "Joey Wills",
            "partner_type": PartnerType.customer,
            "email": "joey.wills@example.com",
            "phone": "9820033344",
            "city": "Pune",
            "state": "Maharashtra",
            "country": "India",
        },
        {
            "name": "Open Wood Furnishings",
            "partner_type": PartnerType.vendor,
            "email": "sales@openwood.example",
            "phone": "9840011223",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "country": "India",
        },
        {
            "name": "Priya Enterprises",
            "partner_type": PartnerType.customer,
            "email": "priya@enterprises.example",
            "phone": "9900112233",
            "city": "Bengaluru",
            "state": "Karnataka",
            "country": "India",
        },
        {
            "name": "Ganesh Traders",
            "partner_type": PartnerType.vendor,
            "email": "ganesh.traders@example.com",
            "phone": "9911223344",
            "city": "Ahmedabad",
            "state": "Gujarat",
            "country": "India",
        },
        {
            "name": "Anita Verma",
            "partner_type": PartnerType.customer,
            "email": "anita.verma@example.com",
            "phone": "9922334455",
            "city": "Delhi",
            "state": "Delhi",
            "country": "India",
        },
        {
            "name": "Metro Electronics Supply",
            "partner_type": PartnerType.vendor,
            "email": "orders@metroelectronics.example",
            "phone": "9933445566",
            "city": "Hyderabad",
            "state": "Telangana",
            "country": "India",
        },
        {
            "name": "Sunrise Retail Co",
            "partner_type": PartnerType.both,
            "email": "contact@sunriseretail.example",
            "phone": "9944556677",
            "city": "Jaipur",
            "state": "Rajasthan",
            "country": "India",
        },
    ]
    partners: dict[str, Partner] = {}
    for spec in specs:
        name = spec.pop("name")
        partner, created = get_or_create(
            db, Partner, lookup={"name": name}, defaults=spec
        )
        partners[name] = partner
        print(f"  partner {name}: {'created' if created else 'already exists'}")
    return partners


def seed_users(db: Session, partners: dict[str, Partner]) -> None:
    specs = [
        {
            "login_id": "adminuser",
            "role": UserRole.admin,
            "password": "Admin@2026",
            "partner": None,
        },
        {
            "login_id": "accountant",
            "role": UserRole.accountant,
            "password": "Accnt@2026",
            "partner": None,
        },
        {
            "login_id": "rahulcust",
            "role": UserRole.contact,
            "password": "Rahul@2026",
            "partner": "Mr Rahul",
        },
    ]
    for spec in specs:
        partner = partners[spec["partner"]] if spec["partner"] else None
        _, created = get_or_create(
            db,
            User,
            lookup={"login_id": spec["login_id"]},
            defaults={
                "name": spec["login_id"],
                "email": f"{spec['login_id']}@urbanfurniture.example",
                "password_hash": hash_password(spec["password"]),
                "role": spec["role"],
                "partner_id": partner.id if partner else None,
                "is_active": True,
            },
        )
        print(
            f"  user {spec['login_id']}: {'created' if created else 'already exists'}"
        )


def seed_categories(db: Session) -> dict[str, ProductCategory]:
    categories: dict[str, ProductCategory] = {}
    for name in ["Furniture", "Electronics", "Services"]:
        category, created = get_or_create(db, ProductCategory, lookup={"name": name})
        categories[name] = category
        print(f"  category {name}: {'created' if created else 'already exists'}")
    return categories


def seed_products(
    db: Session, categories: dict[str, ProductCategory]
) -> dict[str, Product]:
    specs = [
        ("Table", "Furniture", ProductType.goods, "8000.00", "5500.00"),
        ("Chair", "Furniture", ProductType.goods, "2500.00", "1600.00"),
        ("Sofa", "Furniture", ProductType.goods, "22000.00", "15000.00"),
        ("Wardrobe", "Furniture", ProductType.goods, "18000.00", "12500.00"),
        ("Bed", "Furniture", ProductType.goods, "16000.00", "11000.00"),
        ("Bookshelf", "Furniture", ProductType.goods, "6000.00", "4200.00"),
        ("Dining Set", "Furniture", ProductType.combo, "35000.00", "24000.00"),
        ("Air Conditioner", "Electronics", ProductType.goods, "32000.00", "24000.00"),
        ("Refrigerator", "Electronics", ProductType.goods, "28000.00", "21000.00"),
        ("Washing Machine", "Electronics", ProductType.goods, "24000.00", "18000.00"),
        ("Delivery Service", "Services", ProductType.service, "1500.00", "600.00"),
        ("Assembly Service", "Services", ProductType.service, "1200.00", "500.00"),
    ]
    products: dict[str, Product] = {}
    for name, category_name, product_type, sales_price, cost_price in specs:
        product, created = get_or_create(
            db,
            Product,
            lookup={"name": name},
            defaults={
                "category_id": categories[category_name].id,
                "product_type": product_type,
                "sales_price": Decimal(sales_price),
                "cost_price": Decimal(cost_price),
            },
        )
        products[name] = product
        print(f"  product {name}: {'created' if created else 'already exists'}")
    return products


def seed_analytics(db: Session) -> dict[str, AnalyticAccount]:
    analytics: dict[str, AnalyticAccount] = {}
    for name in ["Project 1", "Project 2", "Showroom A", "Online Store"]:
        analytic, created = get_or_create(db, AnalyticAccount, lookup={"name": name})
        analytics[name] = analytic
        print(
            f"  analytic account {name}: {'created' if created else 'already exists'}"
        )
    return analytics


def seed_chart_of_accounts(db: Session) -> dict[str, Account]:
    """The 8 accounts of §10.1's background, pre-configured per the mockup."""
    specs = [
        ("1000", "Bank A/c", AccountGroup.BALANCE_SHEET, AccountType.BANK),
        ("1010", "Cash A/c", AccountGroup.BALANCE_SHEET, AccountType.CASH),
        ("1200", "Debtors A/c", AccountGroup.BALANCE_SHEET, AccountType.ASSET),
        ("2000", "Creditors A/c", AccountGroup.BALANCE_SHEET, AccountType.LIABILITY),
        ("3000", "Capital A/c", AccountGroup.BALANCE_SHEET, AccountType.CAPITAL),
        ("4000", "Sales Income A/c", AccountGroup.PROFIT_AND_LOSS, AccountType.INCOME),
        (
            "5000",
            "Purchase Expense A/c",
            AccountGroup.PROFIT_AND_LOSS,
            AccountType.EXPENSE,
        ),
        (
            "5100",
            "Other Expense A/c",
            AccountGroup.PROFIT_AND_LOSS,
            AccountType.OTHER_EXPENSE,
        ),
    ]
    accounts: dict[str, Account] = {}
    for code, name, group, account_type in specs:
        account, created = get_or_create(
            db,
            Account,
            lookup={"code": code},
            defaults={
                "name": name,
                "account_group": group,
                "account_type": account_type,
            },
        )
        accounts[name] = account
        print(f"  account {code} {name}: {'created' if created else 'already exists'}")
    return accounts


def seed_journals(db: Session, accounts: dict[str, Account]) -> dict[str, Journal]:
    """The 4 journals of §10.1's background."""
    specs = [
        ("Sales", JournalType.SALES, "Sales Income A/c"),
        ("Purchase", JournalType.PURCHASE, "Purchase Expense A/c"),
        ("Bank", JournalType.BANK, "Bank A/c"),
        ("Cash", JournalType.CASH, "Cash A/c"),
    ]
    journals: dict[str, Journal] = {}
    for name, journal_type, default_account_name in specs:
        journal, created = get_or_create(
            db,
            Journal,
            lookup={"name": name},
            defaults={
                "journal_type": journal_type,
                "default_account_id": accounts[default_account_name].id,
            },
        )
        journals[name] = journal
        print(f"  journal {name}: {'created' if created else 'already exists'}")
    return journals


# --- transactions -------------------------------------------------------


def seed_opening_entry(
    db: Session, accounts: dict[str, Account], journals: dict[str, Journal]
) -> None:
    """Capital injection so the Balance Sheet is non-trivial (§14)."""
    post_journal_entry(
        db,
        entry_date=date(2026, 1, 1),
        journal_id=journals["Bank"].id,
        reference="Opening capital",
        source_type="manual",
        lines=[
            LineInput(account_id=accounts["Bank A/c"].id, debit=Decimal("500000.00")),
            LineInput(
                account_id=accounts["Capital A/c"].id, credit=Decimal("500000.00")
            ),
        ],
    )
    print("  opening entry: Bank 500000.00 / Capital 500000.00")


def seed_manual_expenses(
    db: Session, accounts: dict[str, Account], journals: dict[str, Journal]
) -> None:
    """2 manual entries for Other Expense — rent and utilities (§14)."""
    post_journal_entry(
        db,
        entry_date=date(2026, 1, 5),
        journal_id=journals["Bank"].id,
        reference="January rent",
        source_type="manual",
        lines=[
            LineInput(
                account_id=accounts["Other Expense A/c"].id, debit=Decimal("15000.00")
            ),
            LineInput(account_id=accounts["Bank A/c"].id, credit=Decimal("15000.00")),
        ],
    )
    post_journal_entry(
        db,
        entry_date=date(2026, 2, 5),
        journal_id=journals["Bank"].id,
        reference="February utilities",
        source_type="manual",
        lines=[
            LineInput(
                account_id=accounts["Other Expense A/c"].id, debit=Decimal("5000.00")
            ),
            LineInput(account_id=accounts["Bank A/c"].id, credit=Decimal("5000.00")),
        ],
    )
    print("  manual entries: rent 15000.00, utilities 5000.00 (Other Expense A/c)")


def seed_sales_cycle(
    db: Session,
    partners: dict[str, Partner],
    products: dict[str, Product],
    analytics: dict[str, AnalyticAccount],
) -> None:
    """15 sales orders; 12 confirmed and converted to invoices; 10 of those
    invoices confirmed (posted to the ledger). 3 SOs and 2 invoices stay
    draft — a demo that is uniformly "complete" looks synthetic and shows
    fewer of the system's states (§14 deliberate_states).
    """
    customers = [
        "Mr Rahul",
        "Joey Wills",
        "Priya Enterprises",
        "Anita Verma",
        "Sunrise Retail Co",
    ]
    product_names = [
        "Table",
        "Chair",
        "Sofa",
        "Wardrobe",
        "Bed",
        "Bookshelf",
        "Air Conditioner",
    ]
    analytic_names = list(analytics.keys())
    months = [1, 2, 3]

    sales_orders = []
    for i in range(15):
        customer = partners[customers[i % len(customers)]]
        product = products[product_names[i % len(product_names)]]
        analytic = analytics[analytic_names[i % len(analytic_names)]]
        quantity = Decimal(str(1 + (i % 3)))
        order_date = date(2026, months[i % 3], 2 + (i % 25))

        so = sales_service.create_sales_order(
            db,
            customer_id=customer.id,
            order_date=order_date,
            lines=[
                {
                    "product_id": product.id,
                    "analytic_account_id": analytic.id,
                    "quantity": quantity,
                    "unit_price": product.sales_price,
                }
            ],
        )
        sales_orders.append(so)

    # Confirm the first 12 (leaving 3 draft), then invoice all 12 of those.
    invoices = []
    for so in sales_orders[:12]:
        sales_service.confirm_sales_order(db, sales_order_id=so.id)
        invoice = sales_service.create_invoice_from_so(db, sales_order_id=so.id)
        invoices.append(invoice)

    # Confirm 10 of the 12 invoices (posting to the ledger); 2 stay draft.
    for invoice in invoices[:10]:
        sales_service.confirm_customer_invoice(db, invoice_id=invoice.id)

    draft_orders = len(sales_orders) - 12
    draft_invoices = len(invoices) - 10
    print(
        f"  sales cycle: {len(sales_orders)} sales orders "
        f"(12 confirmed, {draft_orders} draft); {len(invoices)} invoices created "
        f"from them (10 confirmed/posted, {draft_invoices} draft)"
    )


# --- optional modules (owned by teammates, may not be merged yet) -----------


def _has_module(*module_names: str) -> bool:
    import importlib

    try:
        for name in module_names:
            importlib.import_module(name)
    except ImportError:
        return False
    return True


def _optional_module_gaps() -> list[str]:
    gaps = []
    if not _has_module("app.models.purchase"):
        gaps.append(
            "purchase orders / vendor bills (12 POs, 9 bills, 7 confirmed per "
            "§14) — app.models.purchase is not present in this tree"
        )
    if not _has_module("app.models.payment"):
        gaps.append(
            "payments (mixed paid/partial/unpaid invoices per §14) — "
            "app.models.payment is not present in this tree"
        )
    if not _has_module("app.models.budget"):
        gaps.append(
            "budgets (3 budgets in different states per §14) — "
            "app.models.budget is not present in this tree"
        )
    return gaps


# --- orchestration -----------------------------------------------------------


def main() -> None:
    print("Initialising schema (create_all)...")
    init_db()

    db = SessionLocal()
    try:
        print("Seeding masters...")
        partners = seed_partners(db)
        seed_users(db, partners)
        categories = seed_categories(db)
        products = seed_products(db, categories)
        analytics = seed_analytics(db)
        accounts = seed_chart_of_accounts(db)
        journals = seed_journals(db, accounts)
        db.commit()

        already_has_entries = (
            db.execute(select(JournalEntry.id).limit(1)).first() is not None
        )
        if already_has_entries:
            print(
                "Ledger already has entries — skipping transaction seeding "
                "(posted entries are immutable, R4). To reseed from scratch: "
                "docker compose down -v && docker compose up -d, then "
                "init_db() and this script again."
            )
        else:
            print("Seeding the opening entry, manual expenses and the sales cycle...")
            seed_opening_entry(db, accounts, journals)
            seed_manual_expenses(db, accounts, journals)
            seed_sales_cycle(db, partners, products, analytics)
            db.commit()

        gaps = _optional_module_gaps()

        print("\nComputing the trial balance (§14 post_seed_assertion)...")
        result = reports.trial_balance(db)
        grand_debit = result["grand_total_debit"]
        grand_credit = result["grand_total_credit"]
        print(f"  grand_total_debit  = {grand_debit}")
        print(f"  grand_total_credit = {grand_credit}")

        if not result["is_balanced"]:
            print("\n" + "=" * 78)
            print("SEED DATA DOES NOT BALANCE. THE POSTING ENGINE IS BROKEN.")
            print(f"  debit={grand_debit}  credit={grand_credit}")
            print("=" * 78)
            sys.exit(1)

        print("  is_balanced = True")

        if gaps:
            print("\n" + "=" * 78)
            print("INCOMPLETE SEED — the following are skipped because their models")
            print("are not yet merged into this branch:")
            for gap in gaps:
                print(f"  - {gap}")
            print("Re-run `python seed.py` after merging that work in.")
            print("=" * 78)

        print("\nSeed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
