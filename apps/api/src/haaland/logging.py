"""structlog setup. Applies the deterministic redaction pre-filter to every
record before emission — our own logs are a leak vector too (docs/09)."""

from __future__ import annotations

import logging
import sys

import structlog

from haaland.redaction.prefilter import redact_text


def _redact_processor(logger, method_name, event_dict):
    for key in ("event", "message"):
        if key in event_dict and isinstance(event_dict[key], str):
            event_dict[key] = redact_text(event_dict[key])
    # Never log evidence content or vault contents — only references.
    event_dict.pop("evidence_content", None)
    event_dict.pop("vault_contents", None)
    return event_dict


def configure_logging(*, json: bool = True, level: int = logging.INFO) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_processor,
            structlog.processors.StackInfoRenderer(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
