"""Domain exceptions and the consistent error-envelope handlers.

Every error response shares the :class:`~sahana_api.schemas.common.ErrorEnvelope`
shape. Handlers deliberately avoid echoing submitted values so personal data
(phone, name) never leaks into an error body.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from sahana_api.db.engine import DatabaseNotConfiguredError
from sahana_api.schemas.common import ErrorDetail, ErrorEnvelope, FieldError


class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource} not found")
        self.resource = resource


def _envelope(code: str, message: str, fields: list[FieldError] | None = None) -> dict[str, object]:
    """Serialize an error envelope to a JSON-ready dict."""
    detail = ErrorDetail(code=code, message=message, fields=fields or [])
    return ErrorEnvelope(error=detail).model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the error-envelope handlers to ``app``."""

    @app.exception_handler(NotFoundError)
    async def _not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_envelope("not_found", f"{exc.resource} not found"),
        )

    @app.exception_handler(DatabaseNotConfiguredError)
    async def _db_unconfigured(_request: Request, _exc: DatabaseNotConfiguredError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_envelope("database_unavailable", "database is not configured"),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            FieldError(
                field=".".join(str(part) for part in error["loc"] if part != "body") or "body",
                message=str(error["msg"]),
            )
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_envelope("validation_error", "request validation failed", fields),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", message),
        )
