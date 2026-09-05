# SPEC.md — Urban Furniture Accounting System

> **Architectural North-Star Specification**
> Odoo Hackathon 2026 · Final Round · 5–6 September 2026 · 24 hours · Team of 3
>
> This document is the single source of truth. If code and this document disagree,
> this document wins. If this document is ambiguous, stop and ask — do not guess.

---

## 0. How to read this document

| Section | What it gives you                                                             |
| ------- | ----------------------------------------------------------------------------- |
| §1–§2   | **Why** the system exists and the rules you may never break                   |
| §3–§5   | Exact tooling, versions, repo layout, environment                             |
| §6      | **Background** — the accounting concepts. Read this before writing any logic. |
| §7      | Database schema (YAML)                                                        |
| §8      | The posting engine — the heart of the system                                  |
| §9      | API contract (YAML)                                                           |
| §10     | BDD scenarios in Gherkin — the definition of correct                          |
| §11–§13 | Validation, errors, frontend                                                  |
| §14–§18 | Seed data, non-functional requirements, Git, build order, done criteria       |

**Instruction to the implementing agent:** Every behaviour in §10 is a test. Before you
mark a feature complete, walk its scenarios manually and confirm each `Then` holds. Do
not write code for behaviour that has no scenario here — ask first.

---

## 1. Context and purpose

### 1.1 The business

Urban Furniture is a furniture trading business. It buys goods from vendors and sells
them to customers. Today its books live in spreadsheets. It needs a system that answers
three questions at any moment:

1. **What do I own and what do I owe?** → Balance Sheet
2. **Did I make money this period?** → Profit & Loss
3. **Am I spending within plan?** → Budget vs Actual (by project/analytic)

### 1.2 What we are building

A double-entry accounting system with:

- Master data: Contacts, Products, Chart of Accounts, Journals, Analytic Accounts
- Purchase cycle: Purchase Order → Vendor Bill → Payment
- Sales cycle: Sales Order → Customer Invoice → Payment
- A general ledger that every transaction posts into
- Budgets tracked against analytic accounts, with revision history
- Financial reports derived entirely from the ledger

### 1.3 Why this shape (the "why" behind the "what")

Every document in this system — invoice, bill, payment, manual entry — is a **source
document**. None of them store balances. They all produce **journal entries**, and every
report is an aggregation over journal entry lines.

This matters because it is the difference between an accounting system and a CRUD app
with an accounting theme. If you find yourself writing a `customer.balance` column, or
computing a report from the `invoices` table, **you have taken a wrong turn**. Go back to
the ledger.

The single benefit: correctness is verifiable. Total debits across the entire database
must always equal total credits. If they don't, something is broken, and you can find it.

---

## 2. Non-negotiable principles

These are invariants. Violating any of them is a defect regardless of whether a test
catches it.

```yaml
principles:
  P1_balanced_entries:
    rule: "Every posted journal entry has sum(debit) == sum(credit), exactly."
    enforced_at:
      - "Database: CHECK constraint on journal_entry_lines (no line has both debit and credit non-zero)"
      - "Service layer: posting engine validates totals before commit"
      - "API: returns 422 with a structured error, never a partial write"
      - "UI: blocking warning, Post button disabled until balanced"
    why: >
      This is the defining property of double-entry bookkeeping. It is also the
      property that makes the system impossible to fake — an unbalanced ledger
      produces a visibly wrong Balance Sheet.

  P2_decimal_money:
    rule: "All monetary values are Decimal in Python and NUMERIC(14,2) in Postgres. Never float."
    why: >
      Binary floating point cannot represent most decimal fractions exactly.
      199.99 * 3 evaluates to 599.9699999999999 in IEEE-754. Accumulated across
      invoice lines this produces a Balance Sheet that does not balance.
    enforcement:
      - "sqlalchemy Numeric(14, 2) for every money column"
      - "Pydantic: condecimal(max_digits=14, decimal_places=2)"
      - "Python: from decimal import Decimal — never float()"
      - "JSON: serialise money as string, parse as Decimal on the way in"
      - "Frontend: never do arithmetic on money in JS; display server-computed values"

  P3_atomic_posting:
    rule: >
      Confirming a source document and creating its journal entry happen in ONE
      database transaction. Both succeed or both roll back.
    why: >
      A confirmed invoice with no journal entry is corrupt data that will never
      appear in reports and cannot be detected without a reconciliation script.
    enforcement: "SQLAlchemy session; single commit at the end of the service call"

  P4_immutable_posted_entries:
    rule: >
      A journal entry in state 'posted' can never be edited or deleted. Documents
      in state 'confirmed' cannot have their lines changed.
    why: "Audit integrity. Real accounting systems reverse, they do not edit."

  P5_derived_not_stored:
    rule: >
      Account balances, report totals, payment status, and budget achievement are
      COMPUTED from the ledger on read. They are never stored as columns.
    why: >
      Stored aggregates need invalidation on every write path. Three write paths
      (invoice, bill, payment) times three aggregates is nine places to get wrong.
      Computed values cannot drift.
    exception: >
      None at P0. If a query becomes slow, add an index first, and only consider
      materialisation after measuring.

  P6_single_posting_entry_point:
    rule: >
      services/accounting.py::post_journal_entry() is the ONLY function in the
      codebase that writes to journal_entries or journal_entry_lines.
      Invoices, bills, payments, and manual entries all call it.
    why: >
      One place to enforce the balance rule. One place to test. This is the
      modularity story of the entire project.

  P7_server_authoritative_validation:
    rule: >
      Every validation rule exists on the server. Client-side validation is a
      UX convenience and is never the only check.
    why: "A rule that only lives in React is not a rule."

  P8_no_static_json:
    rule: >
      No hardcoded arrays of demo data in the frontend. Every list, count, and
      total comes from an API call against Postgres.
    why: "Explicit hackathon requirement. Also, it is the only honest way to build this."
```

---

## 3. Technology stack — exact versions

> **Pin every version.** Do not use `latest`, `^`, or `~` for anything in this list.
> The agent must write these exact strings into `requirements.txt` and `package.json`.
> If a pinned version fails to install, report it and stop — do not silently upgrade.

```yaml
runtime:
  python: ">=3.10"
  node: "20.x LTS"
  postgres: "16"
  docker_compose_schema: "3.9"
  version_check: >
    Before anyone writes code: everyone runs `python3 --version` and confirms 3.10+.
    Each person uses their own venv with their own installed Python — versions do not
    need to match across teammates, only each satisfy the floor. See §5 for the venv
    setup and the startup guard that enforces this.

backend:
  framework:
    fastapi: "0.115.6"
    uvicorn: "0.34.0" # run with: uvicorn app.main:app --reload
  orm_and_db:
    sqlalchemy: "2.0.36" # 2.0 style: Mapped[] + mapped_column()
    psycopg: "3.2.3" # install as psycopg[binary]
  validation:
    pydantic: "2.10.4"
    pydantic-settings: "2.7.0" # env config
    email-validator: "2.2.0" # required by Pydantic EmailStr
  auth:
    pyjwt: "2.10.1"
    bcrypt: "4.2.1" # use bcrypt DIRECTLY, not passlib
  utils:
    python-multipart: "0.0.20" # file upload (P1)
  dev:
    pytest: "8.3.4"
    httpx: "0.28.1" # FastAPI TestClient dependency
    ruff: "0.8.4" # lint + format, single tool

frontend:
  core:
    react: "18.3.1"
    react-dom: "18.3.1"
    typescript: "5.6.3"
    vite: "5.4.11"
    "@vitejs/plugin-react": "4.3.4"
  routing:
    react-router-dom: "6.28.0"
  styling:
    tailwindcss: "3.4.17" # NOT v4 — tooling is more stable on 3.x
    autoprefixer: "10.4.20"
    postcss: "8.4.49"
    "tailwind-merge": "2.5.5"
    "class-variance-authority": "0.7.1"
    "clsx": "2.1.1"
  components:
    shadcn_ui: "CLI-installed, not a package dependency"
    "lucide-react": "0.468.0" # icons
    "@radix-ui/react-dialog": "1.1.4"
    "@radix-ui/react-select": "2.1.4"
    "@radix-ui/react-tabs": "1.1.2"
    "@radix-ui/react-toast": "1.2.4"
  forms_and_validation:
    "react-hook-form": "7.54.2"
    "zod": "3.24.1"
    "@hookform/resolvers": "3.9.1"
  charts:
    recharts: "2.15.0" # budget pie chart only
  dev:
    eslint: "9.17.0"
    prettier: "3.4.2"

explicitly_excluded:
  - name: "TanStack Query / React Query"
    reason: >
      Adds a dependency and a mental model for a problem solved by calling the
      fetch function again after a mutation. The rubric penalises trendy tech
      that does not add value. Use plain fetch + useState + useEffect via a
      thin useApi hook (§13.4).
  - name: "Alembic"
    reason: >
      No production data exists. Schema comes from Base.metadata.create_all().
      Schema changes propagate via `docker compose down -v && docker compose up`
      then re-seed. Migration history has no value inside a 24-hour window.
  - name: "Redis / Celery / message queues"
    reason: "No async workload exists. Pure padding."
  - name: "MongoDB"
    reason: >
      No multi-table ACID transactions, which P3 requires. Also no NUMERIC type.
  - name: "Next.js"
    reason: "SSR buys nothing for an authenticated internal dashboard."
  - name: "Any cloud-hosted database"
    reason: >
      Hackathon requirement: must work offline. Postgres runs in local Docker.
```

### 3.1 Justification (for judges)

Keep this handy; it is the architecture answer.

> Express needs three separate libraries for what FastAPI does with one Pydantic class —
> request validation, response serialisation, and OpenAPI documentation. Python's native
> `Decimal` is the only safe way to do money arithmetic; JavaScript floats turn
> ₹199.99 × 3 into ₹599.9699999999999, which breaks a Balance Sheet. SQLAlchemy's session
> makes ACID transactions explicit — an invoice and its journal entry commit together or
> roll back together, so you can never have one without the other. And Odoo itself is
> Python, so the architecture aligns with the ecosystem.

---

## 4. Repository structure

Monorepo. One repo, three contributors, clear ownership boundaries.

```
urban-furniture-accounting/
├── README.md
├── SPEC.md                          # this file
├── docker-compose.yml               # Postgres only
├── .env.example
├── .gitignore
│
├── backend/
│   ├── requirements.txt
│   ├── .env                         # gitignored
│   ├── seed.py                      # idempotent seed script
│   └── app/
│       ├── main.py                  # FastAPI app, router registration, CORS
│       ├── config.py                # pydantic-settings
│       ├── database.py              # engine, SessionLocal, Base, get_db()
│       ├── models/                  # SQLAlchemy ORM — one file per domain area
│       │   ├── __init__.py          # imports all models so create_all sees them
│       │   ├── user.py
│       │   ├── partner.py
│       │   ├── product.py
│       │   ├── account.py           # accounts, journals, analytic_accounts
│       │   ├── journal_entry.py
│       │   ├── purchase.py          # purchase_orders, vendor_bills + lines
│       │   ├── sales.py             # sales_orders, customer_invoices + lines
│       │   ├── payment.py
│       │   └── budget.py            # budgets, budget_lines
│       ├── schemas/                 # Pydantic — mirrors models/ file-for-file
│       ├── routers/                 # HTTP layer ONLY. No business logic.
│       │   ├── auth.py
│       │   ├── partners.py
│       │   ├── products.py
│       │   ├── accounts.py
│       │   ├── journals.py
│       │   ├── journal_entries.py
│       │   ├── analytics.py
│       │   ├── purchase_orders.py
│       │   ├── vendor_bills.py
│       │   ├── sales_orders.py
│       │   ├── customer_invoices.py
│       │   ├── payments.py
│       │   ├── budgets.py
│       │   ├── reports.py
│       │   └── dashboard.py
│       ├── services/                # ALL business logic lives here
│       │   ├── accounting.py        # ★ posting engine — see §8
│       │   ├── sequences.py         # document numbering
│       │   ├── documents.py         # PO→Bill, SO→Invoice conversion
│       │   ├── payments.py          # payment registration + status
│       │   ├── budgets.py           # achievement computation, revision
│       │   └── reports.py           # balance sheet, P&L
│       ├── core/
│       │   ├── security.py          # bcrypt, JWT encode/decode
│       │   ├── deps.py              # get_current_user, require_role
│       │   ├── errors.py            # AppError hierarchy + handlers
│       │   └── enums.py             # every enum in one place
│       └── tests/
│           ├── test_posting_engine.py   # highest-value tests
│           ├── test_invoice_flow.py
│           ├── test_bill_flow.py
│           ├── test_budget.py
│           └── test_reports.py
│
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx                  # router
        ├── lib/
        │   ├── api.ts               # fetch wrapper, auth header, error normalising
        │   ├── money.ts             # formatting ONLY, never arithmetic
        │   └── utils.ts             # cn()
        ├── hooks/
        │   ├── useApi.ts            # data + loading + error + refetch
        │   └── useAuth.ts
        ├── components/
        │   ├── ui/                  # shadcn primitives
        │   ├── layout/              # AppShell, Sidebar, Topbar
        │   └── shared/              # ★ DataTable, KanbanGrid, FormShell,
        │                            #   StatusBadge, ViewSwitcher, MoneyInput
        ├── pages/
        │   ├── auth/                # Login, Signup, CreateUser
        │   ├── dashboard/
        │   ├── masters/             # Contacts, Products, Analytics
        │   ├── accounting/          # ChartOfAccounts, Journals, JournalEntries
        │   ├── purchase/            # PurchaseOrders, VendorBills
        │   ├── sales/               # SalesOrders, CustomerInvoices
        │   ├── payments/
        │   ├── budgets/
        │   ├── reports/             # BalanceSheet, ProfitAndLoss, BudgetReport
        │   └── portal/              # contact-role view of own invoices/bills
        └── types/
            └── api.ts               # TS types mirroring Pydantic schemas
```

### 4.1 Layering rule

```
routers/  →  services/  →  models/
```

- **Routers** parse input, check auth, call one service function, shape the response.
  A router function should rarely exceed 15 lines and must contain no `if` on business
  conditions.
- **Services** own all business logic and all transaction boundaries.
- **Models** are structure only. No behaviour beyond simple hybrid properties.

A router must never import another router. A service may import another service.

---

## 5. Environment and local setup

```yaml
docker_compose:
  file: "docker-compose.yml"
  services:
    db:
      image: "postgres:16"
      container_name: "urbanfurniture-db"
      environment:
        POSTGRES_DB: "urbanfurniture"
        POSTGRES_USER: "admin"
        POSTGRES_PASSWORD: "admin123"
      ports: ["5432:5432"]
      volumes: ["pgdata:/var/lib/postgresql/data"]
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U admin -d urbanfurniture"]
        interval: "5s"
        retries: 5
  volumes: ["pgdata"]

backend_env:
  file: "backend/.env"
  gitignored: true
  template_committed_as: ".env.example"
  variables:
    DATABASE_URL: "postgresql+psycopg://admin:admin123@localhost:5432/urbanfurniture"
    JWT_SECRET: "dev-secret-change-me"
    JWT_ALGORITHM: "HS256"
    JWT_EXPIRE_MINUTES: "480"
    CORS_ORIGINS: "http://localhost:5173"
    UPLOAD_DIR: "./uploads"

frontend_env:
  file: "frontend/.env"
  variables:
    VITE_API_BASE_URL: "http://localhost:8000/api"

onboarding_commands:
  order_matters: true
  steps:
    - "python3 --version   # confirm 3.10+ before anything else"
    - "docker compose up -d"
    - "cd backend && python -m venv .venv && source .venv/bin/activate"
    - "pip install -r requirements.txt"
    - "cp .env.example .env"
    - "python -c 'from app.database import init_db; init_db()'   # create_all"
    - "python seed.py"
    - "uvicorn app.main:app --reload --port 8000"
    - "cd ../frontend && npm install && npm run dev"

schema_change_protocol:
  why_no_migrations: "See §3 explicitly_excluded.alembic"
  procedure:
    - "Author edits the SQLAlchemy model and commits"
    - "Author posts in team chat: 'schema changed — reset your DB'"
    - "Every teammate runs: docker compose down -v && docker compose up -d"
    - "Then: python -c 'from app.database import init_db; init_db()' && python seed.py"
  rule: >
    seed.py must be idempotent and must recreate a complete, demo-ready dataset
    in under 10 seconds. It is run many times a day. Treat it as production code.

offline_guarantee:
  statement: >
    After the initial `pip install` and `npm install`, the application requires
    zero network access. Postgres is local, there are no third-party APIs, no CDN
    fonts, and no cloud services. Tailwind compiles at build time.
  verification: "Disable wifi, restart both servers, run the full demo script (§18.2)."
```

