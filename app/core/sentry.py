import logging
import os

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

logger = logging.getLogger("facedeep.sentry")

SENTRY_DSN = os.getenv("SENTRY_DSN", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
TRACES_SAMPLE_RATE = 0.1 if ENVIRONMENT == "production" else 1.0


def init_sentry():
    if not SENTRY_DSN:
        logger.info("Sentry DSN not configured, skipping initialization")
        return

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=ENVIRONMENT,
        traces_sample_rate=TRACES_SAMPLE_RATE,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        attach_stacktrace=True,
        send_default_pii=False,
        before_send=_filter_sensitive_data,
    )
    logger.info(f"Sentry initialized for environment: {ENVIRONMENT}")


def _filter_sensitive_data(event):
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        for key in ["authorization", "x-api-key", "cookie"]:
            if key in headers:
                headers[key] = "[FILTERED]"

    if "exception" in event:
        for exc in event["exception"].get("values", []):
            if "value" in exc:
                exc["value"] = _redact_secrets(str(exc["value"]))

    return event


def _redact_secrets(text: str) -> str:
    import re
    text = re.sub(r'fd_[A-Za-z0-9]{20,}', 'fd_[REDACTED]', text)
    text = re.sub(r'Bearer\s+[A-Za-z0-9._-]+', 'Bearer [REDACTED]', text)
    return text


def capture_exception(error: Exception, context: dict | None = None):
    if SENTRY_DSN:
        with sentry_sdk.push_scope() as scope:
            if context:
                for key, value in context.items():
                    scope.set_extra(key, value)
            sentry_sdk.capture_exception(error)


def capture_message(message: str, level: str = "info", context: dict | None = None):
    if SENTRY_DSN:
        with sentry_sdk.push_scope() as scope:
            if context:
                for key, value in context.items():
                    scope.set_extra(key, value)
            sentry_sdk.capture_message(message, level=level)
