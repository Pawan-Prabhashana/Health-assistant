"""Structured logging configuration.

Logging is configured once at application startup from :class:`Settings`. In
production (``log_json = true``) events are rendered as JSON lines suitable for
log aggregation; in development they are rendered with a colourised,
human-readable console renderer. The standard library ``logging`` module is
routed through structlog so third-party libraries share the same output.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.types import Processor

from sahana_api.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure structlog and the stdlib logging bridge from ``settings``.

    Calling this more than once is safe; the configuration is fully replaced on
    each call, which keeps test isolation simple.
    """
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, libraries) through the same handler so all
    # output shares a single format.
    handler = logging.StreamHandler()
    handler.setFormatter(_stdlib_formatter(settings))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def _stdlib_formatter(settings: Settings) -> logging.Formatter:
    """Build a structlog-backed formatter for stdlib log records."""
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )
    return structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
        ],
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger, optionally namespaced by ``name``."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
