import logging
import threading
import time
from collections import defaultdict

logger = logging.getLogger("facedeep.metrics")


class MetricsCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()

    def inc_counter(self, name: str, value: int = 1):
        with self._lock:
            self._counters[name] += value

    def set_gauge(self, name: str, value: float):
        with self._lock:
            self._gauges[name] = value

    def observe_histogram(self, name: str, value: float):
        with self._lock:
            self._histograms[name].append(value)
            if len(self._histograms[name]) > 10000:
                self._histograms[name] = self._histograms[name][-5000:]

    def get_counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> float:
        return self._gauges.get(name, 0.0)

    def _percentile(self, values: list[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * p / 100)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def get_histogram_stats(self, name: str) -> dict:
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "p50": 0, "p95": 0, "p99": 0, "avg": 0}
        return {
            "count": len(values),
            "p50": round(self._percentile(values, 50), 2),
            "p95": round(self._percentile(values, 95), 2),
            "p99": round(self._percentile(values, 99), 2),
            "avg": round(sum(values) / len(values), 2),
        }

    def to_prometheus(self) -> str:
        lines = []
        for name, value in sorted(self._counters.items()):
            lines.append(f"facedeep_{name}_total {value}")
        for name, value in sorted(self._gauges.items()):
            lines.append(f"facedeep_{name} {value}")
        for name in sorted(self._histograms.keys()):
            stats = self.get_histogram_stats(name)
            lines.append(f"facedeep_{name}_count {stats['count']}")
            lines.append(f"facedeep_{name}_p50 {stats['p50']}")
            lines.append(f"facedeep_{name}_p95 {stats['p95']}")
            lines.append(f"facedeep_{name}_p99 {stats['p99']}")
        uptime = round(time.time() - self._start_time, 2)
        lines.append(f"facedeep_uptime_seconds {uptime}")
        return "\n".join(lines) + "\n"

    def reset(self):
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._start_time = time.time()


metrics = MetricsCollector()