---

## 6. Background: the accounting model

> **Read this section before writing any service code.** Most defects in accounting
> software come from not understanding this, not from bad programming.

### 6.1 Accounts and account types

An **account** is a bucket that money flows into and out of. Every account has a **type**,
and the type decides which report it appears on and on which side.

```yaml
account_groups:
  balance_sheet:
    types: [asset, liability, bank, capital, cash]
    meaning: "A snapshot of what the business owns and owes at a point in time"
  profit_and_loss:
    types: [income, expense, other_expense]
    meaning: "Flows over a period — what was earned and what was spent"

normal_balance:
  # 'debit' means the account increases when debited
  asset: debit
  bank: debit
  cash: debit
  expense: debit
  other_expense: debit
  liability: credit
  capital: credit
  income: credit
```

### 6.2 Debits and credits

Forget any intuition about "debit = money out". In double-entry:

- **Debit** increases assets and expenses; decreases liabilities, capital, income.
- **Credit** increases liabilities, capital, income; decreases assets and expenses.

Every transaction touches at least two accounts, and total debits equal total credits.
That is the whole system.

### 6.3 The four transactions this system produces

```yaml
transactions:
  customer_invoice_confirmed:
    narrative: "We sold goods. The customer now owes us money and we earned income."
    debit:
      account: "Debtors A/c (type=asset)"
      amount: "invoice total"
      partner: "the customer"
    credit:
      accounts: "each invoice line's account (normally Sales Income A/c), grouped and summed"
      amount: "line totals"
    journal: "Sales"

  vendor_bill_confirmed:
    narrative: "We bought goods. We incurred an expense and now owe the vendor."
    debit:
      accounts: "each bill line's account (normally Purchase Expense A/c), grouped and summed"
    credit:
      account: "Creditors A/c (type=liability)"
      amount: "bill total"
      partner: "the vendor"
    journal: "Purchase"

  invoice_payment_received:
    narrative: "The customer paid. Cash went up, the amount they owe went down."
    debit:
      account: "Bank A/c or Cash A/c (from the chosen journal's default_account)"
    credit:
      account: "Debtors A/c"
      partner: "the customer"
    journal: "Bank or Cash (user-selected)"

  bill_payment_sent:
    narrative: "We paid the vendor. What we owe went down, cash went down."
    debit:
      account: "Creditors A/c"
      partner: "the vendor"
    credit:
      account: "Bank A/c or Cash A/c (from the chosen journal's default_account)"
    journal: "Bank or Cash (user-selected)"

  manual_journal_entry:
    narrative: "Any other adjustment, entered directly by an accountant."
    rule: "User supplies all lines. Engine only enforces balance."
```

### 6.4 Why reports need no report tables

```yaml
report_derivation:
  balance_sheet:
    assets:
      Bank: "SUM(debit - credit) over lines whose account.type = 'bank'"
      Cash: "SUM(debit - credit) over lines whose account.type = 'cash'"
      Debtors: "SUM(debit - credit) over lines whose account.type = 'asset'"
    liabilities:
      Capital: "SUM(credit - debit) over lines whose account.type = 'capital'"
      Creditors: "SUM(credit - debit) over lines whose account.type = 'liability'"
    identity: "total_assets == total_liabilities  # if this fails, the ledger is broken"

  profit_and_loss:
    income_from_sales: "SUM(credit - debit) where account.type = 'income'"
    total_income: "income_from_sales"
    purchase_expense: "SUM(debit - credit) where account.type = 'expense'"
    other_expense: "SUM(debit - credit) where account.type = 'other_expense'"
    total_expenses: "purchase_expense + other_expense"
    net_income: "total_income - total_expenses"

  scope: "Only lines belonging to journal entries in state='posted'. Drafts never appear."
```

### 6.5 Analytic accounts — the second dimension

Every invoice line and bill line carries **two** classifications:

1. `account_id` — the real ledger account. Drives Balance Sheet and P&L. Mandatory.
2. `analytic_account_id` — a project/cost-centre tag. Drives budgets only. Optional.

They are independent. The analytic dimension never touches the ledger and never affects
the Balance Sheet. It exists purely so budgets can ask "how much did Project 1 earn and
spend this period?"

This is why `analytic_account_id` lives on the **document line**, not on the journal entry
line — budgets read documents, reports read the ledger.

---

## 7. Database schema

> Deeply nested YAML. Every column, type, constraint, and index is prescriptive.
> All money columns are `NUMERIC(14,2)`. All tables have `id BIGSERIAL PRIMARY KEY`,
> `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
> These three are omitted from each table below for brevity — **add them everywhere**.

### 7.1 Enums

```yaml
enums:
  user_role:
    values: [admin, accountant, contact]
    notes: >
      The mockup's Create User screen shows radio buttons 'User' and 'Administrator',
      while its annotation describes three roles. Resolution:
        - 'Administrator' radio  -> admin
        - 'User' radio           -> contact  (portal user, must be linked to a partner)
        - Public self-signup     -> accountant  (the mockup calls this 'invoicing user')
      Document this mapping in the UI with helper text.

  partner_type: [customer, vendor, both]
  product_type: [goods, service, combo]

  account_group: [balance_sheet, profit_and_loss]
  account_type:
    [asset, liability, bank, capital, cash, income, expense, other_expense]
  journal_type: [sales, purchase, bank, cash]

  document_state: [draft, confirmed, cancelled]
  journal_entry_state: [draft, posted, cancelled]
  payment_status: [not_paid, partial, paid]
  payment_type: [send, receive]
  payment_state: [draft, confirmed, cancelled]

  budget_state: [draft, confirmed, revised, cancelled]
  budget_line_type: [income, expense]
```

### 7.2 Authentication and identity

```yaml
tables:
  users:
    purpose: "Login identity and authorisation role."
    columns:
      name: { type: "VARCHAR(120)", null: false }
      login_id:
        {
          type: "VARCHAR(12)",
          null: false,
          unique: true,
          constraint: "length between 6 and 12",
        }
      email: { type: "VARCHAR(255)", null: false, unique: true }
      password_hash:
        { type: "VARCHAR(255)", null: false, notes: "bcrypt, cost factor 12" }
      role: { type: "user_role", null: false, default: "accountant" }
      partner_id:
        { type: "BIGINT", null: true, fk: "partners.id ON DELETE SET NULL" }
      is_active: { type: "BOOLEAN", null: false, default: true }
    constraints:
      - name: "ck_users_login_length"
        sql: "CHECK (char_length(login_id) BETWEEN 6 AND 12)"
      - name: "ck_users_contact_needs_partner"
        sql: "CHECK (role <> 'contact' OR partner_id IS NOT NULL)"
        why: "A portal user with no linked partner could see nothing, or worse, everything."
    indexes:
      - "UNIQUE (login_id)"
      - "UNIQUE (email)"
      - "INDEX (partner_id)"
    security_notes:
      - "password_hash is NEVER returned by any endpoint, in any shape."
      - "Pydantic response models must not include it. Verify by reading /docs."
```

### 7.3 Master data

```yaml
tables:
  partners:
    purpose: "Contacts — customers and vendors. Mockup: Contact Master."
    columns:
      name: { type: "VARCHAR(200)", null: false }
      email:
        {
          type: "VARCHAR(255)",
          null: true,
          unique: true,
          notes: "Mockup marks email 'Unique Email'. Unique but nullable.",
        }
      phone: { type: "VARCHAR(20)", null: true }
      partner_type: { type: "partner_type", null: false, default: "customer" }
      street: { type: "VARCHAR(255)", null: true }
      city: { type: "VARCHAR(100)", null: true }
      state: { type: "VARCHAR(100)", null: true }
      country: { type: "VARCHAR(100)", null: true }
      pincode: { type: "VARCHAR(10)", null: true }
      image_path: { type: "VARCHAR(500)", null: true, priority: "P1" }
      is_active: { type: "BOOLEAN", null: false, default: true }
    indexes:
      - "UNIQUE (email) WHERE email IS NOT NULL"
      - "INDEX (name)"
    delete_policy:
      rule: "Soft delete via is_active=false. Never hard-delete a partner."
      why: "Partners are referenced by posted journal entry lines, which are immutable."

  product_categories:
    purpose: "Mockup: 'Category can be created and saved on the fly (Many2one field)'."
    columns:
      name: { type: "VARCHAR(120)", null: false, unique: true }

  products:
    columns:
      name: { type: "VARCHAR(200)", null: false }
      product_type: { type: "product_type", null: false, default: "goods" }
      category_id:
        {
          type: "BIGINT",
          null: true,
          fk: "product_categories.id ON DELETE SET NULL",
        }
      sales_price: { type: "NUMERIC(14,2)", null: false, default: "0.00" }
      cost_price: { type: "NUMERIC(14,2)", null: false, default: "0.00" }
      image_path: { type: "VARCHAR(500)", null: true, priority: "P1" }
      is_active: { type: "BOOLEAN", null: false, default: true }
    constraints:
      - "CHECK (sales_price >= 0)"
      - "CHECK (cost_price >= 0)"
    indexes: ["INDEX (name)", "INDEX (category_id)"]

  analytic_accounts:
    purpose: >
      Project / cost-centre tags. The budget dimension. Mockup: 'Analyticals'.
    columns:
      name: { type: "VARCHAR(150)", null: false, unique: true }
      is_active: { type: "BOOLEAN", null: false, default: true }
    notes: >
      The mockup's Analyticals form shows a read-only list of every budget in which
      this analytic appears. That is a computed join, not a column.
```

### 7.4 Chart of accounts and journals

```yaml
tables:
  accounts:
    purpose: "Chart of Accounts. Pre-seeded; users may add more."
    columns:
      code: { type: "VARCHAR(20)", null: false, unique: true }
      name: { type: "VARCHAR(150)", null: false, unique: true }
      account_group: { type: "account_group", null: false }
      account_type: { type: "account_type", null: false }
      is_archived:
        {
          type: "BOOLEAN",
          null: false,
          default: false,
          notes: "Mockup has an 'Archived' button on the CoA list view.",
        }
    constraints:
      - name: "ck_accounts_group_type_consistent"
        sql: >
          CHECK (
            (account_group = 'balance_sheet'
              AND account_type IN ('asset','liability','bank','capital','cash'))
            OR
            (account_group = 'profit_and_loss'
              AND account_type IN ('income','expense','other_expense'))
          )
        why: >
          Prevents an Income account being filed under Balance Sheet, which would
          silently corrupt both reports. Enforced in the database, not just the UI.
    indexes: ["UNIQUE (code)", "INDEX (account_type)"]
    delete_policy: "Archive only. Never delete — posted lines reference these."

  journals:
    purpose: "Groups entries by nature and supplies a default account."
    columns:
      name: { type: "VARCHAR(100)", null: false, unique: true }
      journal_type: { type: "journal_type", null: false }
      default_account_id:
        { type: "BIGINT", null: false, fk: "accounts.id ON DELETE RESTRICT" }
    notes: >
      Bank/Cash journals' default_account is the account debited on receipt and
      credited on payment. Sales/Purchase journals' default is used to prefill
      document line accounts.
```

### 7.5 The general ledger — core tables

```yaml
tables:

  journal_entries:
    purpose: "★ The ledger header. Every financial event in the system lands here."
    columns:
      number:       { type: "VARCHAR(30)", null: false, unique: true,
                      notes: "Copied from the source document's number, or JE/YYYY/NNNN if manual" }
      entry_date:   { type: "DATE", null: false, notes: "Mockup: 'Accounting Date'" }
      journal_id:   { type: "BIGINT", null: false, fk: "journals.id ON DELETE RESTRICT" }
      partner_id:   { type: "BIGINT", null: true,  fk: "partners.id ON DELETE RESTRICT" }
      reference:    { type: "VARCHAR(120)", null: true }
      state:        { type: "journal_entry_state", null: false, default: "draft" }
      source_type:  { type: "VARCHAR(30)", null: true,
                      values: ["customer_invoice", "vendor_bill", "payment", "manual"] }
      source_id:    { type: "BIGINT", null: true }
      total_amount: { type: "NUMERIC(14,2)", null: false, default: "0.00",
                      notes: >
                        Denormalised sum(debit) for list-view display only. Never used
                        in any report computation. The single permitted exception to P5,
                        justified because the Journal Entries list would otherwise need
                        an aggregate subquery per row. Reports always re-derive from lines. }
    indexes:
      - "UNIQUE (number)"
      - "INDEX (entry_date)"
      - "INDEX (state, entry_date)   -- reports filter state='posted' then date range"
      - "INDEX (source_type, source_id)"
    immutability: >
      Once state='posted', no UPDATE to any column except a future reversal link,
      and no DELETE, ever. Enforce in the service layer and never expose a PUT/DELETE
      route for posted entries.

  journal_entry_lines:
    purpose: "★ The ledger detail. EVERY financial report reads only this table."
    columns:
      journal_entry_id: { type: "BIGINT", null: false, fk: "journal_entries.id ON DELETE CASCADE" }
      account_id:       { type: "BIGINT", null: false, fk: "accounts.id ON DELETE RESTRICT" }
      partner_id:       { type: "BIGINT", null: true,  fk: "partners.id ON DELETE RESTRICT" }
      label:            { type: "VARCHAR(255)", null: true }
      debit:            { type: "NUMERIC(14,2)", null: false, default: "0.00" }
      credit:           { type: "NUMERIC(14,2)", null: false, default: "0.00" }
      sequence:         { type: "INTEGER", null: false, default: 10 }
    constraints:
      - name: "ck_jel_non_negative"
        sql: "CHECK (debit >= 0 AND credit >= 0)"
      - name: "ck_jel_one_side_only"
        sql: "CHECK (NOT (debit > 0 AND credit > 0))"
        why: >
          A line is either a debit or a credit, never both. This is the strongest
          database-level guarantee available for double-entry, and it is exactly
          the sort of constraint the Database Design criterion rewards.
      - name: "ck_jel_not_both_zero"
        sql: "CHECK (debit > 0 OR credit > 0)"
        why: "A zero line carries no information and would pass balance checks silently."
    indexes:
      - name: "ix_jel_account_entry"
        sql: "INDEX (account_id, journal_entry_id)"
        why: "Balance Sheet and P&L group by account; this keeps them fast at scale."
      - name: "ix_jel_partner"
        sql: "INDEX (partner_id)"
        why: "Partner ledger / portal queries."
      - "INDEX (journal_entry_id)"
    balance_rule:
      statement: "SUM(debit) == SUM(credit) across all lines of one journal_entry"
      enforced_in: "services/accounting.py::post_journal_entry — see §8"
      not_a_db_constraint_because: >
        Postgres cannot express a cross-row constraint without a deferred trigger.
        A trigger is defensible but adds a second source of truth. We enforce in the
        service layer, which is the ONLY writer (P6), and we test it hard (§10.4).
        A `GET /api/reports/trial-balance` endpoint exists so the invariant is
        continuously verifiable at runtime.
