#!/usr/bin/env python
"""Idempotent demo seed (SPEC.md §14).

Run from backend/, after the database is up and initialised:

    docker compose up -d
    python -c 'from app.database import init_db; init_db()'
    python seed.py

THE STORY (for the hackathon walkthrough): Urban Furniture, a furniture
trading business, across Q1 2026 (Jan-Mar) plus an April continuation into
Q2, so the dataset does not look like it stopped dead at the quarter end.
Revenue grows every month.
Purchase volume grows to match. March carries a one-off equipment-repair
expense, so its margin is a little tighter than February's even though it
is the best revenue month of the quarter. Three Q1 budgets tell three
different stories: Showroom Expansion is comfortably on track (~70%),
Online Store Launch has overshot (~120%, the required negative
amount_to_achieve case), and Warehouse Relocation has barely started
(~25%). A fourth budget, February Marketing Push, is left in draft. The
Online Store Launch budget is then revised, producing a linked draft
revision with a bumped committed_amount — the bidirectional
revision_of_id/revised_with_id relationship, live.

Design:

- Masters (users, partners, categories, products, analytics, the chart of
  accounts, journals) are upserted by natural key via get_or_create(), so
  re-running this file never duplicates them.
- Transactional data (the opening entry, manual expenses, the sales cycle,
  the purchase cycle, budgets, payments) is gated behind "does the ledger
  already have entries?". Posted journal entries are immutable by design
  (R4) — reseeding them means reversing, not updating, which is out of
  scope for a demo seed. Re-running against an already-seeded database
  re-upserts masters and re-asserts the trial balance, but does not add a
  second copy of the transactions.
- Every document is created through its real service function
  (confirm_sales_order, confirm_vendor_bill, register_payment, ...), the
  same functions the API routes call — never a raw INSERT. Seed data is
  produced by the same code paths as production, so if it does not
  balance, that code is broken.

Ends with §14's post_seed_assertion: compute the trial balance and exit
loudly, non-zero, if it does not balance. Then prints a verification
summary (income/expenses/margin, budget achievement) so the three budget
stories above can be checked by eye against the ranges they are meant to
land in.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    AccountGroup,
    AccountType,
    BudgetLineType,
    JournalType,
    PartnerType,
    PaymentType,
    ProductType,
    UserRole,
)
from app.core.security import hash_password
from app.database import SessionLocal, init_db
from app.models.account import Account, Journal
from app.models.analytic import AnalyticAccount
from app.models.budget import Budget, BudgetLine
from app.models.journal_entry import JournalEntry
from app.models.partner import Partner
from app.models.product import Product, ProductCategory
from app.models.purchase import PurchaseOrder, PurchaseOrderLine, VendorBill
from app.models.sales import CustomerInvoice
from app.models.user import User
from app.services import budgets as budgets_service
from app.services import payments as payments_service
from app.services import purchase as purchase_service
from app.services import reports
from app.services import sales as sales_service
from app.services.accounting import LineInput, post_journal_entry

ZERO = Decimal("0.00")


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
            "street": "14 Linking Road",
            "city": "Mumbai",
            "state": "Maharashtra",
            "country": "India",
            "pincode": "400050",
        },
        {
            "name": "Nimesh Pathak",
            "partner_type": PartnerType.both,
            "email": "nimesh.pathak@example.com",
            "phone": "9820044556",
            "street": "22 FC Road",
            "city": "Pune",
            "state": "Maharashtra",
            "country": "India",
            "pincode": "411005",
        },
        {
            "name": "Priya Enterprises",
            "partner_type": PartnerType.customer,
            "email": "priya@enterprises.example",
            "phone": "9900112233",
            "street": "45 MG Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "country": "India",
            "pincode": "560001",
        },
        {
            "name": "Metro Interiors",
            "partner_type": PartnerType.customer,
            "email": "contact@metrointeriors.example",
            "phone": "9911223345",
            "street": "8 Banjara Hills Road",
            "city": "Hyderabad",
            "state": "Telangana",
            "country": "India",
            "pincode": "500034",
        },
        {
            "name": "Anita Verma",
            "partner_type": PartnerType.customer,
            "email": "anita.verma@example.com",
            "phone": "9922334455",
            "street": "12 Karol Bagh",
            "city": "Delhi",
            "state": "Delhi",
            "country": "India",
            "pincode": "110005",
        },
        {
            "name": "Coastal Furniture Traders",
            "partner_type": PartnerType.customer,
            "email": "sales@coastalfurniture.example",
            "phone": "9944556678",
            "street": "3 Marine Drive",
            "city": "Kochi",
            "state": "Kerala",
            "country": "India",
            "pincode": "682001",
        },
        {
            "name": "Open Wood Furnishings",
            "partner_type": PartnerType.vendor,
            "email": "sales@openwood.example",
            "phone": "9840011223",
            "street": "67 Anna Salai",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "country": "India",
            "pincode": "600002",
        },
        {
            "name": "Sharma Timber Co",
            "partner_type": PartnerType.vendor,
            "email": "orders@sharmatimber.example",
            "phone": "9811223344",
            "street": "19 Industrial Area",
            "city": "Jaipur",
            "state": "Rajasthan",
            "country": "India",
            "pincode": "302006",
        },
        {
            "name": "Gupta Hardware Supplies",
            "partner_type": PartnerType.vendor,
            "email": "orders@guptahardware.example",
            "phone": "9933445566",
            "street": "5 Sarojini Devi Road",
            "city": "Ahmedabad",
            "state": "Gujarat",
            "country": "India",
            "pincode": "380009",
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
    # (name, category, type, sales_price, cost_price) — margins deliberately
    # vary (~25%-37%), not identical across products.
    specs = [
        ("Dining Table", "Furniture", ProductType.goods, "8000.00", "5500.00"),
        ("Chair", "Furniture", ProductType.goods, "2500.00", "1700.00"),
        ("Sofa Set", "Furniture", ProductType.goods, "24000.00", "16500.00"),
        ("Wardrobe", "Furniture", ProductType.goods, "18000.00", "12000.00"),
        ("Bed", "Furniture", ProductType.goods, "16000.00", "11000.00"),
        ("Bookshelf", "Furniture", ProductType.goods, "6000.00", "4000.00"),
        ("Office Desk", "Furniture", ProductType.goods, "9500.00", "6500.00"),
        ("Air Conditioner", "Electronics", ProductType.goods, "32000.00", "24000.00"),
        ("Refrigerator", "Electronics", ProductType.goods, "28000.00", "21000.00"),
        ("Washing Machine", "Electronics", ProductType.goods, "24000.00", "18000.00"),
        ("Delivery Service", "Services", ProductType.service, "1500.00", "950.00"),
        ("Assembly Service", "Services", ProductType.service, "1200.00", "780.00"),
        ("Installation Service", "Services", ProductType.service, "1800.00", "1150.00"),
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
    for name in [
        "Showroom Expansion",
        "Online Store Launch",
        "Warehouse Relocation",
        "General Operations",
    ]:
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


# --- opening entry and manual expenses ---------------------------------------


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
            LineInput(account_id=accounts["Bank A/c"].id, debit=Decimal("750000.00")),
            LineInput(
                account_id=accounts["Capital A/c"].id, credit=Decimal("750000.00")
            ),
        ],
    )
    print("  opening entry: Bank 750000.00 / Capital 750000.00")


def seed_manual_expenses(
    db: Session, accounts: dict[str, Account], journals: dict[str, Journal]
) -> None:
    """Monthly rent (flat) and utilities (mildly rising) for all three months,
    plus one March-only one-off (equipment repair) that narrows March's
    margin even though March is the quarter's best revenue month (§14)."""
    other_expense = accounts["Other Expense A/c"].id
    bank = accounts["Bank A/c"].id
    bank_journal = journals["Bank"].id

    def _expense(entry_date: date, reference: str, amount: Decimal) -> None:
        post_journal_entry(
            db,
            entry_date=entry_date,
            journal_id=bank_journal,
            reference=reference,
            source_type="manual",
            lines=[
                LineInput(account_id=other_expense, debit=amount),
                LineInput(account_id=bank, credit=amount),
            ],
        )

    _expense(date(2026, 1, 1), "January rent", Decimal("28000.00"))
    _expense(date(2026, 2, 1), "February rent", Decimal("28000.00"))
    _expense(date(2026, 3, 1), "March rent", Decimal("28000.00"))

    _expense(date(2026, 1, 5), "January utilities", Decimal("4000.00"))
    _expense(date(2026, 2, 5), "February utilities", Decimal("4300.00"))
    _expense(date(2026, 3, 5), "March utilities", Decimal("4700.00"))

    _expense(date(2026, 3, 20), "Equipment repair and maintenance", Decimal("25000.00"))

    print(
        "  manual entries: rent 28000.00 x 3, utilities 4000/4300/4700, "
        "one-off March equipment repair 25000.00 (all Other Expense A/c)"
    )


