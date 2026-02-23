"""Request ID middleware for request tracing."""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request.

    - Reads ``X-Request-ID`` from incoming headers (e.g. from a load balancer).
    - Generates a new UUID if none is present.
    - Binds the ID into structlog's context vars so every log line includes it.
    - Returns the ID in the response ``X-Request-ID`` header for client debugging.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