```

### 7.6 Purchase cycle

```yaml
tables:

  purchase_orders:
    columns:
      number:      { type: "VARCHAR(20)", null: false, unique: true, format: "P00001" }
      vendor_id:   { type: "BIGINT", null: false, fk: "partners.id ON DELETE RESTRICT" }
      order_date:  { type: "DATE", null: false, default: "CURRENT_DATE" }
      state:       { type: "document_state", null: false, default: "draft" }
      total_amount:{ type: "NUMERIC(14,2)", null: false, default: "0.00" }
    indexes: ["UNIQUE (number)", "INDEX (vendor_id)", "INDEX (state)"]
    notes: "A PO produces NO journal entry. It is a commitment, not a financial event."

  purchase_order_lines:
    columns:
      purchase_order_id:   { type: "BIGINT", null: false, fk: "purchase_orders.id ON DELETE CASCADE" }
      product_id:          { type: "BIGINT", null: false, fk: "products.id ON DELETE RESTRICT" }
      analytic_account_id: { type: "BIGINT", null: true,  fk: "analytic_accounts.id ON DELETE RESTRICT" }
      quantity:            { type: "NUMERIC(14,2)", null: false }
      unit_price:          { type: "NUMERIC(14,2)", null: false }
      line_total:          { type: "NUMERIC(14,2)", null: false,
                             computation: "quantity * unit_price, computed SERVER-SIDE on save" }
      sequence:            { type: "INTEGER", null: false, default: 10 }
    constraints:
      - "CHECK (quantity > 0)"
      - "CHECK (unit_price >= 0)"

  vendor_bills:
    columns:
      number:            { type: "VARCHAR(30)", null: false, unique: true, format: "BILL/2026/0001" }
      vendor_id:         { type: "BIGINT", null: false, fk: "partners.id ON DELETE RESTRICT" }
      bill_reference:    { type: "VARCHAR(60)", null: true, notes: "Vendor's own doc number, e.g. ABC-26-001" }
      bill_date:         { type: "DATE", null: false, default: "CURRENT_DATE" }
      due_date:          { type: "DATE", null: true }
      state:             { type: "document_state", null: false, default: "draft" }
      total_amount:      { type: "NUMERIC(14,2)", null: false, default: "0.00" }
      source_po_id:      { type: "BIGINT", null: true, fk: "purchase_orders.id ON DELETE SET NULL",
                           notes: >
                             Mockup: the PO button on the bill is shown only when this is
                             non-null. Hidden for bills created fresh. }
      journal_entry_id:  { type: "BIGINT", null: true, fk: "journal_entries.id ON DELETE RESTRICT",
                           notes: "Set on confirm. Null while draft." }
    computed_not_stored:
      amount_paid:    "SUM(payments.amount) WHERE bill_id = this AND state='confirmed'"
      amount_due:     "total_amount - amount_paid"
      payment_status: "paid if due==0 ; not_paid if due==total ; else partial"
    constraints:
      - "CHECK (due_date IS NULL OR due_date >= bill_date)"
    indexes: ["UNIQUE (number)", "INDEX (vendor_id)", "INDEX (state)", "INDEX (source_po_id)"]

  vendor_bill_lines:
    columns:
      vendor_bill_id:      { type: "BIGINT", null: false, fk: "vendor_bills.id ON DELETE CASCADE" }
      product_id:          { type: "BIGINT", null: false, fk: "products.id ON DELETE RESTRICT" }
      account_id:          { type: "BIGINT", null: false, fk: "accounts.id ON DELETE RESTRICT",
                             default_behaviour: "prefill with Purchase Expense A/c; user may override" }
      analytic_account_id: { type: "BIGINT", null: true, fk: "analytic_accounts.id ON DELETE RESTRICT" }
      quantity:            { type: "NUMERIC(14,2)", null: false }
      unit_price:          { type: "NUMERIC(14,2)", null: false }
      line_total:          { type: "NUMERIC(14,2)", null: false }
      sequence:            { type: "INTEGER", null: false, default: 10 }
    constraints: ["CHECK (quantity > 0)", "CHECK (unit_price >= 0)"]
    indexes:
      - name: "ix_vbl_analytic"
        sql: "INDEX (analytic_account_id)"
        why: "Budget achievement scans bill lines by analytic. Without this it is a seq scan."
```

### 7.7 Sales cycle

> Structurally the mirror of §7.6. Same shapes, opposite ledger direction.

```yaml
tables:

  sales_orders:
    columns:
      number:      { type: "VARCHAR(20)", null: false, unique: true, format: "S00001" }
      customer_id: { type: "BIGINT", null: false, fk: "partners.id ON DELETE RESTRICT" }
      order_date:  { type: "DATE", null: false, default: "CURRENT_DATE" }
      state:       { type: "document_state", null: false, default: "draft" }
      total_amount:{ type: "NUMERIC(14,2)", null: false, default: "0.00" }
    notes: "Produces NO journal entry."

  sales_order_lines:
    columns:
      sales_order_id:      { type: "BIGINT", null: false, fk: "sales_orders.id ON DELETE CASCADE" }
      product_id:          { type: "BIGINT", null: false, fk: "products.id ON DELETE RESTRICT" }
      analytic_account_id: { type: "BIGINT", null: true,  fk: "analytic_accounts.id ON DELETE RESTRICT" }
      quantity:            { type: "NUMERIC(14,2)", null: false }
      unit_price:          { type: "NUMERIC(14,2)", null: false }
      line_total:          { type: "NUMERIC(14,2)", null: false }
      sequence:            { type: "INTEGER", null: false, default: 10 }
    constraints: ["CHECK (quantity > 0)", "CHECK (unit_price >= 0)"]

  customer_invoices:
    columns:
      number:            { type: "VARCHAR(30)", null: false, unique: true, format: "INV/2026/0001" }
      customer_id:       { type: "BIGINT", null: false, fk: "partners.id ON DELETE RESTRICT" }
      invoice_reference: { type: "VARCHAR(60)", null: true }
      invoice_date:      { type: "DATE", null: false, default: "CURRENT_DATE" }
      due_date:          { type: "DATE", null: true }
      state:             { type: "document_state", null: false, default: "draft" }
      total_amount:      { type: "NUMERIC(14,2)", null: false, default: "0.00" }
      source_so_id:      { type: "BIGINT", null: true, fk: "sales_orders.id ON DELETE SET NULL" }
      journal_entry_id:  { type: "BIGINT", null: true, fk: "journal_entries.id ON DELETE RESTRICT" }
    computed_not_stored:
      amount_paid:    "SUM(payments.amount) WHERE invoice_id = this AND state='confirmed'"
      amount_due:     "total_amount - amount_paid"
      payment_status: "paid | partial | not_paid"
    indexes:
      - "UNIQUE (number)"
      - "INDEX (customer_id)   -- portal: WHERE customer_id = current_user.partner_id"
      - "INDEX (state)"

  customer_invoice_lines:
    columns:
      customer_invoice_id: { type: "BIGINT", null: false, fk: "customer_invoices.id ON DELETE CASCADE" }
      product_id:          { type: "BIGINT", null: false, fk: "products.id ON DELETE RESTRICT" }
      account_id:          { type: "BIGINT", null: false, fk: "accounts.id ON DELETE RESTRICT",
                             default_behaviour: "prefill with Sales Income A/c" }
      analytic_account_id: { type: "BIGINT", null: true, fk: "analytic_accounts.id ON DELETE RESTRICT" }
      quantity:            { type: "NUMERIC(14,2)", null: false }
      unit_price:          { type: "NUMERIC(14,2)", null: false }
      line_total:          { type: "NUMERIC(14,2)", null: false }
      sequence:            { type: "INTEGER", null: false, default: 10 }
    indexes:
      - "INDEX (analytic_account_id)   -- budget achievement, income side"
```

### 7.8 Payments

```yaml
tables:
  payments:
    purpose: >
      ONE table for both directions. The mockup's Bill Payment and Invoice Payment
      screens are the same form with payment_type flipped.
    columns:
      number:
        {
          type: "VARCHAR(30)",
          null: false,
          unique: true,
          format: "PAY/2026/0001",
        }
      payment_type:
        {
          type: "payment_type",
          null: false,
          notes: "send = we pay vendor; receive = customer pays us",
        }
      partner_id:
        { type: "BIGINT", null: false, fk: "partners.id ON DELETE RESTRICT" }
      journal_id:
        {
          type: "BIGINT",
          null: false,
          fk: "journals.id ON DELETE RESTRICT",
          notes: "Mockup 'Payment Via'. Must be a bank or cash journal. Default: Bank.",
        }
      amount: { type: "NUMERIC(14,2)", null: false }
      payment_date: { type: "DATE", null: false, default: "CURRENT_DATE" }
      note: { type: "TEXT", null: true }
      state: { type: "payment_state", null: false, default: "draft" }
      invoice_id:
        {
          type: "BIGINT",
          null: true,
          fk: "customer_invoices.id ON DELETE RESTRICT",
        }
      bill_id:
        { type: "BIGINT", null: true, fk: "vendor_bills.id ON DELETE RESTRICT" }
      journal_entry_id:
        {
          type: "BIGINT",
          null: true,
          fk: "journal_entries.id ON DELETE RESTRICT",
        }
    constraints:
      - name: "ck_payments_amount_positive"
        sql: "CHECK (amount > 0)"
      - name: "ck_payments_exactly_one_target"
        sql: >
          CHECK (
            (invoice_id IS NOT NULL AND bill_id IS NULL)
            OR
            (invoice_id IS NULL AND bill_id IS NOT NULL)
          )
        why: "A payment settles exactly one document. Scope decision — see §7.8.1."
      - name: "ck_payments_direction_matches_target"
        sql: >
          CHECK (
            (payment_type = 'receive' AND invoice_id IS NOT NULL)
            OR
            (payment_type = 'send' AND bill_id IS NOT NULL)
          )
        why: "You cannot 'send' money to settle a customer invoice."
    indexes:
      - "UNIQUE (number)"
      - name: "ix_payments_invoice_state"
        sql: "INDEX (invoice_id, state)"
        why: "amount_paid aggregates filter on both columns."
      - "INDEX (bill_id, state)"
      - "INDEX (partner_id)"
```

#### 7.8.1 Scope decision — no partial reconciliation

One payment settles one document. A payment cannot be split across several invoices.

**Why:** the mockup shows Amount Due computed on a single bill/invoice, with status
derived from it. Full reconciliation (a `payment_allocations` junction table letting one
₹10,000 payment clear three invoices) is real accounting, but it costs several hours and
no scenario in the mockup requires it.

**Partial payments ARE supported** — pay ₹2,000 against a ₹6,000 invoice three times and
status moves `not_paid → partial → partial → paid`. That is the behaviour the mockup
specifies, and it is what the demo will show.

**If asked by a judge:** "We support partial payments against a document. Full
cross-document reconciliation is the next thing we'd build — it needs an allocation table
between payment lines and invoice lines."

### 7.9 Budgets

```yaml
tables:
  budgets:
    columns:
      name: { type: "VARCHAR(150)", null: false }
      start_date: { type: "DATE", null: false }
      end_date: { type: "DATE", null: false }
      responsible_id:
        {
          type: "BIGINT",
          null: true,
          fk: "partners.id ON DELETE SET NULL",
          notes: "Mockup: 'Select from Contacts created'",
        }
      state: { type: "budget_state", null: false, default: "draft" }
      revision_of_id:
        {
          type: "BIGINT",
          null: true,
          fk: "budgets.id ON DELETE SET NULL",
          notes: "Set on the NEW budget, pointing back to the original",
        }
      revised_with_id:
        {
          type: "BIGINT",
          null: true,
          fk: "budgets.id ON DELETE SET NULL",
          notes: "Set on the ORIGINAL, pointing forward to the revision",
        }
    constraints:
      - "CHECK (end_date >= start_date)"
      - name: "ck_budget_not_self_revision"
        sql: "CHECK (revision_of_id IS NULL OR revision_of_id <> id)"
    indexes: ["INDEX (state)", "INDEX (start_date, end_date)"]
    self_reference_note: >
      Two nullable self-FKs form a doubly-linked revision chain. The mockup requires
      navigation in BOTH directions: the original shows a link to its revision, and
      the revision shows a clickable 'Revision Of' link back to the original.

  budget_lines:
    columns:
      budget_id:
        { type: "BIGINT", null: false, fk: "budgets.id ON DELETE CASCADE" }
      analytic_account_id:
        {
          type: "BIGINT",
          null: false,
          fk: "analytic_accounts.id ON DELETE RESTRICT",
        }
      line_type: { type: "budget_line_type", null: false }
      committed_amount: { type: "NUMERIC(14,2)", null: false }
      sequence: { type: "INTEGER", null: false, default: 10 }
    constraints:
      - "CHECK (committed_amount > 0)"
      - name: "uq_budget_line_analytic"
        sql: "UNIQUE (budget_id, analytic_account_id, line_type)"
        why: "Two lines for the same analytic and type would double-count achievement."
    computed_not_stored:
      achieved_amount: >
        line_type='income'  -> SUM(customer_invoice_lines.line_total)
                               JOIN customer_invoices ci
                               WHERE ci.state = 'confirmed'
                                 AND ci.invoice_date BETWEEN budget.start_date AND budget.end_date
                                 AND line.analytic_account_id = this.analytic_account_id
        line_type='expense' -> same shape over vendor_bill_lines / vendor_bills.bill_date
      achieved_percent: "ROUND(achieved_amount / committed_amount * 100, 2); 0 if committed is 0"
      amount_to_achieve: "committed_amount - achieved_amount   # may go negative when over budget"
      visibility: "achieved_* fields are returned only when budget.state IN ('confirmed','revised')"
```

#### 7.9.1 Why achievement is computed, not stored

Storing `achieved_amount` would require recalculation whenever an invoice is confirmed,
a bill is confirmed, a document is cancelled, an analytic tag is changed, or a budget
period is edited. That is five invalidation paths. Computing on read has one code path
and cannot drift.

**Performance:** with `ix_vbl_analytic` and `ix_cil_analytic` in place, each budget line
is an indexed aggregate over a few hundred rows. At demo scale this is sub-millisecond.
The honest answer to a scalability question: _"It's an indexed aggregate. If the ledger
grew to millions of lines we'd add a materialised view refreshed on document confirm —
but we'd measure before adding that complexity."_

---

## 8. The posting engine — `services/accounting.py`

> This module is the architectural centre of the project. It is what the Modularity and
> Logic criteria are measured on. Build it first, test it hardest, and demo it proudly.

### 8.1 Contract

```yaml
module: "app/services/accounting.py"

exclusive_write_authority:
  statement: >
    This module contains the ONLY code in the repository that INSERTs into
    journal_entries or journal_entry_lines. No router, no other service, no script.
  verification: >
    grep -rn "JournalEntry(" app/ --include=*.py
    Must return hits ONLY in services/accounting.py, tests/, and seed.py.

public_functions:
  post_journal_entry:
    signature: >
      post_journal_entry(
          db: Session,
          *,
          entry_date: date,
          journal_id: int,
          lines: list[LineInput],
          partner_id: int | None = None,
          reference: str | None = None,
          source_type: str | None = None,
          source_id: int | None = None,
          number: str | None = None,
      ) -> JournalEntry
    line_input_shape:
      account_id: int
      debit: Decimal # >= 0
      credit: Decimal # >= 0
      partner_id: "int | None"
      label: "str | None"
    behaviour_ordered:
      - step: 1
        action: "Reject if lines is empty"
        raises: "UnbalancedEntryError('A journal entry must have at least two lines')"
      - step: 2
        action: "Reject if fewer than 2 lines"
        raises: "UnbalancedEntryError"
        why: "A single-line entry cannot balance by definition."
      - step: 3
        action: "Per line: reject debit<0, credit<0, both>0, or both==0"
        raises: "InvalidLineError with the 0-based line index in the payload"
      - step: 4
        action: "total_debit = sum(l.debit); total_credit = sum(l.credit)"
        note: "Sum Decimals. Never float. Never round mid-sum."
      - step: 5
        action: "If total_debit != total_credit -> raise"
        raises: >
          UnbalancedEntryError(total_debit=..., total_credit=...,
                               difference=total_debit - total_credit)
        note: >
          Decimal equality is exact — no epsilon comparison. If you find yourself
          writing abs(a-b) < 0.01 you have introduced floats somewhere. Find them.
      - step: 6
        action: "Verify every account_id exists and is not archived"
        raises: "AccountNotFoundError | AccountArchivedError"
      - step: 7
        action: "Verify journal_id exists"
        raises: "JournalNotFoundError"
      - step: 8
        action: "number = provided number, else sequences.next_journal_entry_number(db)"
      - step: 9
        action: >
          Create JournalEntry(state='posted', total_amount=total_debit) and all
          JournalEntryLine rows with sequence = 10, 20, 30...
      - step: 10
        action: "db.flush()  -- NOT db.commit()"
        why: >
          The CALLER owns the transaction boundary. The invoice service commits once,
          after both the invoice and its entry are in the session. This is how P3
          (atomicity) is achieved. A commit here would break it.
      - step: 11
        action: "return the JournalEntry instance"

  reverse_journal_entry:
    priority: "P2"
    signature: "reverse_journal_entry(db, *, entry_id: int, reversal_date: date) -> JournalEntry"
    behaviour: >
      Creates a new posted entry with debit and credit swapped on every line,
      referencing the original. The original is never modified. This is how a
      confirmed document is undone (P4).

private_helpers:
  _validate_lines: "steps 1-3"
  _assert_balanced: "steps 4-5"
  _resolve_accounts: "step 6, single query with IN clause — do not query per line"