# --- sales cycle --------------------------------------------------------


# Each row: (label, month, day, customer, analytic, mode, lines)
# lines: list of (product, quantity)
# mode: "full" (confirm SO -> invoice -> confirm invoice),
#       "draft_invoice" (confirm SO -> invoice, invoice left draft),
#       "draft_so" (SO left draft, never invoiced)
SALES_SPECS = [
    # --- January: baseline ---
    (
        "J-SO1",
        1,
        5,
        "Priya Enterprises",
        "General Operations",
        "full",
        [("Dining Table", 2), ("Chair", 4)],
    ),
    (
        "J-SO2",
        1,
        8,
        "Metro Interiors",
        "Showroom Expansion",
        "full",
        [("Sofa Set", 2)],
    ),
    (
        "J-SO3",
        1,
        10,
        "Anita Verma",
        "General Operations",
        "full",
        [("Wardrobe", 1), ("Bed", 1)],
    ),
    (
        "J-SO4",
        1,
        14,
        "Coastal Furniture Traders",
        "Online Store Launch",
        "full",
        [("Air Conditioner", 3)],
    ),
    (
        "J-SO5",
        1,
        18,
        "Mr Rahul",
        "General Operations",
        "draft_invoice",
        [("Bookshelf", 2), ("Assembly Service", 2)],
    ),
    (
        "J-SO6",
        1,
        22,
        "Nimesh Pathak",
        "General Operations",
        "draft_so",
        [("Office Desk", 5)],
    ),
    # --- February: noticeably stronger than January ---
    (
        "F-SO1",
        2,
        3,
        "Priya Enterprises",
        "Showroom Expansion",
        "full",
        [("Sofa Set", 3)],
    ),
    (
        "F-SO2",
        2,
        6,
        "Metro Interiors",
        "Online Store Launch",
        "full",
        [("Air Conditioner", 2), ("Refrigerator", 1)],
    ),
    (
        "F-SO3",
        2,
        9,
        "Anita Verma",
        "General Operations",
        "full",
        [("Dining Table", 4), ("Delivery Service", 4)],
    ),
    (
        "F-SO4",
        2,
        13,
        "Coastal Furniture Traders",
        "Online Store Launch",
        "full",
        [("Washing Machine", 2)],
    ),
    (
        "F-SO5",
        2,
        17,
        "Mr Rahul",
        "General Operations",
        "draft_invoice",
        [("Wardrobe", 2)],
    ),
    (
        "F-SO6",
        2,
        21,
        "Nimesh Pathak",
        "General Operations",
        "draft_so",
        [("Chair", 10)],
    ),
    # --- March: highest revenue of the quarter, margin narrows (one-off expense) ---
    (
        "M-SO1",
        3,
        4,
        "Priya Enterprises",
        "Showroom Expansion",
        "full",
        [("Sofa Set", 2), ("Wardrobe", 2)],
    ),
    (
        "M-SO2",
        3,
        7,
        "Metro Interiors",
        "Online Store Launch",
        "full",
        [("Air Conditioner", 3)],
    ),
    (
        "M-SO3",
        3,
        11,
        "Anita Verma",
        "General Operations",
        "full",
        [("Refrigerator", 2), ("Installation Service", 2)],
    ),
    (
        "M-SO4",
        3,
        15,
        "Coastal Furniture Traders",
        "Online Store Launch",
        "full",
        [("Washing Machine", 3)],
    ),
    (
        "M-SO5",
        3,
        19,
        "Mr Rahul",
        "General Operations",
        "draft_invoice",
        [("Dining Table", 6), ("Chair", 10)],
    ),
    (
        "M-SO6",
        3,
        24,
        "Nimesh Pathak",
        "General Operations",
        "draft_so",
        [("Office Desk", 4)],
    ),
    # --- April: the quarter's growth continues into Q2, so the demo does not
    # look like a dataset that stopped dead on 31 March. Same shape as the
    # months above: most run the full cycle, one is left mid-flow.
    (
        "A-SO1",
        4,
        3,
        "Priya Enterprises",
        "General Operations",
        "full",
        [("Dining Table", 5), ("Chair", 10)],
    ),
    (
        "A-SO2",
        4,
        7,
        "Metro Interiors",
        "Showroom Expansion",
        "full",
        [("Sofa Set", 3)],
    ),
    # Mr Rahul's first CONFIRMED invoice. Every invoice of his before this one
    # is a draft, so the portal walkthrough (rahulcust) had nothing payable on
    # it at all — no partial, no outstanding balance, nothing to click Pay on.
    (
        "A-SO3",
        4,
        10,
        "Mr Rahul",
        "General Operations",
        "full",
        [("Wardrobe", 2), ("Bed", 1), ("Delivery Service", 2)],
    ),
    (
        "A-SO4",
        4,
        14,
        "Coastal Furniture Traders",
        "Online Store Launch",
        "full",
        [("Refrigerator", 3), ("Washing Machine", 1)],
    ),
    (
        "A-SO5",
        4,
        20,
        "Nimesh Pathak",
        "General Operations",
        "full",
        [("Office Desk", 5), ("Assembly Service", 5)],
    ),
    # Rahul's second confirmed invoice, deliberately left out of
    # INVOICE_PAYMENT_SPECS. With A-SO3 (partial) and his three drafts, the
    # portal then shows all three states a contact can actually be in:
    # awaiting confirmation, partially paid, and confirmed-but-untouched —
    # the last being the only one that offers a full-balance Pay button.
    (
        "A-SO7",
        4,
        24,
        "Mr Rahul",
        "General Operations",
        "full",
        [("Bookshelf", 2), ("Assembly Service", 3)],
    ),
    (
        "A-SO6",
        4,
        27,
        "Anita Verma",
        "General Operations",
        "draft_invoice",
        [("Air Conditioner", 2), ("Installation Service", 2)],
    ),
]


