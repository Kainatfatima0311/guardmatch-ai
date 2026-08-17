"""Request middleware: correlation, timing, logging and metrics.

Every request gets a ``request_id`` — taken from an inbound header when the
caller supplied one, so a trace can span services, and generated otherwise. It
is bound to the logging context, returned in a response header, and echoed in
scoring response bodies.

That id is what makes a ranking decision reconstructable months later. Without
it, "why was this candidate ranked ninth on the 14th" has no answer.

Nothing here logs a request body. Bodies contain CV text, and logs are retained
longer and read more widely than the data they describe.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from guardmatch.core.logging import get_logger, new_request_id, request_context
from guardmatch.core.metrics import request_duration_seconds, requests_total

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Bind a correlation id, time the request, and record the outcome."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        # The route template rather than the concrete path, so metric labels stay
        # bounded. Labelling by raw path would create a new time series per
        # candidate id in any future path parameter.
        endpoint = request.url.path

        with request_context(incoming or new_request_id()) as request_id:
            logger.info("request_started", method=request.method, endpoint=endpoint)
            started = time.perf_counter()

            try:
                response = await call_next(request)
            except Exception:
                elapsed = time.perf_counter() - started
                requests_total.labels(endpoint=endpoint, method=request.method, status="500").inc()
                request_duration_seconds.labels(endpoint=endpoint).observe(elapsed)
                logger.exception(
                    "request_failed",
                    method=request.method,
                    endpoint=endpoint,
                    duration_ms=round(elapsed * 1000, 2),
                )
                raise

            elapsed = time.perf_counter() - started
            requests_total.labels(
                endpoint=endpoint, method=request.method, status=str(response.status_code)
            ).inc()
            request_duration_seconds.labels(endpoint=endpoint).observe(elapsed)

            logger.info(
                "request_finished",
                method=request.method,
                endpoint=endpoint,
                status=response.status_code,
                duration_ms=round(elapsed * 1000, 2),
            )

            response.headers[REQUEST_ID_HEADER] = request_id
            return response
