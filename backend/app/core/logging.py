"""Structured (JSON) logging configuration.

One JSON object per log line — easy to ship to any log aggregator. Extra fields
attached via `logger.info(..., extra={...})` (e.g. request metadata) are merged in.
"""

import json
import logging
from contextvars import ContextVar

# Per-request correlation id, set by the request middleware and read by the filter
# below so EVERY log line — not just the access log — carries it. An error logged
# deep inside a turn can then be traced back to the request that caused it (#235).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_RESERVED = set(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime", "taskName"}


class RequestIdFilter(logging.Filter):
    """Stamps every record with the current request id (from the contextvar) unless
    the caller already set one explicitly via `extra=`."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge any custom `extra=` fields.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
