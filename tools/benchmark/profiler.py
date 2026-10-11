from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


@dataclass
class ResourceSummary:
    cpu_average_percent: float
    cpu_peak_percent: float
    ram_baseline_mb: float
    ram_peak_mb: float
    ram_delta_mb: float
    gpu_available: bool
    gpu_device_name: str | None = None
    gpu_memory_allocated_mb: float | None = None
    gpu_memory_peak_mb: float | None = None
    gpu_total_vram_mb: float | None = None
    samples_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_average_percent": round(self.cpu_average_percent, 2),
            "cpu_peak_percent": round(self.cpu_peak_percent, 2),
            "ram_baseline_mb": round(self.ram_baseline_mb, 2),
            "ram_peak_mb": round(self.ram_peak_mb, 2),
            "ram_delta_mb": round(self.ram_delta_mb, 2),
            "gpu_available": self.gpu_available,
            "gpu_device_name": self.gpu_device_name,
            "gpu_memory_allocated_mb": round(self.gpu_memory_allocated_mb, 2)
            if self.gpu_memory_allocated_mb is not None
            else None,
            "gpu_memory_peak_mb": round(self.gpu_memory_peak_mb, 2)
            if self.gpu_memory_peak_mb is not None
            else None,
            "gpu_total_vram_mb": round(self.gpu_total_vram_mb, 2)
            if self.gpu_total_vram_mb is not None
            else None,
            "samples_count": self.samples_count,
        }


def _get_process_rss_mb() -> float:
    """Get current process RSS in MB."""
    if _HAS_PSUTIL:
        try:
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:
            pass

    # Linux /proc fallback
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return float(parts[1]) / 1024.0  # kB to MB
    except Exception:
        pass

    return 0.0


def _query_gpu_info() -> tuple[bool, str | None, float | None, float | None, float | None]:
    """Query PyTorch or system for GPU / VRAM availability."""
    try:
        import torch
        if torch.cuda.is_available():
            dev_idx = torch.cuda.current_device()
            dev_name = torch.cuda.get_device_name(dev_idx)
            alloc_mb = torch.cuda.memory_allocated(dev_idx) / (1024 * 1024)
            peak_mb = torch.cuda.max_memory_allocated(dev_idx) / (1024 * 1024)
            total_mb = torch.cuda.get_device_properties(dev_idx).total_memory / (1024 * 1024)
            return True, dev_name, alloc_mb, peak_mb, total_mb
    except Exception:
        pass

    return False, None, None, None, None


class ResourceProfiler:
    """Monitors CPU, RAM, and GPU utilization during benchmark runs."""

    def __init__(self, sample_interval_sec: float = 0.1):
        self.sample_interval = sample_interval_sec
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._cpu_samples: list[float] = []
        self._ram_samples: list[float] = []
        self._baseline_ram_mb: float = 0.0
        self._process = psutil.Process() if _HAS_PSUTIL else None
        self._num_cpus = (psutil.cpu_count() or 1) if _HAS_PSUTIL else 1

    def start(self) -> None:
        """Start background profiling thread."""
        self._stop_event.clear()
        self._cpu_samples.clear()
        self._ram_samples.clear()
        self._baseline_ram_mb = _get_process_rss_mb()

        # Prime psutil CPU calculation
        if self._process:
            try:
                self._process.cpu_percent(interval=None)
            except Exception:
                pass

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._process:
                try:
                    raw_cpu = self._process.cpu_percent(interval=None)
                    normalized_cpu = min(100.0, max(0.0, raw_cpu / self._num_cpus))
                    self._cpu_samples.append(normalized_cpu)
                except Exception:
                    pass

            rss = _get_process_rss_mb()
            if rss > 0:
                self._ram_samples.append(rss)

            time.sleep(self.sample_interval)

    def stop(self) -> ResourceSummary:
        """Stop profiling and return aggregated resource metrics."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        # Final sample
        final_rss = _get_process_rss_mb()
        if final_rss > 0:
            self._ram_samples.append(final_rss)

        avg_cpu = sum(self._cpu_samples) / len(self._cpu_samples) if self._cpu_samples else 0.0
        peak_cpu = max(self._cpu_samples) if self._cpu_samples else 0.0

        baseline_ram = self._baseline_ram_mb
        peak_ram = max(self._ram_samples) if self._ram_samples else baseline_ram
        delta_ram = max(0.0, peak_ram - baseline_ram)

        gpu_avail, gpu_name, gpu_alloc, gpu_peak, gpu_total = _query_gpu_info()

        return ResourceSummary(
            cpu_average_percent=avg_cpu,
            cpu_peak_percent=peak_cpu,
            ram_baseline_mb=baseline_ram,
            ram_peak_mb=peak_ram,
            ram_delta_mb=delta_ram,
            gpu_available=gpu_avail,
            gpu_device_name=gpu_name,
            gpu_memory_allocated_mb=gpu_alloc,
            gpu_memory_peak_mb=gpu_peak,
            gpu_total_vram_mb=gpu_total,
            samples_count=len(self._cpu_samples),
        )