def seed_sales_cycle(
    db: Session,
    partners: dict[str, Partner],
    products: dict[str, Product],
    analytics: dict[str, AnalyticAccount],
) -> dict[str, CustomerInvoice]:
    """25 sales orders across Jan-Apr 2026 (§14): most run the full
    order -> invoice -> confirm cycle; a few are deliberately left mid-flow
    (draft invoice, or draft order never invoiced) so the demo shows the
    system's states, not just finished work.

    Returns the CONFIRMED invoices keyed by their spec label, so
    seed_payments can register real payments against specific, named
    documents.
    """
    confirmed_invoices: dict[str, CustomerInvoice] = {}
    full_count = draft_invoice_count = draft_so_count = 0

    for label, month, day, customer_name, analytic_name, mode, lines in SALES_SPECS:
        customer = partners[customer_name]
        analytic = analytics[analytic_name]
        order_date = date(2026, month, day)

        so = sales_service.create_sales_order(
            db,
            customer_id=customer.id,
            order_date=order_date,
            lines=[
                {
                    "product_id": products[product_name].id,
                    "analytic_account_id": analytic.id,
                    "quantity": Decimal(str(qty)),
                    "unit_price": products[product_name].sales_price,
                }
                for product_name, qty in lines
            ],
        )

        if mode == "draft_so":
            draft_so_count += 1
            continue

        sales_service.confirm_sales_order(db, sales_order_id=so.id)
        invoice = sales_service.create_invoice_from_so(
            db, sales_order_id=so.id, invoice_date=order_date
        )

        if mode == "draft_invoice":
            draft_invoice_count += 1
            continue

        sales_service.confirm_customer_invoice(db, invoice_id=invoice.id)
        confirmed_invoices[label] = invoice
        full_count += 1

    print(
        f"  sales cycle: {len(SALES_SPECS)} sales orders - {full_count} run the "
        f"full cycle (confirmed + invoiced + posted), {draft_invoice_count} left "
        f"with a draft invoice, {draft_so_count} left as a draft order"
    )
    return confirmed_invoices


