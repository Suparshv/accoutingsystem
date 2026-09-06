"""Application error hierarchy and the single error envelope (SPEC.md §12.1).

Every error the API returns has the same shape::

    {"error": {"code", "message", "details", "correlation_id"}}

Services raise an AppError; they know nothing about HTTP beyond carrying the
status code that a handler turns into a response. That keeps ``services/``
free of FastAPI imports while still letting one raise site decide between 404
and 422.

``register_exception_handlers`` wires the four handlers §12.1 requires, so no
route in the app can return a differently-shaped error body.

AppError supports two calling conventions, both of which are in use:

* the explicit form, where the raise site supplies everything ::

      raise AppError(404, "NOT_FOUND", "Partner not found.")

* the subclass form, where the class supplies the code and status ::

      raise NotFoundError("Account 7 does not exist.")
      raise UnbalancedEntryError(total_debit=d, total_credit=c, difference=x)

The subclasses are worth having wherever a specific failure is raised from
more than one place or carries structured details, because the code and the
status then live in exactly one spot.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Base class for every expected, user-facing failure.

    Unexpected failures are NOT this class — they fall through to the catch-all
    handler and become a generic 500 with no internals leaked.
    """

    code: str = "VALIDATION_ERROR"
    status_code: int = 422
    message: str = "The request could not be processed."

    def __init__(self, *args: Any, details: dict[str, Any] | None = None) -> None:
        if args and isinstance(args[0], int):
            # Explicit form: AppError(status_code, code, message[, details]).
            self.status_code = args[0]
            self.code = args[1]
            self.message = args[2]
            if len(args) > 3 and details is None:
                details = args[3]
        else:
            # Subclass form: class attributes supply the code and the status,
            # and the single optional positional argument overrides the message.
            override = args[0] if args else None
            self.message = override or type(self).message

        self.details = details
        # Generated once, here, so the id written to the log is the same id the
        # client is shown — that is the whole point of a correlation id.
        self.correlation_id = str(uuid.uuid4())
        super().__init__(self.message)

    def to_envelope(self) -> dict[str, Any]:
        """Render the §12.1 error envelope."""
        return _envelope(self.code, self.message, self.details, self.correlation_id)


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


class CostAboveSalesPriceError(AppError):
    """A product may not cost more to buy than it is offered for (§11).

    Sibling of AccountGroupTypeMismatchError: a two-field consistency rule
    that neither field can enforce alone, so it lives next to it.
    """

    code = "COST_ABOVE_SALES_PRICE"
    status_code = 422
    message = "Cost price cannot be greater than sales price."


class EntryImmutableError(AppError):
    code = "ENTRY_IMMUTABLE"
    status_code = 405
    message = "A posted journal entry cannot be modified or deleted."


# --- general errors ---------------------------------------------------------


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404
    message = "The requested resource does not exist."


# --- upload errors (SPEC.md §5 UPLOAD_DIR, §17 P1) --------------------------


class UnsupportedImageTypeError(AppError):
    """The upload is not a JPEG or a PNG — by signature, not by its name."""

    code = "UNSUPPORTED_IMAGE_TYPE"
    status_code = 415
    message = "Only JPEG and PNG images can be uploaded."


class ImageTooLargeError(AppError):
    code = "IMAGE_TOO_LARGE"
    status_code = 413
    message = "That image is larger than the 2 MB limit."


class ConflictError(AppError):
    code = "IN_USE"
    status_code = 409
    message = "The resource is in use and cannot be changed."


# --- handlers (SPEC.md §12.1) -----------------------------------------------

# Framework-raised failures carry no code of their own, so map the statuses
# that mean something specific in this API. 405 is how a posted journal entry
# refuses DELETE — immutability by absence of a route (R4).
_HTTP_STATUS_CODES = {
    401: "TOKEN_INVALID",
    403: "INSUFFICIENT_ROLE",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "IN_USE",
}


def _envelope(
    code: str, message: str, details: Any, correlation_id: str
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "correlation_id": correlation_id,
        }
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Expected, user-facing failures raised by services and routers."""
    logger.warning("AppError %s: %s [%s]", exc.code, exc.message, exc.correlation_id)
    return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic rejected the request — malformed JSON, bad types, failed rules."""
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
    """Framework-raised failures, including the 405 on DELETE /journal-entries."""
    correlation_id = str(uuid.uuid4())
    logger.warning(
        "HTTPException %s: %s [%s]", exc.status_code, exc.detail, correlation_id
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(
            _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR"),
            str(exc.detail),
            None,
            correlation_id,
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Anything unforeseen. The correlation id is the only way back to the log.

    The body carries no stack trace, no SQL, no file path and no table name
    (§10.11) — the detail goes to the server log, not to the client.
    """
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
