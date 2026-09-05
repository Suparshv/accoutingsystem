"""AppError hierarchy and the FastAPI handlers that shape every error
response into the SPEC.md §12.1 envelope: {error: {code, message, details,
correlation_id}}.
"""

from __future__ import annotations

import logging
import uuid
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