```

### 8.2 Callers — exact line construction

```yaml
callers:
  customer_invoice_confirm:
    module: "services/documents.py::confirm_customer_invoice"
    transaction: "one db.commit() at the very end, after post_journal_entry returns"
    line_construction:
      debit_side:
        rule: "EXACTLY ONE line"
        account: "Debtors A/c  (lookup: accounts.code='1200' or account_type='asset' seeded as Debtors)"
        partner: "invoice.customer_id"
        debit: "invoice.total_amount"
        label: "invoice.number"
      credit_side:
        rule: >
          One line PER DISTINCT account_id across the invoice lines, with line_total
          summed within each group. Do NOT emit one credit line per invoice line.
        pseudocode: |
          grouped = defaultdict(Decimal)
          for line in invoice.lines:
              grouped[line.account_id] += line.line_total
          credit_lines = [
              Line(account_id=aid, credit=amt, partner_id=invoice.customer_id)
              for aid, amt in grouped.items()
          ]
        why: >
          Most invoices use Sales Income A/c on every line, producing one credit line.
          But an invoice mixing a goods line and a service line with different income
          accounts must produce two credit lines. Grouping handles both without a
          special case, and keeps the ledger readable.
      journal: "the Sales journal (journal_type='sales')"
      entry_date: "invoice.invoice_date"
      number: "invoice.number"
      source_type: "customer_invoice"
      source_id: "invoice.id"
    worked_example:
      given: "INV/2026/0001, customer Mr Rahul, 2 lines: Chair 3x2000=6000, Sofa 1x4000=4000, both Sales Income A/c"
      produces:
        - {
            account: "Debtors A/c",
            partner: "Mr Rahul",
            debit: "10000.00",
            credit: "0.00",
          }
        - {
            account: "Sales Income A/c",
            partner: "Mr Rahul",
            debit: "0.00",
            credit: "10000.00",
          }
      totals: { debit: "10000.00", credit: "10000.00" }

  vendor_bill_confirm:
    module: "services/documents.py::confirm_vendor_bill"
    line_construction:
      debit_side:
        rule: "One line per distinct account_id across bill lines, summed (mirror of invoice credit side)"
        partner: "bill.vendor_id"
      credit_side:
        rule: "EXACTLY ONE line"
        account: "Creditors A/c (account_type='liability')"
        partner: "bill.vendor_id"
        credit: "bill.total_amount"
      journal: "the Purchase journal"
      entry_date: "bill.bill_date"
      number: "bill.number"
    worked_example:
      given: "BILL/2026/0001, vendor Mr Rahul, one line Table 3x2000=6000 on Purchase Expense A/c"
      produces:
        - {
            account: "Purchase Expense A/c",
            partner: "Mr Rahul",
            debit: "6000.00",
            credit: "0.00",
          }
        - {
            account: "Creditors A/c",
            partner: "Mr Rahul",
            debit: "0.00",
            credit: "6000.00",
          }

  payment_receive_confirm:
    module: "services/payments.py::confirm_payment"
    line_construction:
      - {
          account: "payment.journal.default_account_id (Bank or Cash)",
          debit: "payment.amount",
        }
      - {
          account: "Debtors A/c",
          credit: "payment.amount",
          partner: "payment.partner_id",
        }
    journal: "payment.journal_id"
    entry_date: "payment.payment_date"
    number: "payment.number"
    effect: >
      Debtors is now debited by the invoice and credited by the payment. When fully
      paid the two net to zero, and the customer disappears from the Debtors balance
      on the Balance Sheet. This is the system working correctly — show it in the demo.

  payment_send_confirm:
    line_construction:
      - {
          account: "Creditors A/c",
          debit: "payment.amount",
          partner: "payment.partner_id",
        }
      - {
          account: "payment.journal.default_account_id",
          credit: "payment.amount",
        }

  manual_journal_entry:
    module: "routers/journal_entries.py -> services/accounting.py directly"
    line_construction: "Exactly as submitted by the user. The engine only validates."
    source_type: "manual"
```

### 8.3 Anti-patterns — reject these in code review

```yaml
forbidden:
  - pattern: "Any INSERT into journal_entry_lines outside services/accounting.py"
    instead: "Call post_journal_entry"
  - pattern: "float() or arithmetic on a float anywhere near money"
    instead: "Decimal, everywhere, end to end"
  - pattern: "abs(total_debit - total_credit) < 0.01"
    instead: "total_debit != total_credit — Decimal comparison is exact"
  - pattern: "db.commit() inside post_journal_entry"
    instead: "db.flush(); the caller commits"
  - pattern: "A stored balance column on partners or accounts"
    instead: "Aggregate journal_entry_lines on read (P5)"
  - pattern: "Computing line_total on the client and trusting it"
    instead: "Server recomputes quantity * unit_price and ignores any client value"
  - pattern: "Editing a posted entry to 'fix' something"
    instead: "reverse_journal_entry, then post a corrected one"
  - pattern: "try/except around post_journal_entry that swallows the error and continues"
    instead: "Let it propagate. A failed post MUST abort the whole request."
```

---

## 9. API contract

```yaml
api:
  base_url: "http://localhost:8000/api"
  docs: "http://localhost:8000/docs   # FastAPI auto-generated OpenAPI — demo this"
  auth: "Authorization: Bearer <JWT>"
  content_type: "application/json"

  conventions:
    money_wire_format:
      type: "string"
      example: "\"6000.00\""
      why: >
        JSON numbers are IEEE-754 doubles. Serialising Decimal as a JSON number
        re-introduces the exact float problem Decimal exists to avoid. Send strings.
        Pydantic v2: json_encoders={Decimal: str} on the base config.
    dates: "ISO-8601 date only, YYYY-MM-DD"
    timestamps: "ISO-8601 with timezone"
    ids: "integer"
    list_envelope:
      shape: { items: [], total: 0, page: 1, page_size: 20 }
      why: "Every list endpoint paginates. No endpoint ever returns an unbounded array."
    default_page_size: 20
    max_page_size: 100

  standard_query_params:
    applies_to: "all list endpoints"
    params:
      page:      { type: int, default: 1,  min: 1 }
      page_size: { type: int, default: 20, min: 1, max: 100 }
      search:    { type: "string | null", note: "ILIKE on the resource's primary text field" }
      state:     { type: "string | null", note: "filter by state where applicable" }
      sort:      { type: "string", default: "-created_at" }

  roles:
    admin:      "full access to everything"
    accountant: "masters + transactions + reports; cannot create users"
    contact:    "read own invoices and bills; create payments against them; nothing else"

endpoints:

  auth:
    - method: POST
      path: "/auth/signup"
      auth: public
      body: { login_id: str, email: str, password: str, confirm_password: str }
      creates: "user with role='accountant' (the 'invoicing user' of the mockup)"
      returns: 201 { id, login_id, email, role }
      errors: [422 validation, 409 login_id_taken, 409 email_taken]
    - method: POST
      path: "/auth/login"
      auth: public
      body: { login_id: str, password: str }
      returns: 200 { access_token, token_type: "bearer", user: {id, name, login_id, role, partner_id} }
      errors:
        - code: 401
          message: "Invalid Login Id or Password"
          note: >
            IDENTICAL message whether the login_id is unknown or the password is wrong.
            Distinguishing them leaks which accounts exist. The mockup specifies this
            exact wording.
    - method: GET
      path: "/auth/me"
      auth: "any authenticated"
      returns: 200 "current user"
    - method: POST
      path: "/auth/users"
      auth: "admin only"
      body: { name: str, login_id: str, email: str, role: "admin|contact", password: str,
              confirm_password: str, partner_id: "int | null" }
      note: "role='contact' REQUIRES partner_id (see users table constraint)"
      returns: 201
    - method: GET
      path: "/auth/users"
      auth: "admin only"

  masters:
    partners:
      - "GET    /partners            -> paginated; ?partner_type=&search="
      - "GET    /partners/{id}"
      - "POST   /partners            -> 201"
      - "PUT    /partners/{id}"
      - "DELETE /partners/{id}       -> soft delete (is_active=false); 409 if referenced by a posted entry"
    products:
      - "GET/POST/PUT/DELETE /products    -> same shape; ?category_id=&product_type="
    product_categories:
      - "GET  /product-categories"
      - "POST /product-categories   -> supports create-on-the-fly from the product form"
    analytic_accounts:
      - "GET/POST/PUT/DELETE /analytic-accounts"
      - "GET /analytic-accounts/{id}/budgets  -> budgets referencing this analytic"

  accounting:
    accounts:
      - "GET  /accounts             -> ?account_type=&account_group=&include_archived=false"
      - "POST /accounts             -> validates group/type consistency (see CHECK constraint)"
      - "PUT  /accounts/{id}"
      - "POST /accounts/{id}/archive"
    journals:
      - "GET  /journals             -> ?journal_type="
      - "POST /journals"
    journal_entries:
      - method: GET
        path: "/journal-entries"
        returns_per_row: { date, number, partner_name, journal_name, total_amount, state }
        note: "Exactly the columns in the mockup's Journal Entries list view."
      - method: GET
        path: "/journal-entries/{id}"
        returns: "header + lines with account_name and partner_name resolved"
      - method: POST
        path: "/journal-entries"
        auth: "accountant | admin"
        body:
          entry_date: date
          journal_id: int
          reference: "str | null"
          lines: [{ account_id: int, partner_id: "int|null", label: "str|null",
                    debit: "decimal string", credit: "decimal string" }]
        behaviour: "posts immediately via the engine; created in state='posted'"
        returns: 201
        errors: [422 UNBALANCED_ENTRY, 422 INVALID_LINE, 404 ACCOUNT_NOT_FOUND]
      - method: DELETE
        path: "/journal-entries/{id}"
        response: "405 Method Not Allowed — posted entries are immutable (P4)"

  purchase:
    - "GET/POST/PUT  /purchase-orders"
    - "POST /purchase-orders/{id}/confirm   -> state=confirmed; NO journal entry"
    - "POST /purchase-orders/{id}/cancel"
    - method: POST
      path: "/purchase-orders/{id}/create-bill"
      behaviour: "copies vendor, lines, analytics, quantities, prices into a draft bill"
      sets: "bill.source_po_id = po.id"
      returns: 201 "the new draft vendor bill"
      errors: [409 PO_NOT_CONFIRMED, 409 BILL_ALREADY_EXISTS]
    - "GET/POST/PUT  /vendor-bills"
    - method: POST
      path: "/vendor-bills/{id}/confirm"
      behaviour: "★ atomic: state=confirmed + journal entry posted + link stored"
      returns: 200 "{ bill, journal_entry_id, journal_entry_number }"
      errors: [409 ALREADY_CONFIRMED, 422 NO_LINES, 422 UNBALANCED_ENTRY]
    - "GET /vendor-bills/{id}/budget-report  -> analytics used on this bill vs their budgets"

  sales:
    - "GET/POST/PUT  /sales-orders"
    - "POST /sales-orders/{id}/confirm"
    - "POST /sales-orders/{id}/create-invoice"
    - "GET/POST/PUT  /customer-invoices"
    - method: POST
      path: "/customer-invoices/{id}/confirm"
      behaviour: "★ atomic: state=confirmed + journal entry posted"
    - "GET /customer-invoices/{id}/budget-report"

  payments:
    - method: POST
      path: "/payments"
      body: { payment_type, partner_id, journal_id, amount, payment_date, note,
              invoice_id: "int|null", bill_id: "int|null" }
      behaviour: "creates in state='draft'; no ledger effect yet"
      validations:
        - "amount > 0"
        - "amount <= target document's amount_due  (422 OVERPAYMENT)"
        - "target document must be state='confirmed' (422 DOCUMENT_NOT_CONFIRMED)"
        - "journal must be bank or cash type (422 INVALID_PAYMENT_JOURNAL)"
        - "payment_type must match the target document type"
    - method: POST
      path: "/payments/{id}/confirm"
      behaviour: "★ atomic: state=confirmed + journal entry posted; target status recomputed"
    - "POST /payments/{id}/cancel   -> only from draft; 409 if already confirmed"
    - "GET  /payments               -> ?payment_type=&partner_id=&state="

  budgets:
    - "GET  /budgets                -> list with state + period"
    - method: GET
      path: "/budgets/{id}"
      returns: >
        header + lines, each line enriched with achieved_amount, achieved_percent,
        amount_to_achieve — computed live (§7.9). Achieved fields are null when
        state='draft'.
    - "POST /budgets                -> draft"
    - "PUT  /budgets/{id}           -> draft only; 409 otherwise"
    - "POST /budgets/{id}/confirm   -> draft -> confirmed"
    - method: POST
      path: "/budgets/{id}/revise"
      auth: "accountant | admin"
      precondition: "state == 'confirmed'"
      behaviour: "see §10.7 scenarios — creates a linked copy"
      returns: 201 "the new draft revision"
      errors: [409 BUDGET_NOT_CONFIRMED, 409 ALREADY_REVISED]
    - "POST /budgets/{id}/cancel"
    - method: GET
      path: "/budgets/{id}/lines/{line_id}/source-documents"
      purpose: >
        Mockup: 'Clicking on the Achieved Amount button opens list view of all
        Invoices/Bills having same analytical for the budget period.'
      returns: "list of {document_type, number, date, partner_name, line_total}"

  reports:
    - method: GET
      path: "/reports/balance-sheet"
      params: { year: int, as_of: "date | null" }
      returns:
        assets:      [{ label, account_type, balance }]
        liabilities: [{ label, account_type, balance }]
        total_assets: "decimal string"
        total_liabilities: "decimal string"
        is_balanced: "bool   # total_assets == total_liabilities"
      note: "is_balanced is the live proof of P1. Surface it in the UI."
    - method: GET
      path: "/reports/profit-and-loss"
      params: { year: int }
      returns:
        income: { income_from_sales, total_income }
        expenses: { purchase_expense, other_expense, total_expenses }
        net_income: "decimal string"
    - method: GET
      path: "/reports/trial-balance"
      purpose: "Integrity check: every account's debit and credit totals, plus grand totals."
      returns: { rows: [{account_code, account_name, total_debit, total_credit}],
                 grand_total_debit, grand_total_credit, is_balanced }
      why: >
        Cheap to build, and it is the single most convincing screen you can show a
        judge. Build it even though the mockup does not require it.
    - "GET /reports/budget-summary   -> per-budget achieved vs committed, for the pie chart"

  dashboard:
    - method: GET
      path: "/dashboard"
      returns:
        sales:    { all: int, confirmed: int, draft: int }
        purchase: { all: int, confirmed: int, draft: int }
        budget:   { achieved: int, budget: int, committed: int }
      note: "Single endpoint, single round trip. Mockup: App Dashboard tiles."

  portal:
    - method: GET
      path: "/portal/my-documents"
      auth: "contact role"
      returns: "invoices and bills WHERE partner_id = current_user.partner_id"
      security: >
        The partner filter is applied in the SERVICE query, never from a client
        parameter. See §12.3.
    - "POST /portal/pay/{invoice_id}   -> contact pays own invoice; 403 if not theirs"
```

---

## 10. Behaviour specification (BDD / Gherkin)

> **These scenarios are the definition of correct.** They are not illustrative. Every
> `Then` is a checkable assertion. The agent must not consider a feature done until its
> scenarios pass — by automated test where §10.4 says so, by manual walkthrough otherwise.
>
> **If a behaviour you are about to implement has no scenario here, stop and ask.**

### 10.1 Background (assumed by every scenario)

```gherkin
Background:
  Given the database has been seeded per §14
  And the Chart of Accounts contains:
    | code | name                | group         | type        |
    | 1000 | Bank A/c            | balance_sheet | bank        |
    | 1010 | Cash A/c            | balance_sheet | cash        |
    | 1200 | Debtors A/c         | balance_sheet | asset       |
    | 2000 | Creditors A/c       | balance_sheet | liability   |
    | 3000 | Capital A/c         | balance_sheet | capital     |
    | 4000 | Sales Income A/c    | profit_loss   | income      |
    | 5000 | Purchase Expense A/c| profit_loss   | expense     |
    | 5100 | Other Expense A/c   | profit_loss   | other_expense |
  And the Journals contain:
    | name     | type     | default account      |
    | Sales    | sales    | Sales Income A/c     |
    | Purchase | purchase | Purchase Expense A/c |
    | Bank     | bank     | Bank A/c             |
    | Cash     | cash     | Cash A/c             |
  And a partner "Mr Rahul" exists with type "both"
  And a product "Table" exists with sales price 2000.00 and cost 1500.00
  And an analytic account "Project 1" exists
