"""Application error hierarchy and the single error envelope (SPEC.md §12.1).

Every error the API returns has the same shape::

    {"error": {"code", "message", "details", "correlation_id"}}

Services raise these; they know nothing about HTTP beyond carrying the status
code that the handler in ``main.py`` turns into a response. That keeps
``services/`` free of FastAPI imports while still letting one raise site decide
between 404 and 422.
"""AppError hierarchy and the FastAPI handlers that shape every error
response into the SPEC.md §12.1 envelope: {error: {code, message, details,
correlation_id}}.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for every expected, user-facing failure.

    Unexpected failures are NOT this class — they fall through to the catch-all
    handler and become a generic 500 with no internals leaked.
    """

    code: str = "VALIDATION_ERROR"
    status_code: int = 422
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details
        self.correlation_id = str(uuid.uuid4())
        super().__init__(self.message)

    def to_envelope(self) -> dict[str, Any]:
        """Render the §12.1 error envelope."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "correlation_id": self.correlation_id,
            }
        }


# --- ledger errors (SPEC.md §8.1) -------------------------------------------


class UnbalancedEntryError(AppError):
    """Total debits do not equal total credits, or there are too few lines."""

    code = "UNBALANCED_ENTRY"
    status_code = 422
    message = "Debit and credit amounts do not match."

    def __init__(
        self,
        message: str | None = None,
        *,
        total_debit: Decimal | None = None,
        total_credit: Decimal | None = None,
        difference: Decimal | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if details is None and total_debit is not None:
            # Money crosses the wire as a string, never a JSON number (§9).
            details = {
                "total_debit": f"{total_debit:.2f}",
                "total_credit": f"{total_credit:.2f}",
                "difference": f"{difference:.2f}",
            }
        super().__init__(message, details=details)


class InvalidLineError(AppError):
    """One line is malformed: negative, two-sided, or empty on both sides."""

    code = "INVALID_LINE"
    status_code = 422
    message = "A journal entry line is invalid."

    def __init__(self, message: str | None = None, *, line_index: int) -> None:
        # 0-based index so the frontend can highlight the offending row (§10.4).
        super().__init__(message, details={"line_index": line_index})


class AccountNotFoundError(AppError):
    code = "ACCOUNT_NOT_FOUND"
    status_code = 404
    message = "The referenced account does not exist."


class AccountArchivedError(AppError):
    code = "ACCOUNT_ARCHIVED"
    status_code = 422
    message = "An archived account cannot be used on a new entry."


class JournalNotFoundError(AppError):
    code = "JOURNAL_NOT_FOUND"
    status_code = 404
    message = "The referenced journal does not exist."


class AccountGroupTypeMismatchError(AppError):
    code = "ACCOUNT_GROUP_TYPE_MISMATCH"
    status_code = 422
    message = "This account type is not valid for the chosen account group."


class EntryImmutableError(AppError):
    code = "ENTRY_IMMUTABLE"
    status_code = 405
    message = "A posted journal entry cannot be modified or deleted."


# --- general errors ---------------------------------------------------------


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404
    message = "The requested resource does not exist."


class ConflictError(AppError):
    code = "IN_USE"
    status_code = 409
    message = "The resource is in use and cannot be changed."
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Base class for every deliberately-raised API error.

    Carries everything the §12.1 envelope needs: an HTTP status, a
    SCREAMING_SNAKE_CASE code, a message safe to show verbatim in a toast,
    and optional structured details.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _envelope(code: str, message: str, details: Any, correlation_id: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "correlation_id": correlation_id,
        }
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    correlation_id = str(uuid.uuid4())
    logger.warning("AppError %s: %s [%s]", exc.code, exc.message, correlation_id)
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, exc.details, correlation_id),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    correlation_id = str(uuid.uuid4())
    # Each error dict can carry a raw exception object under "ctx" (e.g. the
    # ValueError raised by a field_validator) — not JSON serialisable as-is.
    raw_errors = [{k: v for k, v in err.items() if k != "ctx"} for err in exc.errors()]
    fields = jsonable_encoder(raw_errors)
    logger.warning("ValidationError: %s [%s]", fields, correlation_id)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope(
            "VALIDATION_ERROR",
            "One or more fields failed validation.",
            {"fields": fields},
            correlation_id,
        ),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    correlation_id = str(uuid.uuid4())
    logger.warning(
        "HTTPException %s: %s [%s]", exc.status_code, exc.detail, correlation_id
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope("HTTP_ERROR", str(exc.detail), None, correlation_id),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = str(uuid.uuid4())
    logger.exception("Unhandled exception [%s]", correlation_id)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            "INTERNAL_ERROR", "An unexpected error occurred.", None, correlation_id
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers so no route in the app can return a differently
    shaped error body (SPEC.md §12.1 rule)."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
