from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock


@dataclass
class RequestMetrics:
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    total_requests: int = 0
    status_counts: Counter[str] = field(default_factory=Counter)
    path_counts: Counter[str] = field(default_factory=Counter)
    last_request_at: datetime | None = None
    last_status_code: int | None = None
    last_path: str | None = None
    last_duration_ms: float | None = None
    _lock: Lock = field(default_factory=Lock)

    def record(self, *, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self.total_requests += 1
            self.status_counts[str(status_code)] += 1
            self.path_counts[path] += 1
            self.last_request_at = datetime.now(tz=UTC)
            self.last_status_code = status_code
            self.last_path = path
            self.last_duration_ms = round(duration_ms, 3)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "started_at": self.started_at.isoformat(),
                "total_requests": self.total_requests,
                "status_counts": dict(self.status_counts),
                "path_counts": dict(self.path_counts),
                "last_request_at": self.last_request_at.isoformat() if self.last_request_at else None,
                "last_status_code": self.last_status_code,
                "last_path": self.last_path,
                "last_duration_ms": self.last_duration_ms,
            }