```

### 10.2 Authentication

```gherkin
Feature: Account creation and login

  Scenario: Successful self-signup
    Given no user exists with login id "rahul_ac"
    When I POST /auth/signup with login id "rahul_ac", a unique email,
         and password "Str0ng@Pass"
    Then the response status is 201
    And a user is created with role "accountant"
    And the response body does NOT contain any password field
    And the stored password_hash starts with "$2b$"

  Scenario Outline: Login id length is enforced
    When I POST /auth/signup with login id "<login_id>"
    Then the response status is <status>
    And when rejected the error field is "login_id"
    Examples:
      | login_id      | status | note              |
      | abc           | 422    | 3 chars, too short|
      | abcdef        | 201    | 6 chars, minimum  |
      | abcdefghijkl  | 201    | 12 chars, maximum |
      | abcdefghijklm | 422    | 13 chars, too long|

  Scenario Outline: Password complexity is enforced
    When I POST /auth/signup with password "<password>"
    Then the response status is <status>
    Examples:
      | password      | status | reason               |
      | Short1@       | 422    | only 7 characters    |
      | alllower1@    | 422    | no uppercase         |
      | ALLUPPER1@    | 422    | no lowercase         |
      | NoSpecial123  | 422    | no special character |
      | Str0ng@Pass   | 201    | satisfies all rules  |

  Scenario: Passwords must match
    When I POST /auth/signup with password "Str0ng@Pass" and
         confirm_password "Str0ng@Pas"
    Then the response status is 422
    And the error message names the confirm_password field

  Scenario: Duplicate login id is rejected
    Given a user exists with login id "rahul_ac"
    When I POST /auth/signup with login id "rahul_ac"
    Then the response status is 409
    And the error code is "LOGIN_ID_TAKEN"

  Scenario: Duplicate email is rejected
    Given a user exists with email "rahul@example.com"
    When I POST /auth/signup with email "rahul@example.com"
    Then the response status is 409
    And the error code is "EMAIL_TAKEN"

  Scenario: Successful login returns a token
    Given a user exists with login id "rahul_ac" and password "Str0ng@Pass"
    When I POST /auth/login with those credentials
    Then the response status is 200
    And the body contains a JWT access_token
    And the token payload contains the user id and role
    And the body contains the user's role and partner_id

  Scenario Outline: Failed login is indistinguishable
    When I POST /auth/login with login id "<login_id>" and password "<password>"
    Then the response status is 401
    And the message is exactly "Invalid Login Id or Password"
    Examples:
      | login_id     | password      | actual_problem      |
      | nonexistent  | Str0ng@Pass   | user does not exist |
      | rahul_ac     | WrongPass1@   | wrong password      |
    # The identical message is deliberate: differing messages let an attacker
    # enumerate which accounts exist.

  Scenario: An inactive user cannot log in
    Given the user "rahul_ac" has is_active = false
    When I log in with correct credentials
    Then the response status is 401

  Scenario: Admin creating a portal user must supply a partner
    Given I am authenticated as an admin
    When I POST /auth/users with role "contact" and no partner_id
    Then the response status is 422
    And the error code is "CONTACT_REQUIRES_PARTNER"

  Scenario: A non-admin cannot create users
    Given I am authenticated as an accountant
    When I POST /auth/users
    Then the response status is 403
```

### 10.3 Master data

```gherkin
Feature: Contacts, products and analytic accounts

  Scenario: Creating a contact with valid data
    Given I am authenticated as an accountant
    When I POST /partners with name "Open Wood", a unique email and a phone
    Then the response status is 201
    And GET /partners returns the new contact in items

  Scenario: Contact email must be unique when supplied
    Given a partner exists with email "openwood21@example.com"
    When I POST /partners with the same email
    Then the response status is 409
    And the error code is "EMAIL_TAKEN"

  Scenario: Contact email may be omitted
    When I POST /partners with a name and no email
    Then the response status is 201

  Scenario: Contact name is required
    When I POST /partners with an empty name
    Then the response status is 422

  Scenario: List view defaults and view switching
    Given 25 partners exist
    When I GET /partners
    Then 20 items are returned with total = 25 and page = 1
    And the same data serves both the List and Kanban views
    # The mockup requires List and Kanban for Contact, Product and Analytics.
    # This is a FRONTEND toggle over one API response — not two endpoints.

  Scenario: Search filters the list
    Given partners "Open Wood" and "Joey Wills" exist
    When I GET /partners?search=wood
    Then exactly one item is returned, named "Open Wood"

  Scenario: Creating a product with a new category on the fly
    Given no category named "Furniture" exists
    When I POST /product-categories with name "Furniture"
    And I POST /products with that category_id, name "Table",
        sales_price "2000.00" and cost_price "1500.00"
    Then both are created
    And the product list shows "Table" with category "Furniture"

  Scenario: Negative prices are rejected
    When I POST /products with sales_price "-100.00"
    Then the response status is 422

  Scenario: An account's group and type must be consistent
    When I POST /accounts with group "balance_sheet" and type "income"
    Then the response status is 422
    And the error code is "ACCOUNT_GROUP_TYPE_MISMATCH"
    # An Income account filed under the Balance Sheet would silently corrupt
    # both financial reports.

  Scenario: An account in use cannot be deleted
    Given "Sales Income A/c" is referenced by a posted journal entry line
    When I DELETE /accounts/{id}
    Then the response status is 409
    And the error code is "ACCOUNT_IN_USE"
    And the response suggests archiving instead
```

### 10.4 ★ The posting engine — highest-value scenarios

> These MUST have automated tests in `tests/test_posting_engine.py`.
> They are the core of the Logic criterion.

```gherkin
Feature: Journal entry posting

  Scenario: A balanced two-line entry posts successfully
    Given I am authenticated as an accountant
    When I POST /journal-entries with journal "Bank" and lines:
      | account     | partner   | debit    | credit   |
      | Debtors A/c | Mr Rahul  | 10000.00 | 0.00     |
      | Bank A/c    |           | 0.00     | 10000.00 |
    Then the response status is 201
    And the entry state is "posted"
    And the entry has a unique number
    And the entry total_amount is "10000.00"
    And GET /reports/trial-balance reports is_balanced = true

  Scenario: An unbalanced entry is rejected entirely
    When I POST /journal-entries with lines:
      | account     | debit    | credit  |
      | Debtors A/c | 10000.00 | 0.00    |
      | Bank A/c    | 0.00     | 9000.00 |
    Then the response status is 422
    And the error code is "UNBALANCED_ENTRY"
    And the error payload contains total_debit "10000.00",
        total_credit "9000.00" and difference "1000.00"
    And NO journal entry row was created
    And NO journal entry line row was created
    # "Entirely" is the point. A partial write here is the worst possible
    # outcome — corrupt data that no report would reveal.

  Scenario: A balanced entry with more than two lines posts
    When I POST a journal entry with lines:
      | account              | debit   | credit  |
      | Purchase Expense A/c | 6000.00 | 0.00    |
      | Other Expense A/c    | 1000.00 | 0.00    |
      | Creditors A/c        | 0.00    | 7000.00 |
    Then the response status is 201
    And the entry has 3 lines

  Scenario: A line cannot carry both a debit and a credit
    When I POST a journal entry containing a line with debit "500.00"
         and credit "500.00"
    Then the response status is 422
    And the error code is "INVALID_LINE"
    And the error payload names the 0-based index of the offending line

  Scenario: A line cannot be zero on both sides
    When I POST a journal entry containing a line with debit "0.00"
         and credit "0.00"
    Then the response status is 422
    And the error code is "INVALID_LINE"

  Scenario: Negative amounts are rejected
    When I POST a journal entry containing a line with debit "-500.00"
    Then the response status is 422

  Scenario: A single-line entry is rejected
    When I POST a journal entry with exactly one line
    Then the response status is 422
    And the error code is "UNBALANCED_ENTRY"

  Scenario: An entry with no lines is rejected
    When I POST a journal entry with an empty lines array
    Then the response status is 422

  Scenario: Posting to an archived account is rejected
    Given "Other Expense A/c" is archived
    When I POST a balanced entry using that account
    Then the response status is 422
    And the error code is "ACCOUNT_ARCHIVED"

  Scenario: Decimal precision survives a round trip
    When I POST a balanced entry with debit "199.99" and credit "199.99"
    Then the stored debit reads back as exactly "199.99"
    And no value anywhere in the response matches /\.\d{3,}/
    # Guards against float contamination. 199.99 * 3 = 599.9699999999999
    # in IEEE-754; a single float() in the path will surface here.

  Scenario: Many small lines still sum exactly
    When I POST an entry with 10 debit lines of "199.99"
         and one credit line of "1999.90"
    Then the response status is 201
    # Decimal sums exactly. Floats would drift and this would 422.

  Scenario: A posted entry cannot be deleted
    Given a posted journal entry exists
    When I DELETE /journal-entries/{id}
    Then the response status is 405

  Scenario: A posted entry cannot be edited
    Given a posted journal entry exists
    When I attempt to modify any of its lines
    Then the request is rejected
    # No PUT route exists for journal entries. Immutability by absence of API.
```

### 10.5 Purchase cycle

```gherkin
Feature: Purchase Order to Vendor Bill to Payment

  Scenario: Creating and confirming a purchase order
    Given I am authenticated as an accountant
    When I POST /purchase-orders for vendor "Mr Rahul" with one line:
         product "Table", analytic "Project 1", quantity 3, unit price "2000.00"
    Then the response status is 201
    And the PO number matches the pattern "P#####"
    And the line_total is "6000.00" computed by the SERVER
    And the PO total_amount is "6000.00"
    And the PO state is "draft"
    When I POST /purchase-orders/{id}/confirm
    Then the state is "confirmed"
    And NO journal entry was created
    # A purchase order is a commitment, not a financial event. Nothing has
    # been bought yet, so nothing hits the ledger.

  Scenario: The server ignores a client-supplied line total
    When I POST a purchase order line with quantity 3, unit price "2000.00"
         and line_total "1.00"
    Then the stored line_total is "6000.00"
    # Never trust client arithmetic on money.

  Scenario: PO numbering increments
    Given the last purchase order is "P00007"
    When I create a new purchase order
    Then its number is "P00008"

  Scenario: Creating a bill from a confirmed PO copies everything
    Given a confirmed purchase order "P00001" for "Mr Rahul" with one line
          product "Table", analytic "Project 1", quantity 3, price "2000.00"
    When I POST /purchase-orders/P00001/create-bill
    Then a vendor bill is created in state "draft"
    And its vendor is "Mr Rahul"
    And it has one line with product "Table", quantity 3, price "2000.00"
    And that line's analytic is "Project 1"
    And that line's account defaults to "Purchase Expense A/c"
    And the bill's source_po_id points to P00001
    And the bill number matches "BILL/YYYY/####"

  Scenario: A bill created from a PO shows the PO link
    Given a bill created from purchase order "P00001"
    When I GET that bill
    Then source_po_id is not null
    And the UI renders the "PO" button
    # The mockup hides this button on bills created fresh.

  Scenario: A bill created directly hides the PO link
    When I POST /vendor-bills directly with no source PO
    Then source_po_id is null
    And the UI does not render the "PO" button

  Scenario: A draft PO cannot be billed
    Given a purchase order in state "draft"
    When I POST /purchase-orders/{id}/create-bill
    Then the response status is 409
    And the error code is "PO_NOT_CONFIRMED"

  Scenario: ★ Confirming a vendor bill posts a balanced journal entry
    Given a draft vendor bill for "Mr Rahul" totalling "6000.00"
          with one line on "Purchase Expense A/c"
    When I POST /vendor-bills/{id}/confirm
    Then the response status is 200
    And the bill state is "confirmed"
    And a journal entry exists in the "Purchase" journal with lines:
      | account              | partner  | debit   | credit  |
      | Purchase Expense A/c | Mr Rahul | 6000.00 | 0.00    |
      | Creditors A/c        | Mr Rahul | 0.00    | 6000.00 |
    And that entry's state is "posted"
    And that entry's number equals the bill number
    And the bill's journal_entry_id points to it
    And the bill's payment_status is "not_paid"
    And amount_due is "6000.00"

  Scenario: Bill lines on different accounts produce grouped debit lines
    Given a draft bill with two lines:
      | product | account              | line_total |
      | Table   | Purchase Expense A/c | 6000.00    |
      | Freight | Other Expense A/c    | 1000.00    |
    When I confirm the bill
    Then the journal entry has 3 lines:
      | account              | debit   | credit  |
      | Purchase Expense A/c | 6000.00 | 0.00    |
      | Other Expense A/c    | 1000.00 | 0.00    |
      | Creditors A/c        | 0.00    | 7000.00 |

  Scenario: Two bill lines on the SAME account are merged
    Given a draft bill with two lines both on "Purchase Expense A/c",
          "4000.00" and "2000.00"
    When I confirm the bill
    Then the journal entry has exactly 2 lines
    And the Purchase Expense debit line is "6000.00"
    # Group by account, then sum. Do not emit one ledger line per document line.

  Scenario: A bill with no lines cannot be confirmed
    Given a draft vendor bill with zero lines
    When I POST /vendor-bills/{id}/confirm
    Then the response status is 422
    And the error code is "NO_LINES"
    And the bill remains in state "draft"

  Scenario: Confirming twice is rejected
    Given a confirmed vendor bill
    When I POST /vendor-bills/{id}/confirm again
    Then the response status is 409
    And the error code is "ALREADY_CONFIRMED"
    And no second journal entry is created

  Scenario: ★ Atomicity — a failed post leaves nothing behind
    Given a draft vendor bill whose confirmation would raise inside the posting engine
    When I POST /vendor-bills/{id}/confirm
    Then the response status is 5xx or 422
    And the bill is STILL in state "draft"
    And no journal entry exists for it
    And no journal entry lines exist for it
    # One transaction. Both sides commit or neither does. This is P3, and it is
    # the single most important non-happy-path behaviour in the system.
```

### 10.6 Sales cycle and payments

```gherkin
Feature: Sales Order to Invoice to Payment

  Scenario: ★ Confirming a customer invoice posts a balanced journal entry
    Given a draft customer invoice for "Mr Rahul" with two lines
          totalling "10000.00", both on "Sales Income A/c"
    When I POST /customer-invoices/{id}/confirm
    Then the invoice state is "confirmed"
    And a journal entry exists in the "Sales" journal with lines:
      | account          | partner  | debit    | credit   |
      | Debtors A/c      | Mr Rahul | 10000.00 | 0.00     |
      | Sales Income A/c | Mr Rahul | 0.00     | 10000.00 |
    And it appears in the Journal Entries list with state "posted"
    And the invoice payment_status is "not_paid"

  Scenario: An invoice mixing income accounts produces grouped credit lines
    Given a draft invoice with lines on "Sales Income A/c" ("6000.00")
          and a second income account ("4000.00")
    When I confirm the invoice
    Then the journal entry has one debit line to Debtors of "10000.00"
    And two credit lines of "6000.00" and "4000.00"
    And total debits equal total credits

  Scenario: Partial payment moves status to partial
    Given a confirmed invoice "INV/2026/0001" totalling "10000.00"
    When I POST /payments with type "receive", amount "4000.00",
         journal "Bank", invoice_id INV/2026/0001
    And I POST /payments/{id}/confirm
    Then a journal entry is posted with lines:
      | account     | partner  | debit   | credit  |
      | Bank A/c    |          | 4000.00 | 0.00    |
      | Debtors A/c | Mr Rahul | 0.00    | 4000.00 |
    And the invoice amount_paid is "4000.00"
    And amount_due is "6000.00"
    And payment_status is "partial"

  Scenario: Settling the remainder moves status to paid
    Given invoice "INV/2026/0001" totalling "10000.00" with "4000.00" already paid
    When I register and confirm a further payment of "6000.00"
    Then amount_due is "0.00"
    And payment_status is "paid"
    And the net Debtors balance for "Mr Rahul" is "0.00"
    # Debtors was debited 10000 by the invoice and credited 4000 + 6000 by the
    # payments. The customer correctly disappears from the Balance Sheet.

  Scenario Outline: Payment status is derived, never stored
    Given a confirmed invoice totalling "10000.00"
    When confirmed payments totalling "<paid>" exist against it
    Then payment_status is "<status>"
    Examples:
      | paid     | status   |
      | 0.00     | not_paid |
      | 0.01     | partial  |
      | 9999.99  | partial  |
      | 10000.00 | paid     |

  Scenario: Overpayment is rejected
    Given a confirmed invoice totalling "10000.00" with "6000.00" already paid
    When I POST /payments with amount "5000.00" against it
    Then the response status is 422
    And the error code is "OVERPAYMENT"
    And the error states the remaining due is "4000.00"

  Scenario: A draft document cannot be paid
    Given a customer invoice in state "draft"
    When I POST /payments against it
    Then the response status is 422
    And the error code is "DOCUMENT_NOT_CONFIRMED"

  Scenario: A draft payment has no ledger effect
    Given a payment created but not confirmed
    Then no journal entry exists for it
    And the target invoice's amount_due is unchanged
    And the payment does not appear in the trial balance

  Scenario: Payment direction must match the document
    When I POST /payments with type "send" and an invoice_id
    Then the response status is 422
    And the error code is "PAYMENT_DIRECTION_MISMATCH"

  Scenario: Payments must use a bank or cash journal
    When I POST /payments with the "Sales" journal
    Then the response status is 422
    And the error code is "INVALID_PAYMENT_JOURNAL"

  Scenario: A confirmed payment cannot be cancelled
    Given a confirmed payment
    When I POST /payments/{id}/cancel
    Then the response status is 409
    # Its journal entry is posted and immutable (P4). Reversal is the P2 path.
