"""FastAPI application entry point."""

import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

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


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe used by the frontend and the demo script."""
    return {"status": "ok"}
