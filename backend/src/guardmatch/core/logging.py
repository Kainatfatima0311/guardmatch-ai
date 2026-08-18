"""Structured logging.

The brief requires real logging and states that print statements do not count.
That requirement is enforced in two places: ruff's ``T20`` rule fails the lint
step on any ``print()`` in the source tree, and this module provides the thing
to use instead.

Logs are JSON by default so they can be shipped and queried. Every line carries
a ``request_id`` and the active ``model_version``, which is what makes it
possible to reconstruct a specific ranking decision months later.

The redaction layer matters more than it looks. Logs are retained for a long
time and are readable by more people than the database is, so a service that
logs raw CV text has quietly built a second, less protected copy of every
applicant's personal data. Nothing here logs candidate text, names, or protected
attributes; only identifiers, derived numeric features and outcomes.
"""

from __future__ import annotations

import contextvars
import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

from guardmatch.core.config import get_settings

# Correlation id for the current request, set by the API middleware and read by
# the log processor below. A context variable rather than a global so that
# concurrent requests do not overwrite each other's id.
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

# Keys whose values must never reach a log line. Matching is on the key name, so
# a caller passing cv_text=... gets it redacted regardless of where it came from.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "cv_text",
        "cv",
        "resume_text",
        "raw_text",
        "text",
        "name",
        "full_name",
        "first_name",
        "last_name",
        "email",
        "phone",
        "address",
        "postcode",
        "date_of_birth",
        "dob",
        "gender",
        "age",
        "nationality",
        "ethnicity",
        "marital_status",
        "photo",
        "religion",
    }
)

REDACTED = "[redacted]"


def redact(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``payload`` with sensitive values replaced.

    Applied recursively, because personal data is usually one level down inside
    a candidate object rather than at the top of the log call.
    """
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in SENSITIVE_KEYS:
            cleaned[key] = REDACTED
        elif isinstance(value, dict):
            cleaned[key] = redact(value)
        elif isinstance(value, list):
            cleaned[key] = [redact(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


def _redaction_processor(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Structlog processor applying :func:`redact` to every event."""
    return redact(dict(event_dict))


def _request_context_processor(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Attach the current request id and the active model version."""
    event_dict["request_id"] = _request_id.get()
    event_dict.setdefault("model_version", get_settings().model_version)
    return event_dict


def configure_logging() -> None:
    """Configure structlog. Call once at process startup."""
    settings = get_settings()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _request_context_processor,
            # Redaction runs last among the enrichers and immediately before
            # rendering, so anything added by an earlier processor is also
            # covered rather than slipping past.
            _redaction_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, settings.log_level)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for ``name``."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def new_request_id() -> str:
    """Generate a fresh correlation id."""
    return uuid.uuid4().hex


def set_request_id(request_id: str) -> None:
    """Set the correlation id for the current context."""
    _request_id.set(request_id)


def get_request_id() -> str | None:
    """Return the correlation id for the current context, if any."""
    return _request_id.get()


@contextmanager
def request_context(request_id: str | None = None) -> Iterator[str]:
    """Bind a correlation id for the duration of the block.

    Used by the API middleware, and by any background task that should be
    traceable in the same way as a request.
    """
    resolved = request_id or new_request_id()
    token = _request_id.set(resolved)
    try:
        yield resolved
    finally:
        _request_id.reset(token)
