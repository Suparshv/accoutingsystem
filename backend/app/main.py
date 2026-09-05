"""FastAPI application entry point."""

import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.errors import register_exception_handlers
from app.routers import (
    accounts,
    analytics,
    auth,
    budgets,
    journal_entries,
    journals,
    partners,
    payments,
    products,
    purchase_orders,
    vendor_bills,
)

# Startup guard for the Python floor in SPEC.md §3 (python: ">=3.10"). Raising
# here fails loudly at import time rather than at the first use of 3.10 syntax.
if sys.version_info < (3, 10):
    raise RuntimeError(
        "Urban Furniture Accounting requires Python 3.10 or newer "
        f"(SPEC.md §3); this interpreter is {sys.version.split()[0]}. "
        "Recreate the venv with a newer Python: python3 -m venv .venv"
    )

app = FastAPI(title="Urban Furniture Accounting API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The four §12.1 handlers live in core/errors.py alongside the AppError they
# shape, so this stays a single call rather than a block of decorators.
register_exception_handlers(app)


# --- routes -----------------------------------------------------------------

API_PREFIX = "/api"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(partners.router, prefix=API_PREFIX)
app.include_router(products.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(accounts.router, prefix=API_PREFIX)
app.include_router(journals.router, prefix=API_PREFIX)
app.include_router(journal_entries.router, prefix=API_PREFIX)
app.include_router(purchase_orders.router, prefix=API_PREFIX)
app.include_router(vendor_bills.router, prefix=API_PREFIX)
app.include_router(payments.router, prefix=API_PREFIX)
app.include_router(budgets.router, prefix=API_PREFIX)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe used by the frontend and the demo script."""
    return {"status": "ok"}