```

### 10.7 Budgets

```gherkin
Feature: Budget lifecycle and achievement tracking

  Scenario: Creating a draft budget
    When I POST /budgets named "January 2026", period 2026-01-01 to 2026-01-31,
         responsible "Mr Rahul", with one line: analytic "Project 1",
         type "expense", committed "200000.00"
    Then the response status is 201
    And the state is "draft"
    And achieved_amount is null on every line
    # Achievement is meaningless until the budget is committed to.

  Scenario: End date cannot precede start date
    When I POST a budget with start 2026-01-31 and end 2026-01-01
    Then the response status is 422

  Scenario: The same analytic cannot appear twice with the same type
    When I POST a budget with two lines both for analytic "Project 1"
         with type "expense"
    Then the response status is 422
    And the error code is "DUPLICATE_BUDGET_LINE"
    # Two lines for one analytic would double-count achievement.

  Scenario: Confirming a budget reveals achievement figures
    Given a draft budget "January 2026" with an expense line for "Project 1"
          committed "200000.00"
    When I POST /budgets/{id}/confirm
    Then the state is "confirmed"
    And achieved_amount, achieved_percent and amount_to_achieve are returned

  Scenario: ★ Expense achievement sums vendor bill lines in the period
    Given a confirmed budget for 2026-01-01 to 2026-01-31 with an expense line
          for analytic "Project 1" committed "200000.00"
    And a confirmed vendor bill dated 2026-01-15 with a line
        for "Project 1" of "10000.00"
    When I GET that budget
    Then the line's achieved_amount is "10000.00"
    And achieved_percent is "5.00"
    And amount_to_achieve is "190000.00"

  Scenario: ★ Income achievement sums customer invoice lines in the period
    Given a confirmed budget with an income line for "Project 1"
          committed "500000.00"
    And a confirmed customer invoice dated inside the period with a line
        for "Project 1" of "21000.00"
    Then achieved_amount is "21000.00"
    And achieved_percent is "4.20"

  Scenario: Documents outside the budget period are excluded
    Given a confirmed budget for January 2026
    And a confirmed vendor bill dated 2026-02-05 tagged "Project 1"
    Then that bill contributes "0.00" to the January budget

  Scenario: Draft documents are excluded from achievement
    Given a confirmed budget for January 2026
    And a DRAFT vendor bill dated 2026-01-15 tagged "Project 1" for "50000.00"
    Then achieved_amount is "0.00"
    # Only confirmed documents count. A draft is not yet a commitment.

  Scenario: Income lines ignore bills, expense lines ignore invoices
    Given a confirmed budget with an income line for "Project 1"
    And a confirmed vendor bill in the period tagged "Project 1"
    Then the income line's achieved_amount is "0.00"
    # Per the mockup: invoice lines map to Income, bill lines map to Expense.

  Scenario: Untagged document lines contribute nothing
    Given a confirmed invoice whose line has no analytic account
    Then it contributes to no budget

  Scenario: Achievement may exceed 100 percent
    Given a confirmed budget line committed "10000.00"
    And confirmed bills tagged with that analytic totalling "12000.00"
    Then achieved_amount is "12000.00"
    And achieved_percent is "120.00"
    And amount_to_achieve is "-2000.00"
    # Over-budget is a real state and must be representable, not clamped.
    # The UI shows the negative figure in a warning colour.

  Scenario: Division by zero is impossible
    Given a budget line with committed_amount "0.00"
    Then achieved_percent is "0.00" and no error occurs
    # Guarded even though a CHECK constraint forbids committed_amount = 0.

  Scenario: ★ Revising a confirmed budget creates a linked copy
    Given a confirmed budget "January 2026" with one line committed "200000.00"
    When I POST /budgets/{id}/revise
    Then a new budget is created named "January 2026 Revised"
    And the new budget is in state "draft"
    And it has the same period, responsible and lines as the original
    And new_budget.revision_of_id points to the original
    And the original's state becomes "revised"
    And original.revised_with_id points to the new budget
    And both budgets remain visible in the list
    # The mockup requires navigation in BOTH directions: the original links
    # forward to its revision, the revision links back to the original.

  Scenario: Only a confirmed budget can be revised
    Given a budget in state "draft"
    When I POST /budgets/{id}/revise
    Then the response status is 409
    And the error code is "BUDGET_NOT_CONFIRMED"

  Scenario: A budget can be revised only once
    Given a budget already in state "revised"
    When I POST /budgets/{id}/revise
    Then the response status is 409
    And the error code is "ALREADY_REVISED"

  Scenario: Drilling into an achieved amount lists its source documents
    Given a confirmed budget line with achieved_amount "10000.00"
          arising from two confirmed bills
    When I GET /budgets/{id}/lines/{line_id}/source-documents
    Then both bills are listed with number, date, partner and contributing amount
    And the listed amounts sum to "10000.00"

  Scenario: A confirmed budget cannot be edited
    Given a confirmed budget
    When I PUT /budgets/{id}
    Then the response status is 409
    And the error suggests revising instead
```

### 10.8 Budget warnings on documents

```gherkin
Feature: Non-blocking over-budget warning

  # The mockup shows a warning on PO and Bill confirmation:
  #   "Exceeds Approved Budget — the entered amount is higher than the remaining
  #    budget amount for this budget line. Consider adjusting the value or revise
  #    the budget."
  # It is explicitly NON-BLOCKING.

  Scenario: Confirming over budget warns but succeeds
    Given a confirmed budget for January 2026 with an expense line for
          "Project 1" committed "10000.00"
    And confirmed bills tagged "Project 1" already totalling "8000.00"
    When I confirm a new bill dated in January with a "Project 1" line of "5000.00"
    Then the response status is 200
    And the bill IS confirmed
    And a journal entry IS posted
    And the response contains a warnings array with code "EXCEEDS_BUDGET"
    And that warning names the analytic and the remaining amount "2000.00"
    # Non-blocking is deliberate. The business may legitimately overspend;
    # the system informs, it does not obstruct.

  Scenario: Confirming within budget produces no warning
    Given remaining budget of "10000.00" for "Project 1"
    When I confirm a bill with a "Project 1" line of "5000.00"
    Then the warnings array is empty

  Scenario: Untagged lines never warn
    When I confirm a bill whose lines carry no analytic
    Then the warnings array is empty

  Scenario: Warnings never block the ledger
    Given any over-budget condition
    Then the journal entry is always posted
    # A warning must never leave the document confirmed but unposted.
```

### 10.9 Reports

```gherkin
Feature: Financial reports derived from the ledger

  Scenario: ★ The Balance Sheet balances after a full business cycle
    Given the ledger is empty
    And an opening entry: debit Bank A/c "100000.00", credit Capital A/c "100000.00"
    When I confirm a vendor bill of "6000.00" (Purchase Expense / Creditors)
    And I confirm a customer invoice of "10000.00" (Debtors / Sales Income)
    And I confirm a payment of "6000.00" to the vendor via Bank
    And I confirm a receipt of "10000.00" from the customer via Bank
    Then GET /reports/balance-sheet returns:
      | side        | label     | balance   |
      | assets      | Bank      | 104000.00 |
      | assets      | Cash      | 0.00      |
      | assets      | Debtors   | 0.00      |
      | liabilities | Capital   | 100000.00 |
      | liabilities | Creditors | 0.00      |
    And total_assets is "104000.00"
    And total_liabilities is "100000.00"
    And is_balanced is false
    # NOTE: assets exceed liabilities by exactly the period's net income
    # (10000 income - 6000 expense = 4000). This is CORRECT and expected:
    # a Balance Sheet only balances once retained earnings are carried in.
    # See the following scenario.

  Scenario: Balance Sheet identity including retained earnings
    Given the state of the previous scenario
    When I GET /reports/profit-and-loss for the same period
    Then net_income is "4000.00"
    And total_assets equals total_liabilities plus net_income
    And the Balance Sheet displays "Current Period Earnings" of "4000.00"
        as a Capital-side row
    And with that row included, is_balanced is true
    # IMPLEMENTATION REQUIREMENT: the balance-sheet endpoint MUST include a
    # computed "Current Period Earnings" row on the liabilities/capital side,
    # equal to P&L net income. Without it the report will never balance and
    # the demo's strongest moment is lost. This is the one piece of accounting
    # the mockup does not spell out, and the one most teams get wrong.

  Scenario: Profit and Loss computation
    Given confirmed invoices totalling "10000.00" to Sales Income
    And confirmed bills totalling "6000.00" to Purchase Expense
    And a manual entry of "1000.00" to Other Expense
    When I GET /reports/profit-and-loss
    Then income_from_sales is "10000.00"
    And total_income is "10000.00"
    And purchase_expense is "6000.00"
    And other_expense is "1000.00"
    And total_expenses is "7000.00"
    And net_income is "3000.00"

  Scenario: Draft documents never appear in reports
    Given a DRAFT customer invoice of "50000.00"
    When I GET /reports/profit-and-loss
    Then income_from_sales is "0.00"
    # Reports read only posted journal entries. Drafts have none.

  Scenario: Payments do not affect Profit and Loss
    Given a confirmed invoice of "10000.00"
    When I record and confirm a receipt of "10000.00"
    Then total_income remains "10000.00"
    And net_income is unchanged
    # A payment moves an asset (Debtors -> Bank). Income was already
    # recognised at invoice time. If P&L changes on payment, the posting
    # rules are wrong.

  Scenario: ★ The trial balance always balances
    Given any sequence of confirmed documents and payments
    When I GET /reports/trial-balance
    Then grand_total_debit equals grand_total_credit
    And is_balanced is true
    # This is the system-wide integrity check and the most convincing
    # 10 seconds of the demo. It can only fail if P1 or P6 was violated.

  Scenario: An empty ledger produces zeroed reports, not errors
    Given no journal entries exist
    When I GET each report
    Then the response status is 200
    And every figure is "0.00"
    And is_balanced is true

  Scenario: Reports are year-scoped
    Given confirmed invoices in 2025 and in 2026
    When I GET /reports/profit-and-loss?year=2026
    Then only 2026 amounts are included
```

### 10.10 Authorisation and portal access

```gherkin
Feature: Role-based access control

  Scenario Outline: Route access by role
    Given I am authenticated as "<role>"
    When I <method> <path>
    Then the response status is <status>
    Examples:
      | role       | method | path                    | status |
      | admin      | GET    | /auth/users             | 200    |
      | accountant | GET    | /auth/users             | 403    |
      | contact    | GET    | /auth/users             | 403    |
      | admin      | POST   | /partners               | 201    |
      | accountant | POST   | /partners               | 201    |
      | contact    | POST   | /partners               | 403    |
      | accountant | POST   | /journal-entries        | 201    |
      | contact    | POST   | /journal-entries        | 403    |
      | accountant | GET    | /reports/balance-sheet  | 200    |
      | contact    | GET    | /reports/balance-sheet  | 403    |
      | contact    | GET    | /portal/my-documents    | 200    |

  Scenario: No token is rejected
    When I GET /partners with no Authorization header
    Then the response status is 401

  Scenario: An expired token is rejected
    Given a JWT whose exp is in the past
    When I GET /partners with it
    Then the response status is 401
    And the error code is "TOKEN_EXPIRED"

  Scenario: A tampered token is rejected
    Given a JWT whose payload role was edited to "admin"
    When I GET /auth/users with it
    Then the response status is 401
    # The signature no longer verifies. Never trust an unverified claim.

  Scenario: ★ A portal user sees only their own documents
    Given partner "Mr Rahul" with a contact user, and partner "Joey Wills"
    And confirmed invoices exist for both
    When Mr Rahul's user GETs /portal/my-documents
    Then only Mr Rahul's invoices are returned
    And Joey Wills' invoices do not appear in any form

  Scenario: ★ A portal user cannot read another partner's invoice by id
    Given an invoice belonging to "Joey Wills" with id 42
    When Mr Rahul's user GETs /customer-invoices/42
    Then the response status is 403
    And the response body contains no data about that invoice
    # Ownership is checked server-side on every single-resource read.
    # Guessing an id must reveal nothing, including via the error message.

  Scenario: ★ The partner filter cannot be overridden by a parameter
    When Mr Rahul's user GETs /portal/my-documents?partner_id=99
    Then the parameter is ignored entirely
    And only Mr Rahul's documents are returned
    # The filter derives from the JWT, never from client input. Accepting a
    # client-supplied partner_id here would be a complete authorisation bypass.

  Scenario: A portal user may pay their own invoice
    Given a confirmed invoice belonging to Mr Rahul with amount due "6000.00"
    When Mr Rahul's user POSTs /portal/pay/{invoice_id} with "6000.00"
    Then the payment is created and confirmed
    And the invoice payment_status becomes "paid"

  Scenario: A portal user cannot pay someone else's invoice
    When Mr Rahul's user POSTs /portal/pay/{joey_invoice_id}
    Then the response status is 403
    And no payment is created
```

### 10.11 Cross-cutting edge cases

```gherkin
Feature: Robustness

  Scenario: Concurrent document numbering does not collide
    When two purchase orders are created simultaneously
    Then both succeed with distinct numbers
    And neither number is reused
    # See §12.4 — numbering uses a row lock, not SELECT MAX() + 1.

  Scenario: Deleting a partner referenced by a posted entry is refused
    Given "Mr Rahul" appears on a posted journal entry line
    When I DELETE /partners/{id}
    Then the response status is 409
    And the error code is "PARTNER_IN_USE"
    And the response explains that archiving is available instead

  Scenario: Every list endpoint is bounded
    Given 10000 partners exist
    When I GET /partners with no page_size
    Then at most 20 items are returned
    And total reports 10000
    # No endpoint may return an unbounded array. This is the Performance criterion.

  Scenario: An oversized page_size is clamped
    When I GET /partners?page_size=5000
    Then at most 100 items are returned

  Scenario: A page beyond the end returns empty, not an error
    When I GET /partners?page=9999
    Then the response status is 200 and items is empty

  Scenario: Malformed JSON is rejected cleanly
    When I POST invalid JSON to any endpoint
    Then the response status is 422
    And the response is the standard error envelope, not a stack trace

  Scenario: A non-existent id returns 404, not 500
    When I GET /customer-invoices/999999
    Then the response status is 404
    And the error code is "NOT_FOUND"

  Scenario: An unexpected server error never leaks internals
    Given an unhandled exception occurs
    Then the response status is 500
    And the body contains a generic message and a correlation id
    And it contains no stack trace, SQL, file path, or table name
```

---

## 11. Validation rules

```yaml
validation:
  principle: >
    Every rule below is enforced on the SERVER. The frontend mirrors them with Zod
    for immediate feedback, but the server never trusts the client (P7).
  layers:
    - "Pydantic: type, format, range, cross-field — returns 422"
    - "Service: business rules needing DB context — returns 409 or 422"
    - "Database: CHECK/UNIQUE/FK — last line of defence, should never be user-visible"

  auth:
    login_id:
      rules:
        [
          "required",
          "6-12 characters",
          "unique",
          "alphanumeric plus underscore",
        ]
      regex: "^[A-Za-z0-9_]{6,12}$"
    email:
      rules: ["required", "valid format (Pydantic EmailStr)", "unique"]
    password:
      rules:
        - "minimum 9 characters"
        - "at least one lowercase letter"
        - "at least one uppercase letter"
        - "at least one special character"
      regex: "^(?=.*[a-z])(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{9,}$"
      mockup_wording: >
        "must have more than 8 characters" — read strictly as >8, i.e. minimum 9.
        The regex above encodes that. Show the rule text next to the field so the
        user is never guessing.
      never: "Never log, echo, or return a password. Not in errors, not in debug output."
    confirm_password:
      rule: "must equal password"
      implementation: "Pydantic model_validator(mode='after')"

  money_fields:
    type: "Decimal via condecimal(max_digits=14, decimal_places=2)"
    rules:
      - "amounts on documents and payments must be > 0"
      - "debit and credit on ledger lines must be >= 0"
      - "reject more than 2 decimal places rather than silently rounding"
    why_reject_not_round: >
      Silently rounding 100.005 to 100.01 hides a client bug. Rejecting surfaces it.

  quantity:
    rules: ["> 0", "at most 2 decimal places"]

  dates:
    rules:
      - "ISO-8601 YYYY-MM-DD"
      - "due_date >= bill_date / invoice_date when supplied"
      - "budget end_date >= start_date"
    future_dates: "Allowed. Post-dated invoices are legitimate."

  documents:
    - "at least one line required to confirm (422 NO_LINES)"
    - "every line requires product_id, quantity, unit_price"
    - "bill and invoice lines additionally require account_id"
    - "line_total is ALWAYS computed server-side and any client value discarded"
    - "totals recomputed server-side on every write"

  referential:
    - "every foreign key verified to exist before write"
    - "archived accounts cannot be used on new entries"
    - "inactive partners cannot be used on new documents"
