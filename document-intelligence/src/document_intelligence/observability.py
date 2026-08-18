from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "structured_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )


def configure_json_logging() -> logging.Logger:
    logger = logging.getLogger("document_intelligence.api")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


@dataclass(frozen=True)
class MetricSnapshot:
    requests_total: dict[tuple[str, str, int], int]
    request_duration_seconds_sum: dict[tuple[str, str], float]
    request_duration_seconds_count: dict[tuple[str, str], int]
    inflight_requests: int


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self._inflight = 0
        self._started_at = time.monotonic()

    def request_started(self) -> None:
        with self._lock:
            self._inflight += 1

    def request_finished(
        self, method: str, path_class: str, status: int, duration_s: float
    ) -> None:
        with self._lock:
            self._inflight = max(0, self._inflight - 1)
            self._requests[(method, path_class, status)] += 1
            self._duration_sum[(method, path_class)] += max(0.0, duration_s)
            self._duration_count[(method, path_class)] += 1

    def snapshot(self) -> MetricSnapshot:
        with self._lock:
            return MetricSnapshot(
                requests_total=dict(self._requests),
                request_duration_seconds_sum=dict(self._duration_sum),
                request_duration_seconds_count=dict(self._duration_count),
                inflight_requests=self._inflight,
            )

    @staticmethod
    def _label(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def render_prometheus(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP document_intelligence_info Static service information.",
            "# TYPE document_intelligence_info gauge",
            'document_intelligence_info{service="document-intelligence"} 1',
            "# HELP document_intelligence_uptime_seconds Process uptime.",
            "# TYPE document_intelligence_uptime_seconds gauge",
            f"document_intelligence_uptime_seconds {time.monotonic() - self._started_at:.6f}",
            "# HELP document_intelligence_http_inflight_requests In-flight HTTP requests.",
            "# TYPE document_intelligence_http_inflight_requests gauge",
            f"document_intelligence_http_inflight_requests {snapshot.inflight_requests}",
            "# HELP document_intelligence_http_requests_total Completed HTTP requests.",
            "# TYPE document_intelligence_http_requests_total counter",
        ]
        for (method, path, status), value in sorted(snapshot.requests_total.items()):
            lines.append(
                "document_intelligence_http_requests_total"
                f'{{method="{self._label(method)}",path="{self._label(path)}",'
                f'status="{status}"}} {value}'
            )
        lines.extend(
            [
                "# HELP document_intelligence_http_request_duration_seconds_sum "
                "Request duration sum.",
                "# TYPE document_intelligence_http_request_duration_seconds_sum counter",
            ]
        )
        for (method, path), value in sorted(snapshot.request_duration_seconds_sum.items()):
            lines.append(
                "document_intelligence_http_request_duration_seconds_sum"
                f'{{method="{self._label(method)}",path="{self._label(path)}"}} {value:.9f}'
            )
        lines.extend(
            [
                "# HELP document_intelligence_http_request_duration_seconds_count "
                "Request duration count.",
                "# TYPE document_intelligence_http_request_duration_seconds_count counter",
            ]
        )
        for (method, path), value in sorted(snapshot.request_duration_seconds_count.items()):
            lines.append(
                "document_intelligence_http_request_duration_seconds_count"
                f'{{method="{self._label(method)}",path="{self._label(path)}"}} {value}'
            )
        return "\n".join(lines) + "\n"