# --- purchase cycle -----------------------------------------------------


# Each row: (label, month, day, vendor, analytic, mode, lines)
# lines: list of (product, quantity, unit_price) — purchase pricing is
# vendor-negotiated, independent of the product master's cost_price.
# mode: "full" (confirm PO -> bill -> confirm bill),
#       "draft_bill" (confirm PO -> bill, bill left draft),
#       "draft_po" (PO left draft, never billed)
#
# The Showroom Expansion / Online Store Launch / Warehouse Relocation lines
# below are the exact figures the three Q1 budgets are built against
# (§14 budgets): they sum to precisely 87500.00, 138000.00 and 24000.00
# respectively — see seed_budgets for the committed_amount each is measured
# against, and the printed verification summary at the end of this script.
PURCHASE_SPECS = [
    # --- January ---
    (
        "PJ1",
        1,
        8,
        "Sharma Timber Co",
        "Showroom Expansion",
        "full",
        [("Sofa Set", 1, "22500.00")],
    ),
    (
        "PJ2",
        1,
        10,
        "Gupta Hardware Supplies",
        "Online Store Launch",
        "full",
        [("Washing Machine", 1, "19000.00")],
    ),
    (
        "PJ3",
        1,
        12,
        "Open Wood Furnishings",
        "Warehouse Relocation",
        "full",
        [("Bookshelf", 2, "4000.00")],
    ),
    (
        "PJ4",
        1,
        15,
        "Open Wood Furnishings",
        "General Operations",
        "full",
        [
            ("Dining Table", 6, "5500.00"),
            ("Chair", 10, "1700.00"),
            ("Office Desk", 1, "6000.00"),
        ],
    ),
    (
        "PJ5",
        1,
        20,
        "Sharma Timber Co",
        "General Operations",
        "draft_bill",
        [("Bed", 2, "11000.00"), ("Bookshelf", 3, "4000.00")],
    ),
    # --- February: higher purchase volume, buying more stock to meet demand ---
    (
        "PF1",
        2,
        5,
        "Gupta Hardware Supplies",
        "Showroom Expansion",
        "full",
        [("Air Conditioner", 1, "25000.00")],
    ),
    (
        "PF2",
        2,
        8,
        "Sharma Timber Co",
        "Online Store Launch",
        "full",
        [("Refrigerator", 2, "22000.00")],
    ),
    (
        "PF3",
        2,
        10,
        "Sharma Timber Co",
        "Warehouse Relocation",
        "full",
        [("Chair", 4, "2000.00")],
    ),
    (
        "PF4",
        2,
        14,
        "Open Wood Furnishings",
        "General Operations",
        "full",
        [("Dining Table", 10, "5500.00")],
    ),
    (
        "PF5",
        2,
        18,
        "Sharma Timber Co",
        "General Operations",
        "draft_bill",
        [("Wardrobe", 2, "12000.00"), ("Bed", 2, "11000.00")],
    ),
    (
        "PF6",
        2,
        22,
        "Gupta Hardware Supplies",
        "General Operations",
        "full",
        [("Office Desk", 2, "7000.00")],
    ),
    (
        "PF7",
        2,
        25,
        "Sharma Timber Co",
        "General Operations",
        "draft_po",
        [("Bed", 1, "11000.00")],
    ),
    # --- March: continued growth, feeds the equipment-repair-narrowed margin ---
    (
        "PM1",
        3,
        4,
        "Open Wood Furnishings",
        "Showroom Expansion",
        "full",
        [("Wardrobe", 2, "20000.00")],
    ),
    (
        "PM2",
        3,
        7,
        "Open Wood Furnishings",
        "Online Store Launch",
        "full",
        [("Air Conditioner", 3, "25000.00")],
    ),
    (
        "PM3",
        3,
        10,
        "Gupta Hardware Supplies",
        "Warehouse Relocation",
        "full",
        [("Office Desk", 1, "8000.00")],
    ),
    (
        "PM4",
        3,
        13,
        "Open Wood Furnishings",
        "General Operations",
        "full",
        [("Dining Table", 8, "5500.00"), ("Chair", 20, "1700.00")],
    ),
    (
        "PM5",
        3,
        17,
        "Sharma Timber Co",
        "General Operations",
        "draft_bill",
        [("Sofa Set", 2, "16500.00")],
    ),
    # --- April: the purchase side of the Q2 continuation.
    #
    # Every April line is tagged "General Operations" deliberately. The three
    # Q1 budgets measure 01 Jan - 31 Mar, so an April bill tagged (say) Online
    # Store Launch would contribute 0.00 to it and read as a bug to anyone
    # comparing the two screens. The date filter is already covered by its own
    # §10.7 scenario; the demo data does not need to re-litigate it.
    (
        "PA1",
        4,
        2,
        "Sharma Timber Co",
        "General Operations",
        "full",
        [("Dining Table", 6, "5500.00"), ("Chair", 12, "1700.00")],
    ),
    (
        "PA2",
        4,
        6,
        "Gupta Hardware Supplies",
        "General Operations",
        "full",
        [("Sofa Set", 2, "16500.00")],
    ),
    # Mr Rahul is a "both" contact — customer AND vendor — but nothing in the
    # dataset ever bought from him, so the portal's My Bills page was empty.
    # Real products with real product_ids, not a typed-in description.
    (
        "PA3",
        4,
        9,
        "Mr Rahul",
        "General Operations",
        "full",
        [("Bookshelf", 3, "4000.00"), ("Delivery Service", 2, "950.00")],
    ),
    (
        "PA4",
        4,
        13,
        "Open Wood Furnishings",
        "General Operations",
        "full",
        [("Refrigerator", 2, "21000.00")],
    ),
    (
        "PA5",
        4,
        21,
        "Gupta Hardware Supplies",
        "General Operations",
        "full",
        [("Office Desk", 2, "6500.00")],
    ),
    (
        "PA6",
        4,
        28,
        "Sharma Timber Co",
        "General Operations",
        "draft_bill",
        [("Bed", 2, "11000.00")],
    ),
]


