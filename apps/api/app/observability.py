import contextvars
import json
import logging
import threading
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import sentry_sdk

from app.config import Settings

request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        payload.update(getattr(record, "structured", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_observability(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    if settings.error_tracking_dsn:
        sentry_sdk.init(
            dsn=settings.error_tracking_dsn,
            environment=settings.app_env,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            traces_sample_rate=0.05,
        )


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(event, extra={"structured": {"event": event, **fields}})


class MetricRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: defaultdict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(
            float
        )
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    @staticmethod
    def _key(name: str, labels: dict[str, str]) -> tuple[str, tuple[tuple[str, str], ...]]:
        return name, tuple(sorted(labels.items()))

    def increment(self, name: str, amount: float = 1, **labels: str) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += amount

    def set(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._gauges[self._key(name, labels)] = value

    def observe(self, name: str, value: float, **labels: str) -> None:
        self.increment(f"{name}_count", **labels)
        self.increment(f"{name}_sum", value, **labels)

    @staticmethod
    def _labels(labels: tuple[tuple[str, str], ...]) -> str:
        if not labels:
            return ""
        values = ",".join(
            f'{key}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
            for key, value in labels
        )
        return f"{{{values}}}"

    def render(self, additional: dict[tuple[str, tuple[tuple[str, str], ...]], float]) -> str:
        with self._lock:
            values = {**self._counters, **self._gauges, **additional}
        lines = [
            f"{name}{self._labels(labels)} {value:g}"
            for (name, labels), value in sorted(values.items())
        ]
        return "\n".join(lines) + "\n"


metrics = MetricRegistry()
