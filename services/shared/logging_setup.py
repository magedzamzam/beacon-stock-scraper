"""Structured JSON logger shared across services."""
import logging
import sys
import structlog


def configure_logging(service_name: str, level: str = "INFO") -> structlog.BoundLogger:
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper())
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
    )
    return structlog.get_logger(service=service_name)
