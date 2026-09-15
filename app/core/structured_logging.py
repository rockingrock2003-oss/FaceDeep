import json
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id
        if hasattr(record, "method"):
            log_entry["method"] = record.method
        if hasattr(record, "endpoint"):
            log_entry["endpoint"] = record.endpoint
        if hasattr(record, "status_code"):
            log_entry["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        parts = [ts, record.levelname.ljust(8), record.name, record.getMessage()]
        if record.exc_info and record.exc_info[0]:
            parts.append(self.formatException(record.exc_info))
        return " | ".join(parts)


def setup_logging(environment: str = "production", json_output: bool = True):
    root = logging.getLogger("facedeep")
    root.setLevel(logging.INFO)

    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if json_output and environment != "development":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root.addHandler(handler)

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