```

---

## 12. Error handling and security

### 12.1 Error envelope

```yaml
error_response:
  shape:
    error:
      code: "SCREAMING_SNAKE_CASE"
      message: "human-readable, safe to display verbatim in a toast"
      details: "object | null — field errors or structured context"
      correlation_id: "uuid4, also written to the server log"
  rule: >
    EVERY error response from EVERY endpoint uses this shape. Register FastAPI
    exception handlers for AppError, RequestValidationError, HTTPException and
    Exception so no route can return a differently-shaped body.

  worked_example_unbalanced:
    status: 422
    body:
      error:
        code: "UNBALANCED_ENTRY"
        message: "Debit and credit amounts do not match."
        details:
          total_debit: "10000.00"
          total_credit: "9000.00"
          difference: "1000.00"
        correlation_id: "8f3a...".
    ui_treatment: >
      The Journal Entry form shows this as a blocking inline banner beneath the
      lines table, exactly as the mockup specifies, with running Debit and Credit
      totals in the table footer so the user can see the gap.

  status_codes:
    200: "successful read or state transition"
    201: "resource created"
    400: "malformed request"
    401: "missing, expired or invalid token"
    403: "authenticated but not permitted, including ownership failures"
    404: "resource does not exist"
    405: "method not allowed — e.g. DELETE on a posted journal entry"
    409: "state conflict — already confirmed, in use, wrong state for this action"
    422: "validation failed"
    500: "unexpected — generic message only"

  error_codes:
    auth: [LOGIN_ID_TAKEN, EMAIL_TAKEN, INVALID_CREDENTIALS, TOKEN_EXPIRED,
           TOKEN_INVALID, INSUFFICIENT_ROLE, CONTACT_REQUIRES_PARTNER]
    ledger: [UNBALANCED_ENTRY, INVALID_LINE, ACCOUNT_NOT_FOUND, ACCOUNT_ARCHIVED,
             ACCOUNT_GROUP_TYPE_MISMATCH, JOURNAL_NOT_FOUND, ENTRY_IMMUTABLE]
    documents: [NO_LINES, ALREADY_CONFIRMED, DOCUMENT_NOT_CONFIRMED,
                PO_NOT_CONFIRMED, BILL_ALREADY_EXISTS, INVALID_STATE_TRANSITION]
    payments: [OVERPAYMENT, INVALID_PAYMENT_JOURNAL, PAYMENT_DIRECTION_MISMATCH]
    budgets: [BUDGET_NOT_CONFIRMED, ALREADY_REVISED, DUPLICATE_BUDGET_LINE]
    general: [NOT_FOUND, IN_USE, PARTNER_IN_USE, ACCOUNT_IN_USE, VALIDATION_ERROR]

  warnings:
    shape: "{ warnings: [{ code, message, details }] }"
    note: >
      Warnings ride along in SUCCESS responses. EXCEEDS_BUDGET is a warning,
      never an error — the operation completed (§10.8).
```

### 12.2 Security requirements

```yaml
security:
  passwords:
    algorithm: "bcrypt, cost factor 12"
    library: "bcrypt 4.2.1 directly — NOT passlib (known incompatibility with bcrypt 4.x)"
    storage: "hash only; the plaintext never leaves the request handler"

  tokens:
    type: "JWT HS256"
    claims:
      {
        sub: "user id",
        role: "user_role",
        partner_id: "int|null",
        exp: "8 hours",
      }
    verification: "signature verified on EVERY request via a FastAPI dependency"
    rule: >
      Never read role or partner_id from a request body, query string, or header
      other than the verified token.

  authorisation:
    implementation: "require_role('admin') dependency injected per route"
    rule: >
      Authorisation is enforced in the ROUTE DEPENDENCY, never by hiding a button.
      A hidden button is a UX affordance, not a security control. Every route
      states its own required role — no route inherits permission implicitly.

  ownership_checks:
    rule: >
      For any single-resource read or write by a contact-role user, the service
      must verify resource.partner_id == token.partner_id BEFORE returning data.
      Failure returns 403 with no resource details.
    tampering_demo: >
      Rehearse this: log in as a portal user, change the invoice id in the URL to
      another partner's invoice, show the 403. It is a 15-second demonstration
      that maps directly to the Security criterion.

  sql_injection:
    mitigation: "SQLAlchemy parameterised queries exclusively. No f-string SQL, ever."

  mass_assignment:
    mitigation: >
      Request Pydantic models list only client-settable fields. state, totals,
      journal_entry_id, number and any *_id link are NEVER accepted from the client.

  response_leakage:
    rule: "password_hash appears in no response model. Verify by reading /docs."

  cors:
    allowed_origins: ["http://localhost:5173"]
    rule: "Never allow_origins=['*'] with credentials enabled."

  rate_limiting:
    status: "Out of scope for 24h. Note it as future work if asked."
```

### 12.3 Where the ownership filter lives

```python
# CORRECT — filter derived from the verified token
def list_my_documents(db: Session, current_user: User):
    return db.query(CustomerInvoice).filter(
        CustomerInvoice.customer_id == current_user.partner_id
    )

# WRONG — client controls the filter. Complete authorisation bypass.
def list_my_documents(db: Session, partner_id: int):
    return db.query(CustomerInvoice).filter(
        CustomerInvoice.customer_id == partner_id
    )
```

### 12.4 Document numbering — concurrency

```yaml
sequences:
  module: "services/sequences.py"
  formats:
    purchase_order:  "P00001"          # P + 5 digits
    sales_order:     "S00001"
    vendor_bill:     "BILL/2026/0001"  # prefix / year / 4 digits, resets yearly
    customer_invoice:"INV/2026/0001"
    payment:         "PAY/2026/0001"
    journal_entry:   "JE/2026/0001"    # manual entries only; document-sourced
                                       # entries reuse the source document number
  implementation:
    table: "sequences(name PK, prefix, year, last_number)"
    algorithm:
      - "SELECT ... FOR UPDATE on the sequence row (row-level lock)"
      - "increment last_number"
      - "format and return"
      - "the caller's commit releases the lock"
    forbidden: "SELECT MAX(number) + 1 — races under concurrency and reuses numbers"
    why: >
      Two users clicking Confirm at the same instant must not receive the same
      number. A UNIQUE constraint would catch it, but as a 500 error rather than
      correct behaviour. See §10.11.
```

---

## 13. Frontend specification

### 13.1 Design system

```yaml
design:
  principle: >
    ONE table component, ONE form shell, ONE kanban grid, ONE status badge, reused
    everywhere. The mockup has ~20 screens; if each is bespoke you will not finish,
    and consistency is an explicit judging criterion. Consistency beats variety.

  palette:
    rationale: "Derived from the mockup's own accents. Neutral base, purposeful colour."
    tokens:
      background: "#FFFFFF"
      surface: "#F8F9FB"
      border: "#E2E5EA"
      text_primary: "#1A1D23"
      text_secondary: "#6B7280"
      primary: "#7C2D55" # deep maroon — mockup's Post/Confirm/Print buttons
      primary_hover: "#5F2242"
      accent: "#3B82F6" # blue — secondary actions, links
      success: "#16A34A" # paid, achieved, balanced
      warning: "#D97706" # partial, exceeds budget
      danger: "#DC2626" # unpaid, unbalanced, destructive
      draft: "#9CA3AF" # neutral grey for draft states
  rule: >
    These are Tailwind theme extensions. No hex codes inline in components.

  typography:
    font: "Inter, system-ui fallback — self-hosted or system, NEVER a CDN (offline rule)"
    scale:
      {
        page_title: "24px/600",
        section: "18px/600",
        body: "14px/400",
        label: "13px/500",
        table_cell: "14px/400",
        money: "14px/500 tabular-nums",
      }
    money_rule: >
      Every monetary figure uses font-variant-numeric: tabular-nums and is
      right-aligned. Columns of digits that do not line up read as amateur.

  spacing:
    base: "4px scale (Tailwind default)"
    page_padding: "24px"
    card_padding: "20px"
    form_row_gap: "16px"
    table_cell_padding: "12px 16px"

  responsive:
    breakpoints: { mobile: "<768px", tablet: "768-1024px", desktop: ">1024px" }
    rules:
      - "Sidebar collapses to a hamburger drawer below 768px"
      - "Tables become stacked cards below 768px — never a horizontal scrollbar"
      - "Forms go single-column below 768px"
      - "Every action reachable on desktop is reachable on mobile"
    verification: "Test at 375px, 768px and 1440px before calling any screen done."
```

### 13.2 Shared components — build these FIRST

```yaml
shared_components:
  DataTable:
    props: [columns, rows, loading, error, page, pageSize, total, onPageChange,
            onRowClick, searchValue, onSearchChange, emptyMessage]
    features: [server-side pagination, search box, loading skeleton, empty state,
               error state with retry, right-aligned money columns]
    used_by: "every list view in the app — contacts, products, accounts, journals,
              journal entries, POs, bills, SOs, invoices, payments, budgets"

  KanbanGrid:
    props: [items, renderCard, loading, onCardClick]
    used_by: "Contact, Product, Analytics, Budget Report (mockup requires all four)"

  ViewSwitcher:
    purpose: "List/Kanban toggle in the top-right, per the mockup"
    note: "Pure client-side toggle over ONE API response. Not two endpoints."

  FormShell:
    props: [title, state, actions, children, onBack]
    features: "renders the New/Confirm/Back button row and the state pipeline
               (Draft > Confirm > Revised > Cancelled) shown in the mockup"

  StatusBadge:
    mapping:
      draft: draft; confirmed: accent; posted: success; cancelled: danger
      paid: success; partial: warning; not_paid: danger; revised: accent

  MoneyInput / MoneyDisplay:
    rules:
      - "MoneyInput holds a string, never a JS number"
      - "MoneyDisplay formats with Indian grouping: ₹1,00,000.00"
      - "NEVER perform arithmetic in JS — display server-computed values"

  LineItemsTable:
    used_by: "PO, Bill, SO, Invoice, Journal Entry, Budget"
    features: [add/remove rows, per-row product or account select, live line total
               from the server on blur, running footer totals]
    journal_entry_variant: >
      Shows running Debit and Credit totals in the footer with the difference
      highlighted in danger colour when non-zero, and disables Post until they match.
```

### 13.3 Navigation

```yaml
navigation:
  structure: "Persistent left sidebar + top bar. Mirrors the mockup's menu exactly."
  menu:
    Dashboard: "/"
    Sales:
      [
        Sales Orders /sales/orders,
        Customer Invoices /sales/invoices,
        Receipts /sales/receipts,
      ]
    Purchase:
      [
        Purchase Orders /purchase/orders,
        Vendor Bills /purchase/bills,
        Payments /purchase/payments,
      ]
    Account:
      [
        Contacts /masters/contacts,
        Products /masters/products,
        Analytics /masters/analytics,
        Analytic Budget /budgets,
        Chart of Accounts /accounting/accounts,
        Journals /accounting/journals,
        Journal Entries /accounting/journal-entries,
      ]
    Report:
      [
        Balance Sheet /reports/balance-sheet,
        Profit and Loss /reports/profit-and-loss,
        Budget Report /reports/budget,
        Trial Balance /reports/trial-balance,
      ]
  role_visibility:
    contact: "sees ONLY the portal — My Invoices, My Bills. No masters, no reports."
    accountant: "everything except user management"
    admin: "everything plus Users"
  rules:
    - "Active route highlighted in the sidebar"
    - "Breadcrumb on every detail page"
    - "Back button on every form, per the mockup"
    - "Menu items the role cannot access are HIDDEN, not disabled — but the server
      enforces regardless (§12.2)"
```

### 13.4 Data fetching without a query library

```typescript
// hooks/useApi.ts — the entire state-management story. ~40 lines.
export function useApi<T>(path: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<T>(path));
    } catch (e) {
      setError(normaliseError(e));
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    refetch();
  }, deps);
  return { data, loading, error, refetch };
}
```

```yaml
mutation_pattern:
  rule: "After any successful mutation, call refetch() on the affected list."
  example: |
    const { data: invoices, refetch } = useApi<Page<Invoice>>('/customer-invoices');
    async function confirmInvoice(id: number) {
      await api.post(`/customer-invoices/${id}/confirm`);
      toast.success('Invoice confirmed and journal entry posted');
      await refetch();              // the list now shows the new state
    }
  justification_for_judges: >
    "We used plain fetch with a refetch-after-mutation pattern rather than adding
    a query library. The problem it solves — keeping lists fresh after a mutation —
    is one line of code here. Adding a dependency for that would be trendy tech
    without value."

  ui_states:
    rule: "EVERY data-driven view handles all four states explicitly."
    states:
      loading: "skeleton rows, never a bare spinner on a blank page"
      error: "message plus a Retry button that calls refetch()"
      empty: "friendly message plus the primary action, e.g. 'No invoices yet — New'"
      success: "the data"
    why: "Unhandled empty and error states are the most common Usability deduction."
```

### 13.5 Frontend validation

```yaml
frontend_validation:
  library: "react-hook-form + zod via @hookform/resolvers"
  rules:
    - "Zod schemas mirror the server rules in §11 — same limits, same messages"
    - "Validate on blur, re-validate on change once a field has errored"
    - "Errors appear inline beneath the field, never only in a toast"
    - "The submit button disables while a request is in flight (double-submit guard)"
    - "Server 422 field errors map back onto the form fields by name"
  money_inputs:
    - "type='text' with inputMode='decimal', NOT type='number'"
    - "regex mask ^\\d*\\.?\\d{0,2}$"
    - "value held as a string end to end; sent as a string"
    why: "type='number' coerces to a JS float in some browsers. That is the bug
          Decimal exists to prevent, reintroduced at the last possible moment."