def seed_purchase_cycle(
    db: Session,
    partners: dict[str, Partner],
    products: dict[str, Product],
    analytics: dict[str, AnalyticAccount],
) -> dict[str, VendorBill]:
    """23 purchase orders across Jan-Apr 2026 (§14): most run the full
    order -> bill -> confirm cycle; a few are deliberately left mid-flow
    (draft bill, or draft order never billed), the same principle as the
    sales cycle.

    Returns the CONFIRMED bills keyed by their spec label, so seed_payments
    can register real payments against specific, named documents.
    """
    confirmed_bills: dict[str, VendorBill] = {}
    full_count = draft_bill_count = draft_po_count = 0

    for label, month, day, vendor_name, analytic_name, mode, lines in PURCHASE_SPECS:
        vendor = partners[vendor_name]
        analytic = analytics[analytic_name]
        order_date = date(2026, month, day)

        order = PurchaseOrder(
            number=purchase_service.next_purchase_order_number(db),
            vendor_id=vendor.id,
            order_date=order_date,
        )
        for sequence, (product_name, qty, unit_price) in enumerate(lines, start=1):
            quantity = Decimal(str(qty))
            price = Decimal(unit_price)
            order.lines.append(
                PurchaseOrderLine(
                    product_id=products[product_name].id,
                    analytic_account_id=analytic.id,
                    quantity=quantity,
                    unit_price=price,
                    line_total=purchase_service.compute_line_total(quantity, price),
                    sequence=sequence * 10,
                )
            )
        order.total_amount = purchase_service.recompute_total(order.lines)
        db.add(order)
        db.flush()

        if mode == "draft_po":
            draft_po_count += 1
            continue

        purchase_service.confirm_purchase_order(db, order)
        bill = purchase_service.create_bill_from_po(db, order, bill_date=order_date)

        if mode == "draft_bill":
            draft_bill_count += 1
            continue

        purchase_service.confirm_vendor_bill(db, bill)
        confirmed_bills[label] = bill
        full_count += 1

    print(
        f"  purchase cycle: {len(PURCHASE_SPECS)} purchase orders - {full_count} run "
        f"the full cycle (confirmed + billed + posted), {draft_bill_count} left "
        f"with a draft bill, {draft_po_count} left as a draft order"
    )
    return confirmed_bills


