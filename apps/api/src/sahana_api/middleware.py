"""HTTP middleware: correlation IDs and a request-body size limit.

``CorrelationIdMiddleware`` assigns each request a correlation id (honouring an
inbound ``X-Request-ID`` when present), binds it into the structlog contextvars so
every log line for the request — including the pipeline's node logs — is
correlated, and echoes it back in the ``X-Request-ID`` response header. The bind
is cleared after the request so ids never leak across requests. PII redaction is
unaffected: only the opaque id is bound.

``BodySizeLimitMiddleware`` rejects a request whose declared ``Content-Length``
exceeds the configured maximum with a ``413`` error envelope, before the body is
read or parsed, so oversized input never reaches the model paths.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.status import HTTP_413_CONTENT_TOO_LARGE
from starlette.types import ASGIApp

from sahana_api.schemas.common import ErrorDetail, ErrorEnvelope

REQUEST_ID_HEADER = "X-Request-ID"

Dispatch = Callable[[Request], Awaitable[Response]]


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind a per-request correlation id into logs and the response header."""

    async def dispatch(self, request: Request, call_next: Dispatch) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming if incoming else uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds ``max_bytes`` with a 413."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Dispatch) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > self._max_bytes:
                envelope = ErrorEnvelope(
                    error=ErrorDetail(
                        code="request_too_large",
                        message=f"request body exceeds the {self._max_bytes} byte limit",
                    )
                )
                return JSONResponse(
                    status_code=HTTP_413_CONTENT_TOO_LARGE,
                    content=envelope.model_dump(),
                )
        return await call_next(request)