```

---

## 14. Seed data

```yaml
seed:
  file: "backend/seed.py"
  requirements:
    - "Idempotent — safe to run repeatedly (upsert by natural key)"
    - "Completes in under 10 seconds"
    - "Produces a ledger that BALANCES"
    - "Produces a demo that looks like a real business, not five test rows"

  contents:
    users:
      - { login_id: "adminuser", role: admin, password: "Admin@2026" }
      - { login_id: "accountant", role: accountant, password: "Accnt@2026" }
      - {
          login_id: "rahulcust",
          role: contact,
          password: "Rahul@2026",
          partner: "Mr Rahul",
        }
    partners: "8 — mix of customer, vendor and both; realistic Indian names,
      addresses and phone numbers"
    product_categories: ["Furniture", "Electronics", "Services"]
    products: "12 — Table, Chair, Sofa, Wardrobe, Air Conditioner, Refrigerator,
      Delivery Service, Assembly Service..."
    accounts: "the 8 accounts of §10.1 — pre-configured, per the mockup"
    journals: "the 4 journals of §10.1"
    analytic_accounts: ["Project 1", "Project 2", "Showroom A", "Online Store"]
    opening_entry:
      description: "Capital injection so the Balance Sheet is non-trivial"
      lines:
        [
          { account: "Bank A/c", debit: "500000.00" },
          { account: "Capital A/c", credit: "500000.00" },
        ]
    transactions:
      volume: "~3 months of activity across Jan-Mar 2026"
      composition:
        - "12 purchase orders, 9 converted to bills, 7 of those confirmed"
        - "15 sales orders, 12 converted to invoices, 10 of those confirmed"
        - "payments covering: some fully paid, some partial, some unpaid"
        - "2 manual journal entries for Other Expense (rent, utilities)"
        - "analytic tags spread across all four analytics"
      deliberate_states: >
        Leave some documents in draft and some invoices partially paid. A demo
        where everything is uniformly complete looks synthetic and shows fewer
        of the system's states.
    budgets:
      - { name: "January 2026", state: confirmed, lines: "income and expense
            for Project 1 and Project 2, achievement between 40% and 120%" }
      - { name: "February 2026", state: draft }
      - {
          name: "Q1 Showroom A",
          state: confirmed,
          over_budget: true,
          note: "demonstrates the negative amount_to_achieve path",
        }

  post_seed_assertion:
    rule: >
      seed.py MUST finish by calling the trial-balance computation and asserting
      grand_total_debit == grand_total_credit. If it does not balance, print a
      loud error and exit non-zero.
    why: >
      Seed data is generated by the same posting engine as production paths. If
      the seed does not balance, the engine is broken — and you learn it in the
      first minute rather than during the demo.
```

---

## 15. Non-functional requirements

```yaml
performance:
  targets:
    list_endpoints: "< 200ms with seed data"
    report_endpoints: "< 500ms"
    page_interactive: "< 2s on localhost"
  rules:
    - name: "No N+1 queries"
      how: "selectinload / joinedload for every relationship rendered in a list"
      example: >
        The Journal Entries list shows partner and journal name. Without eager
        loading that is 1 + 2N queries for N rows. With it, 3 queries total.
      verification: "Set echo=True temporarily and count queries per request."
    - name: "Aggregate in SQL, not Python"
      how: "func.sum() with GROUP BY. Never load all lines and sum in a loop."
    - name: "Every list paginated"
    - name: "Indexes as specified in §7"
      verification: "EXPLAIN ANALYZE the balance-sheet query; confirm an index scan."

scalability:
  design_choices_and_their_justification:
    - choice: "Reports aggregate the ledger rather than reading stored balances"
      scales_because: "Correct at any volume; cost controlled by indexes"
      next_step_if_needed: "Materialised view refreshed on document confirm"
    - choice: "Stateless JWT auth"
      scales_because: "No server session store; horizontally scalable as-is"
    - choice: "All pagination is server-side"
      scales_because: "Response size is bounded regardless of table size"
    - choice: "Row-locked sequence table"
      scales_because: "Correct under concurrent writes, unlike SELECT MAX()+1"
  honest_limits:
    - "Single Postgres instance; no read replicas"
    - "No caching layer — unnecessary at this scale, and we did not want to add
      invalidation complexity we could not justify"
  talking_point: >
    "We indexed for the access patterns we actually have — journal lines by
    account for reports, by analytic for budgets, by partner for the portal.
    We deliberately did not add caching or materialised views because we have
    not measured a need, and unmeasured optimisation is just added complexity."

usability:
  requirements:
    - "Every destructive action confirms first"
    - "Every mutation produces a toast — success or error"
    - "Loading, error and empty states on every data view (§13.4)"
    - "Keyboard: Tab order follows visual order; Enter submits forms"
    - "Money right-aligned, tabular figures, ₹ symbol, Indian grouping"
    - "Dates formatted DD/MM/YYYY for display; ISO on the wire"
    - "Form errors inline and specific — never 'Invalid input'"
    - "The Journal Entry form shows live Debit/Credit totals and the difference"

coding_standards:
  python:
    - "ruff for lint and format; zero warnings at commit time"
    - "Type hints on every function signature"
    - "Docstrings on every service function stating what it does and what it raises"
    - "Max function length ~50 lines; extract helpers beyond that"
    - "No business logic in routers (§4.1)"
  typescript:
    - "strict: true in tsconfig"
    - "No `any` — use `unknown` and narrow"
    - "Props typed via interfaces; no inline object types on components"
    - "One component per file; filename matches the component name"
  both:
    - "No commented-out code committed"
    - "No console.log or print() in committed code"
    - "No secrets in source; .env only, and .env is gitignored"
    - "Names say what things are: post_journal_entry, not process()"
```

---

## 16. Git workflow

```yaml
git:
  why_this_matters: >
    Explicit hackathon requirement: "Use version control properly; one member
    managing the repo is not enough." Judges inspect the commit graph. All three
    members must have commits spread across the full 24 hours.

  branches:
    main: "always working, always demoable; protected by convention"
    feature: "feat/<area>-<short-description>, e.g. feat/posting-engine"
    fix: "fix/<short-description>"

  commit_convention:
    format: "<type>(<scope>): <imperative summary>"
    types: [feat, fix, refactor, test, docs, chore, style]
    examples:
      - "feat(accounting): add balance validation to posting engine"
      - "feat(invoices): post journal entry on confirm"
      - "fix(budgets): exclude draft bills from achievement"
      - "test(posting): cover unbalanced entry rejection"
    rules:
      - "One logical change per commit"
      - "Never commit .env, __pycache__, node_modules, .venv, or /uploads"
      - "Never commit directly to main after the first hour"

  pull_requests:
    rule: "Every feature branch merges via PR with at least one teammate's review comment"
    why: >
      A PR trail with real review comments from all three members is the artifact
      that satisfies the requirement. Rubber-stamp approvals with no comments look
      exactly like one person managing the repo.
    template: "What changed / Which SPEC section / Which scenarios verified / How to test"

  cadence:
    rule: "Every member commits at least once every 90 minutes"
    why: >
      A graph where one person commits 40 times and two commit 5 times each fails
      the requirement no matter how the work was actually divided.

  gitignore_must_include:
    - ".env"
    - "__pycache__/"
    - "*.pyc"
    - ".venv/"
    - "node_modules/"
    - "dist/"
    - "uploads/"
    - ".DS_Store"
```

---

## 17. Build order and priority tiers

> **Hard rule: no P1 work begins until every P0 item passes its §10 scenarios.**
> This tiering exists because an agent left to its own judgment will build the
> interesting features before the essential ones, and you will reach hour 20 with
> a PDF exporter and no Balance Sheet.

```yaml
P0_must_ship:
  definition: "Without these the project does not demo. Nothing else starts first."
  items:
    - "Auth: signup, login, JWT, three roles, route guards"
    - "Masters: Contacts, Products, Categories, Analytics, CoA, Journals — full CRUD"
    - "List + Form views for every master (Kanban is P1)"
    - "★ Posting engine with balance enforcement + automated tests (§10.4)"
    - "Manual Journal Entry create and list, with the blocking unbalanced warning"
    - "Purchase Order -> Vendor Bill -> confirm (posts entry) -> Payment"
    - "Sales Order -> Customer Invoice -> confirm (posts entry) -> Payment"
    - "Computed payment status: paid / partial / not_paid"
    - "Balance Sheet (including Current Period Earnings — see §10.9)"
    - "Profit and Loss"
    - "Trial Balance"
    - "Budgets: create, confirm, achievement computation"
    - "Dashboard tiles"
    - "Seed script with the balance assertion"
    - "Loading / error / empty states everywhere"
    - "Responsive layout at 375 / 768 / 1440"

P1_should_ship:
  definition: "Start only when every P0 scenario passes."
  items:
    - "Kanban views for Contact, Product, Analytics, Budget Report"
    - "Budget revise flow with bidirectional linking"
    - "Budget pie chart (recharts)"
    - "Over-budget non-blocking warnings on PO and Bill confirm"
    - "Achieved-amount drill-down to source documents"
    - "Contact portal: view own documents, pay own invoice"
    - "Image upload for contacts and products (local filesystem)"
    - "PDF export for Balance Sheet and P&L"

P2_only_if_time_remains:
  definition: "Realistically will not be reached. Do not start these before hour 20."
  items:
    - "Journal entry reversal"
    - "Email send on payment"
    - "Forgot password flow (stub the link until then — it must not 404)"
    - "Archived filter on the Chart of Accounts list"
    - "CSV export"

hour_by_hour:
  H0_H1:
    all_three: >
      Whiteboard together. Agree the schema. Commit SPEC.md, docker-compose.yml,
      .env.example, .gitignore and the empty folder structure. Confirm every
      member can run `docker compose up` and reach Postgres. DO NOT WRITE FEATURES
      IN THIS HOUR — the alignment is worth more than the code.
  H1_H4:
    A: "SQLAlchemy models for every table, constraints included; init_db(); seed skeleton"
    B: "Vite + Tailwind + shadcn; AppShell, Sidebar, DataTable, FormShell, StatusBadge"
    C: "Auth end to end: bcrypt, JWT, deps, signup/login routes + Login and Signup pages"
  H4_H8:
    A: "★ Posting engine + tests (§10.4). This is the highest-value block of the day."
    B: "Masters list + form pages, wired to real endpoints"
    C: "Masters routers and services; CoA and Journals seeded"
  H8_H14:
    A: "Bill and Invoice confirm flows calling the engine; payment service + status"
    B: "PO/SO/Bill/Invoice forms with LineItemsTable; payment dialogs"
    C: "Document routers; PO->Bill and SO->Invoice conversion; sequences with row lock"
  H14_H18:
    A: "Reports: Balance Sheet with Current Period Earnings, P&L, Trial Balance"
    B: "Report pages, Dashboard, Journal Entry form with live debit/credit totals"
    C: "Budgets: model, achievement computation, confirm; budget pages"
  H18_H21:
    all_three: >
      P1 items in priority order. Then polish: empty states, error copy, responsive
      passes at all three breakpoints, toast coverage, validation messages.
  H21_H22:
    all_three: >
      FEATURE FREEZE. No new code. Reset the database, re-seed, and walk the
      entire demo script (§18.2) end to end.
  H22_H24:
    all_three: >
      Rehearse the demo twice, out loud, with the person who will speak actually
      speaking. Fix only demo-breaking bugs. Write the README. Sleep if possible.
  hard_rule: >
    Nothing new is written after hour 21. A feature added at hour 23 that breaks
    the demo costs more than every feature it would have added.
```

---

## 18. Definition of done

### 18.1 Checklist

```yaml
done_when:
  correctness:
    - "Every §10.4 posting-engine scenario has a passing automated test"
    - "GET /reports/trial-balance returns is_balanced = true after the full demo flow"
    - "The Balance Sheet balances once Current Period Earnings is included"
    - "No float appears anywhere in a money code path (grep for 'float(')"
    - "Confirming a document with a deliberately broken engine leaves NO partial data"
  security:
    - "A portal user changing an invoice id in the URL receives 403"
    - "A tampered JWT is rejected"
    - "password_hash appears in no response (verified in /docs)"
    - "Every route declares its required role"
  quality:
    - "ruff and eslint pass with zero warnings"
    - "No console.log or print() in committed code"
    - "Every list view has loading, error and empty states"
    - "Every screen usable at 375px"
  process:
    - "All three members have commits spread across all 24 hours"
    - "Every feature branch merged via a PR with a real review comment"
    - "README explains setup in under 6 commands"
    - "docker compose down -v && up && seed produces a working demo from scratch"
```

### 18.2 Demo script — rehearse this exactly

```gherkin
Scenario: The eight-minute demo
  Given a freshly seeded database

  # 1 — Frame the problem (30s)
  Show the Dashboard. "Every business asks three questions: what do I own,
  what do I owe, did I make money. This system answers all three from one ledger."

  # 2 — Masters (45s)
  Contacts list, toggle to Kanban, open a form. Show Chart of Accounts and point
  out that every account carries a type that decides which report it lands on.

  # 3 — Purchase cycle (90s)
  Create a PO for a vendor, tagged to an analytic. Confirm it — note that nothing
  hits the ledger, because a PO is a commitment, not a financial event.
  Create Bill from PO; show the fields carried over and the PO back-link.
  Confirm the bill. Immediately open Journal Entries and show the entry that
  appeared: Purchase Expense debited, Creditors credited, balanced.

  # 4 — The invariant (45s)  ★ the moment that wins it
  Open a new Journal Entry. Enter 10,000 debit and 9,000 credit. Show the running
  totals, the difference in red, and the disabled Post button. Fix it to 10,000.
  Post succeeds. "This is enforced in the service layer, and the database
  constrains every line to be a debit or a credit but never both."

  # 5 — Sales cycle and payment (90s)
  SO -> Invoice -> Confirm. Show the journal entry: Debtors debited, Sales credited.
  Register a PARTIAL payment. Show the status move to Partial and amount due update.
  Pay the remainder. Status becomes Paid. Point out that status is computed from
  the ledger, not stored.

  # 6 — Budgets (60s)
  Open the confirmed January budget. Show achieved amount, percent and remaining,
  all computed live from the analytic tags on the documents just created. Show the
  over-budget case with its negative remaining figure. Click Revise; show the two
  budgets linked in both directions.

  # 7 — Reports (75s)  ★ the proof
  Profit and Loss: income, expenses, net income.
  Balance Sheet: "Assets equal Liabilities plus Capital plus this period's earnings."
  Trial Balance: "Total debits equal total credits across the entire database.
  Every number on these three screens came from one table."

  # 8 — Security (30s)
  Log in as the portal user. Show only their own invoices. Edit the invoice id in
  the URL to another partner's. 403. "Ownership is checked server-side on every read."

  # 9 — Engineering (45s)
  Open /docs — the full API, auto-generated. Open services/accounting.py — "this is
  the only file in the codebase that writes to the ledger; invoices, bills, payments
  and manual entries all call this one function." Open the git graph — three
  contributors, commits throughout.
```

### 18.3 Anticipated questions

```yaml
qa:
  - q: "Why this problem statement over the other two?"
    a: >
      Every business needs to know what it owns, what it owes, and whether it made
      money. Accounting is universal where B2B deal flow and HR payroll are niche.
      It is also the problem with the hardest logic to fake — if our double-entry
      is wrong, the Balance Sheet visibly does not balance. And Odoo's core product
      is accounting, so we built closest to what Odoo actually ships.

  - q: "Why FastAPI over MERN?"
    a: >
      Express needs three separate libraries for what one Pydantic class does —
      validation, serialisation and OpenAPI docs. Python's Decimal is the only safe
      way to do money arithmetic; JavaScript floats turn 199.99 x 3 into
      599.9699999999999, which breaks a Balance Sheet. SQLAlchemy makes the
      transaction boundary explicit, so an invoice and its journal entry commit
      together or roll back together. And Odoo is Python.

  - q: "How do you guarantee the ledger is correct?"
    a: >
      One function writes to the ledger — post_journal_entry. It validates the
      balance inside the transaction. The database constrains every line to be a
      debit or a credit but never both, and never negative. And the trial balance
      endpoint lets you verify the invariant across the whole database at any time.

  - q: "How does this scale?"
    a: >
      Reports aggregate indexed journal lines rather than reading stored balances,
      so they cannot drift and they stay correct at any volume. We indexed for our
      actual access patterns — lines by account for reports, document lines by
      analytic for budgets, invoices by partner for the portal. Auth is stateless
      JWT so the API scales horizontally. If the ledger reached millions of lines
      we would add a materialised view refreshed on confirm, but we would measure
      before adding that complexity.

  - q: "What would you build next?"
    a: >
      Multi-currency, fiscal-year closing entries that roll earnings into retained
      earnings, aged receivable ageing buckets, and full payment reconciliation
      allowing one payment to settle several invoices.

  - q: "What did you deliberately NOT build, and why?"
    a: >
      Cross-document payment reconciliation, caching, and a query library on the
      frontend. Each would have added complexity we could not justify inside the
      scope, and the brief explicitly warns against trendy technology that does not
      add value. We would rather defend every line we shipped.
```

---

## Appendix A — Glossary

| Term                   | Meaning                                                       |
| ---------------------- | ------------------------------------------------------------- |
| **Journal Entry**      | A single balanced financial transaction in the ledger         |
| **Journal Entry Line** | One debit or one credit against one account                   |
| **Journal**            | A grouping of entries by nature (Sales, Purchase, Bank, Cash) |
| **Chart of Accounts**  | The full list of accounts money can flow through              |
| **Account Type**       | Decides which report an account appears on and on which side  |
| **Debtors**            | Money customers owe us — an asset                             |
| **Creditors**          | Money we owe vendors — a liability                            |
| **Analytic Account**   | A project/cost-centre tag used only for budgeting             |
| **Posting**            | Writing a balanced entry into the ledger, making it permanent |
| **Source Document**    | An invoice, bill or payment that generates a journal entry    |
| **Committed Amount**   | What a budget planned to spend or earn                        |
| **Achieved Amount**    | What actually happened, from tagged confirmed documents       |
| **Trial Balance**      | Every account's debit and credit totals; must balance overall |

---

## Appendix B — Agent working agreement

```yaml
rules_for_the_implementing_agent:
  - "Read §6 before writing any service code. The accounting model is not obvious."
  - "Implement in the §17 order. Do not start P1 before P0 passes."
  - "Every behaviour must trace to a §10 scenario. If there is no scenario, ASK."
  - "Never write to journal_entries outside services/accounting.py (P6)."
  - "Never use float in a money path (P2)."
  - "Never commit inside the posting engine (P3)."
  - "Pin the exact versions in §3. If one fails to install, report and stop."
  - "When a mockup detail and this spec conflict, follow the spec and flag it."
  - "Prefer deleting code over adding a flag. Scope discipline is the whole game."
  - "If you are unsure whether something is in scope, it is not. Ask."
```

_End of specification._