# --- budgets --------------------------------------------------------------


def seed_budgets(
    db: Session, partners: dict[str, Partner], analytics: dict[str, AnalyticAccount]
) -> None:
    """4 budgets telling 3 distinct achievement stories, plus a draft, plus
    a revision (§14):

    - "Q1 Showroom Expansion" (expense, committed 125000.00) measures
      against 87500.00 of confirmed, Showroom-Expansion-tagged bill lines
      (PJ1+PF1+PM1) => 70.00% achieved. Comfortably on track.
    - "Q1 Online Store Launch" (expense, committed 115000.00) measures
      against 138000.00 of confirmed, Online-Store-Launch-tagged bill lines
      (PJ2+PF2+PM2) => 120.00% achieved, amount_to_achieve -23000.00. The
      required over-budget case.
    - "Q1 Warehouse Relocation" (expense, committed 96000.00) measures
      against 24000.00 of confirmed, Warehouse-Relocation-tagged bill lines
      (PJ3+PF3+PM3) => 25.00% achieved. Hasn't ramped up yet.
    - "February Marketing Push" is created but left in DRAFT — its
      achievement stays hidden (§7.9) until someone confirms it.

    The over-budget "Q1 Online Store Launch" budget is then revised via
    revise_budget(): the original becomes state=revised, a new draft budget
    is created with committed_amount raised to a more realistic figure,
    and the two link to each other via revision_of_id/revised_with_id.
    """
    period_start = date(2026, 1, 1)
    period_end = date(2026, 3, 31)

    def _confirmed_budget(
        name: str, analytic_name: str, committed: str, responsible_name: str
    ) -> Budget:
        budget = Budget(
            name=name,
            start_date=period_start,
            end_date=period_end,
            responsible_id=partners[responsible_name].id,
        )
        budget.lines.append(
            BudgetLine(
                analytic_account_id=analytics[analytic_name].id,
                line_type=BudgetLineType.EXPENSE,
                committed_amount=Decimal(committed),
                sequence=10,
            )
        )
        db.add(budget)
        db.flush()
        budgets_service.confirm_budget(db, budget)
        return budget

    showroom = _confirmed_budget(
        "Q1 Showroom Expansion",
        "Showroom Expansion",
        "125000.00",
        "Sharma Timber Co",
    )
    online_store = _confirmed_budget(
        "Q1 Online Store Launch",
        "Online Store Launch",
        "115000.00",
        "Gupta Hardware Supplies",
    )
    warehouse = _confirmed_budget(
        "Q1 Warehouse Relocation",
        "Warehouse Relocation",
        "96000.00",
        "Open Wood Furnishings",
    )

    marketing_push = Budget(
        name="February Marketing Push",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        responsible_id=partners["Priya Enterprises"].id,
    )
    marketing_push.lines.append(
        BudgetLine(
            analytic_account_id=analytics["General Operations"].id,
            line_type=BudgetLineType.EXPENSE,
            committed_amount=Decimal("30000.00"),
            sequence=10,
        )
    )
    db.add(marketing_push)
    db.flush()

    # Revise the over-budget one: the business responds to overshooting by
    # approving a higher figure going forward. revise_budget() copies the
    # committed_amount unchanged (it is a snapshot of what WAS agreed); the
    # revision is a fresh draft, so bumping its line here is exactly what a
    # PUT /budgets/{revision_id} edit would do before it is re-confirmed.
    revision = budgets_service.revise_budget(db, online_store)
    revision.lines[0].committed_amount = Decimal("150000.00")
    db.flush()

    showroom_achievement = budgets_service.compute_achievement(db, showroom.lines[0])
    online_store_achievement = budgets_service.compute_achievement(
        db, online_store.lines[0]
    )
    warehouse_achievement = budgets_service.compute_achievement(db, warehouse.lines[0])

    print(
        f"  budgets: '{showroom.name}' confirmed, achieved "
        f"{showroom_achievement.achieved_amount} "
        f"({showroom_achievement.achieved_percent}%)"
    )
    print(
        f"  budgets: '{online_store.name}' confirmed OVER budget, achieved "
        f"{online_store_achievement.achieved_amount} "
        f"({online_store_achievement.achieved_percent}%, "
        f"amount_to_achieve {online_store_achievement.amount_to_achieve}); "
        f"revised -> '{revision.name}' (draft, committed "
        f"{revision.lines[0].committed_amount})"
    )
    print(
        f"  budgets: '{warehouse.name}' confirmed, achieved "
        f"{warehouse_achievement.achieved_amount} "
        f"({warehouse_achievement.achieved_percent}%)"
    )
    print(f"  budgets: '{marketing_push.name}' left draft")


