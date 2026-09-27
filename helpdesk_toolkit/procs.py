"""Find the programs slowing a computer down."""

from __future__ import annotations

import time
from dataclasses import dataclass

import psutil


@dataclass
class ProcessInfo:
    pid: int
    name: str
    user: str
    cpu_percent: float
    memory_bytes: int
    memory_percent: float


def top_processes(limit: int = 10, sort_by: str = "cpu", sample_seconds: float = 1.0) -> list[ProcessInfo]:
    """Return the heaviest processes by CPU or memory.

    CPU % needs two measurements, so we prime every process, wait, then read again.
    """
    if sort_by not in {"cpu", "memory"}:
        raise ValueError("sort_by must be 'cpu' or 'memory'")

    processes = list(psutil.process_iter(["pid", "name", "username"]))
    for proc in processes:
        try:
            proc.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    time.sleep(sample_seconds)
    cpu_count = psutil.cpu_count() or 1

    results: list[ProcessInfo] = []
    for proc in processes:
        try:
            with proc.oneshot():
                cpu = proc.cpu_percent(None) / cpu_count  # normalise to 0-100% of the whole machine
                mem = proc.memory_info().rss
                mem_pct = proc.memory_percent()
            results.append(
                ProcessInfo(
                    pid=proc.info["pid"],
                    name=proc.info["name"] or "?",
                    user=(proc.info.get("username") or "").split("\\")[-1],
                    cpu_percent=round(cpu, 1),
                    memory_bytes=mem,
                    memory_percent=round(mem_pct, 1),
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    key = (lambda p: p.cpu_percent) if sort_by == "cpu" else (lambda p: p.memory_bytes)
    results.sort(key=key, reverse=True)
    return results[:limit]
