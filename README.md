# Urban Furniture Accounting System

A double-entry accounting system for a furniture trading business. It covers the full
sales cycle (sales order → customer invoice → receipt), the full purchase cycle
(purchase order → vendor bill → payment), manual journal entries, analytic budgets, and
the four financial reports derived from the ledger. Every financial transaction produces
a balanced journal entry, and nothing stores a balance — account balances, payment
status, and budget achievement are all computed on read from the underlying entries and
documents. A customer/vendor portal lets a linked contact see their own invoices and
bills and pay their own invoices online.

## Tech stack

**Backend** (`backend/requirements.txt`, pinned exactly)

| | |
|---|---|
| Python | 3.10+ required (enforced at import in `app/main.py`); 3.13.3 in the local venv |
| FastAPI | 0.115.6 |
| Uvicorn | 0.34.0 |
| SQLAlchemy | 2.0.36 |
| psycopg (binary) | 3.2.3 |
| Pydantic / pydantic-settings | 2.10.4 / 2.7.0 |
| PyJWT / bcrypt | 2.10.1 / 4.2.1 |
| pytest / httpx / ruff | 8.3.4 / 0.28.1 / 0.8.4 |
| PostgreSQL | 16 (via `postgres:16` in `docker-compose.yml`) |

**Frontend** (`frontend/package.json`)

| | |
|---|---|
| React / React DOM | 18.3.1 |
| TypeScript | 5.6.3 |
| Vite | 5.4.11 |
| React Router | 6.28.0 |
| Tailwind CSS | 3.4.17 |
| Radix UI primitives | dialog 1.1.4, select 2.1.4, toast 1.2.4, tabs 1.1.2, label 2.1.15, slot 1.1.1 |
| react-hook-form / zod | 7.54.2 / 3.24.1 |
| Recharts | 2.15.0 (budget pie chart) |
| lucide-react | 0.468.0 |
| ESLint | 9.17.0 |

## Setup

From a clean clone:

```bash
# 1. Database
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -c "from app.database import init_db; init_db()"   # creates tables
python seed.py                                            # demo data
uvicorn app.main:app --reload --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
cp .env.example .env
npm run dev
```