# --- payments ---------------------------------------------------------------


# (label, kind, mode, amount) — kind in {"invoice", "bill"}; mode "full" pays
# the whole document, "partial" pays exactly `amount`. Anything not listed is
# left completely unpaid (not_paid) on purpose (§14 deliberate_states): all
# three payment_status values must be visible across the dataset at once.
INVOICE_PAYMENT_SPECS = [
    ("J-SO1", "full", None),
    ("J-SO4", "full", None),
    ("F-SO2", "full", None),
    ("M-SO1", "full", None),
    ("M-SO4", "full", None),
    ("J-SO2", "partial", "24000.00"),
    ("F-SO1", "partial", "40000.00"),
    ("M-SO2", "partial", "50000.00"),
    # --- April ---
    ("A-SO1", "full", None),
    ("A-SO4", "full", None),
    ("A-SO2", "partial", "30000.00"),
    # Mr Rahul, partially settled: this is what gives the portal walkthrough a
    # confirmed invoice with a real outstanding balance to pay against.
    ("A-SO3", "partial", "20000.00"),
    # J-SO3, F-SO3, F-SO4, M-SO3 and A-SO5 stay not_paid.
]

BILL_PAYMENT_SPECS = [
    ("PJ1", "full", None),
    ("PJ4", "full", None),
    ("PF2", "full", None),
    ("PF4", "full", None),
    ("PJ2", "partial", "10000.00"),
    ("PF1", "partial", "12000.00"),
    ("PM1", "partial", "20000.00"),
    ("PM2", "partial", "40000.00"),
    ("PM4", "partial", "40000.00"),
    # --- April ---
    ("PA1", "full", None),
    ("PA4", "full", None),
    ("PA2", "partial", "15000.00"),
    # Mr Rahul as a vendor, partially paid — so his My Bills page shows a
    # balance rather than a row that is either untouched or already closed.
    ("PA3", "partial", "5000.00"),
    # PJ3, PF3, PF6, PM3, PA5 stay not_paid.
]


