"""FastAPI application entry point."""

import logging
import sys
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.core.errors import AppError
from app.routers import accounts, journal_entries, journals

# Startup guard for the Python floor in SPEC.md §3 (python: ">=3.10"). Raising
# here fails loudly at import time rather than at the first use of 3.10 syntax.
if sys.version_info < (3, 10):
    raise RuntimeError(
        "Urban Furniture Accounting requires Python 3.10 or newer "
        f"(SPEC.md §3); this interpreter is {sys.version.split()[0]}. "
        "Recreate the venv with a newer Python: python3 -m venv .venv"
    )

logger = logging.getLogger(__name__)

app = FastAPI(title="Urban Furniture Accounting API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- error envelope (SPEC.md §12.1) -----------------------------------------
# Four handlers so that no route can return a differently-shaped error body.


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """Expected, user-facing failures raised by services."""
    logger.info("%s %s [%s]", exc.code, exc.message, exc.correlation_id)
    return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())


@app.exception_handler(RequestValidationError)
def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic rejected the body — malformed JSON, bad types, failed rules."""
    correlation_id = str(uuid.uuid4())
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "The request body failed validation.",
                "details": {"errors": _serialisable_errors(exc)},
                "correlation_id": correlation_id,
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Framework-raised failures, including the 405 on DELETE /journal-entries."""
    codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "TOKEN_INVALID"}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": codes.get(exc.status_code, "HTTP_ERROR"),
                "message": str(exc.detail),
                "details": None,
                "correlation_id": str(uuid.uuid4()),
            }
        },
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Anything unforeseen. The correlation id is the only way back to the log.

    The body carries no stack trace, no SQL, no file path and no table name
    (§10.11) — the detail goes to the server log, not to the client.
    """
    correlation_id = str(uuid.uuid4())
    logger.exception("Unhandled error [%s]", correlation_id)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Something went wrong. Please try again.",
                "details": None,
                "correlation_id": correlation_id,
            }
        },
    )


def _serialisable_errors(exc: RequestValidationError) -> list[dict]:
    """Strip the non-JSON-serialisable context Pydantic attaches to errors."""
    return [
        {k: v for k, v in error.items() if k != "ctx"} | {"loc": list(error["loc"])}
        for error in exc.errors()
    ]


# --- routes -----------------------------------------------------------------

API_PREFIX = "/api"

app.include_router(accounts.router, prefix=API_PREFIX)
app.include_router(journals.router, prefix=API_PREFIX)
app.include_router(journal_entries.router, prefix=API_PREFIX)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe used by the frontend and the demo script."""
    return {"status": "ok"}