The frontend runs on <http://localhost:5173> and the API on <http://localhost:8000>
(interactive docs at <http://localhost:8000/docs>, liveness at `/api/health`).

**Ports:** `docker-compose.yml` publishes Postgres on 5432 and the tracked
`docker-compose.override.yml` additionally publishes it on 5541 — `docker compose config`
shows both, so either works in `DATABASE_URL`. `.env.example` uses 5432.

**Environment variables** — `backend/.env` (see `app/config.py`):
`DATABASE_URL`, `JWT_SECRET`, `JWT_ALGORITHM` (default `HS256`), `JWT_EXPIRE_MINUTES`
(default `480`), `CORS_ORIGINS` (default `http://localhost:5173`), `UPLOAD_DIR`
(default `./uploads`). `frontend/.env` needs only `VITE_API_BASE_URL`
(default `http://localhost:8000/api`). Both `.env` files are gitignored.

**Verification note:** `docker compose up -d`, `init_db()`, `python seed.py`,
`uvicorn`, `npm run dev`, `npm run build`, `npm run lint` and `pytest` were all run
against this checkout while writing this file. `python -m venv`, `pip install` and
`npm install` were *not* re-run here (the venv and `node_modules` already existed), so
those three lines are the standard commands rather than ones freshly verified.

### Tests

```bash
cd backend && source .venv/bin/activate && python -m pytest
```

**176 tests, all passing** (verified on this checkout), across 8 files covering the
posting engine, purchase and sales cycles, payments, budgets, products, search, and
contact image upload. There is no frontend test suite; the frontend is checked with
`npx tsc --noEmit` and `npm run lint`, both of which pass.

### Resetting the database

There are no migrations — the schema comes from `create_all`. After any model change:

```bash
docker compose down -v && docker compose up -d
cd backend && python -c "from app.database import init_db; init_db()" && python seed.py
```

`seed.py` upserts master data on every run but only seeds transactions into an empty
ledger; against an already-seeded database it re-checks the trial balance and stops.
It ends by asserting `grand_total_debit == grand_total_credit` and exits non-zero if the
ledger does not balance.

## Login credentials

Created by `backend/seed.py`:

| Login ID | Password | Role |
|---|---|---|
| `adminuser` | `Admin@2026` | Admin |
| `accountant` | `Accnt@2026` | Accountant |
| `rahulcust` | `Rahul@2026` | Contact (portal, linked to partner "Mr Rahul") |

The login page also has an **Explore Pages in Demo Mode** button, which browses the UI
against bundled mock data without a backend.

## Features

### Accountant

The full application except user management. Sidebar: Dashboard, Sales, Purchase,
Account, Report.

- **Dashboard** — all/confirmed/draft counts for sales orders and purchase orders, plus
  budget counts.
- **Sales** — Sales Orders (create, edit while draft, confirm, cancel, convert to
  invoice), Customer Invoices (create directly or from an order, edit while draft,
  confirm → posts a balanced journal entry, cancel, register a receipt), Receipts (list
  of received payments).
- **Purchase** — Purchase Orders (create, edit while draft, confirm, cancel, convert to
  bill), Vendor Bills (create directly or from an order, edit while draft, confirm →
  posts a balanced journal entry, cancel, register a payment), Payments (list of sent
  payments).
- **Masters** — Contacts (customers/vendors, with JPEG/PNG avatar upload up to 2 MB),
  Products and product categories, Analytic accounts. Contacts, Products, Analytics and
  the Budget Report each offer a list/Kanban view toggle.
- **Accounting** — Chart of Accounts (create, edit, archive), Journals, Journal Entries
  (list, view, post a manual balanced entry; posting is blocked until debits equal
  credits).
- **Budgets** — create budget lines per analytic account, confirm, cancel, and revise
  (revising creates a linked draft copy and marks the original revised, with links
  navigable in both directions). Achieved amount, achieved percent and remaining amount
  are computed live from confirmed invoices and bills, and remaining goes negative when
  a budget is overspent rather than clamping at zero.
- **Reports** — Balance Sheet (with a Current Period Earnings row so it balances),
  Profit and Loss, and Trial Balance (with a live balanced/not-balanced banner), each
  with a year selector and a Print button that uses the browser's print dialog; plus a
  Budget Report showing committed vs achieved per budget as a table or a Recharts pie
  chart (no year selector or Print button on that one).
- **Search and pagination** — server-side search and pagination on every list
  (contacts, products, analytics, accounts, journals, journal entries, purchase orders,
  vendor bills, sales orders, customer invoices, payments, budgets, users).

Documents follow draft → confirmed → cancelled. Orders never touch the ledger; only
confirming an invoice or a bill posts an entry. Confirmed documents cannot be edited,
and a document with a confirmed invoice/bill cannot be cancelled.

### Admin

Everything the accountant has, plus **Users** (`/settings/users`) — list users and
create new ones. A portal (contact) user must be linked to a contact. Self-signup at
`/signup` creates an accountant.

### Contact (portal)

Sidebar shows only the portal.

- **My Invoices / My Bills** — the contact's own documents, filtered server-side from
  the verified token, showing number, date, total, amount due and payment status.
  Non-confirmed rows read "Awaiting confirmation" or "Cancelled" instead of a payment
  badge.
- **Document detail** — clicking a row opens a read-only view with line items
  (product/service, quantity, unit price, line total), the totals, and a payment history
  of confirmed payments where any exist.
- **Paying an invoice** — a contact can register and confirm a payment against their own
  confirmed customer invoice. Vendor bills are read-only for a contact (a bill is money
  the business owes them), and the server refuses a contact payment against any bill.