def seed_payments(
    db: Session,
    journals: dict[str, Journal],
    invoices: dict[str, CustomerInvoice],
    bills: dict[str, VendorBill],
) -> None:
    """Mixed paid/partial/not_paid on both sides, landing at roughly a
    60-70% collection rate overall (§14) — verified in the summary this
    script prints at the end, not just asserted here.
    """
    bank = journals["Bank"]

    def _pay(
        *, payment_type, partner_id, amount, payment_date, invoice_id=None, bill_id=None
    ):
        payment = payments_service.register_payment(
            db,
            payment_type=payment_type,
            partner_id=partner_id,
            journal_id=bank.id,
            amount=amount,
            payment_date=payment_date,
            invoice_id=invoice_id,
            bill_id=bill_id,
        )
        payments_service.confirm_payment(db, payment)

    paid_count = partial_count = 0
    for label, mode, amount in INVOICE_PAYMENT_SPECS:
        invoice = invoices[label]
        pay_amount = invoice.total_amount if mode == "full" else Decimal(amount)
        _pay(
            payment_type=PaymentType.RECEIVE,
            partner_id=invoice.customer_id,
            amount=pay_amount,
            payment_date=invoice.invoice_date + timedelta(days=10),
            invoice_id=invoice.id,
        )
        if mode == "full":
            paid_count += 1
        else:
            partial_count += 1

    bill_paid_count = bill_partial_count = 0
    for label, mode, amount in BILL_PAYMENT_SPECS:
        bill = bills[label]
        pay_amount = bill.total_amount if mode == "full" else Decimal(amount)
        _pay(
            payment_type=PaymentType.SEND,
            partner_id=bill.vendor_id,
            amount=pay_amount,
            payment_date=bill.bill_date + timedelta(days=10),
            bill_id=bill.id,
        )
        if mode == "full":
            bill_paid_count += 1
        else:
            bill_partial_count += 1

    invoices_untouched = len(invoices) - len(INVOICE_PAYMENT_SPECS)
    bills_untouched = len(bills) - len(BILL_PAYMENT_SPECS)
    print(
        f"  payments (invoices): {paid_count} paid in full, {partial_count} "
        f"partial, {invoices_untouched} left not_paid"
    )
    print(
        f"  payments (bills): {bill_paid_count} paid in full, {bill_partial_count} "
        f"partial, {bills_untouched} left not_paid"
    )


# --- verification summary ----------------------------------------------------


def print_verification_summary(db: Session) -> None:
    """§14 step 7: print the numbers a human needs to eyeball the three
    budget stories and the overall margin, computed the same way the report
    endpoints compute them — not hand-asserted separately.
    """
    pnl = reports.profit_and_loss(db, year=2026)
    total_income = pnl["income"]["total_income"]
    total_expenses = pnl["expenses"]["total_expenses"]
    net_income = pnl["net_income"]
    margin = (net_income / total_income * 100) if total_income else ZERO

    print("\n" + "=" * 78)
    print("VERIFICATION SUMMARY")
    print("=" * 78)
    print(f"  Total income          : {total_income}")
    print(f"  Total expenses         : {total_expenses}")
    print(f"    Purchase expense      : {pnl['expenses']['purchase_expense']}")
    print(f"    Other expense         : {pnl['expenses']['other_expense']}")
    print(f"  Net income             : {net_income}")
    print(f"  Net margin             : {margin:.2f}%")

    print("\n  Budget achievement (confirmed/revised budgets only):")
    for row in budgets_service.budget_summary(db):
        print(
            f"    {row['budget_name']:<28} committed={row['committed_amount']:<12} "
            f"achieved={row['achieved_amount']:<12} "
            f"({row['achieved_percent']}%)"
        )
    print("=" * 78)


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
                "Ledger already has entries - skipping transaction seeding "
                "(posted entries are immutable, R4). To reseed from scratch: "
                "docker compose down -v && docker compose up -d, then "
                "init_db() and this script again."
            )
        else:
            print("Seeding the opening entry and manual expenses...")
            seed_opening_entry(db, accounts, journals)
            seed_manual_expenses(db, accounts, journals)
            db.commit()

            print("Seeding the sales cycle (Jan-Apr 2026)...")
            invoices = seed_sales_cycle(db, partners, products, analytics)
            db.commit()

            print("Seeding the purchase cycle (Jan-Apr 2026)...")
            bills = seed_purchase_cycle(db, partners, products, analytics)
            db.commit()

            print("Seeding budgets...")
            seed_budgets(db, partners, analytics)
            db.commit()

            print("Seeding payments...")
            seed_payments(db, journals, invoices, bills)
            db.commit()

        print("\nComputing the trial balance (SPEC.md #14 post_seed_assertion)...")
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

        print_verification_summary(db)
        print("\nSeed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
