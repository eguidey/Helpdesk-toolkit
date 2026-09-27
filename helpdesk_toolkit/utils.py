"""Shared helpers: status levels, check results, and formatting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from enum import Enum


class Status(str, Enum):
    """Outcome of a single health check."""

    PASS = "PASS"  # noqa: S105 - a status label, not a password
    WARN = "WARN"
    FAIL = "FAIL"
    INFO = "INFO"


STATUS_STYLE = {
    Status.PASS: "bold green",
    Status.WARN: "bold yellow",
    Status.FAIL: "bold red",
    Status.INFO: "bold cyan",
}


@dataclass
class CheckResult:
    """A single diagnostic result that can be shown in a table or exported."""

    name: str
    status: Status
    detail: str
    elapsed_ms: float | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data


def human_bytes(num_bytes: float) -> str:
    """Convert a byte count into a readable string, e.g. 1536 -> '1.5 KB'."""
    if num_bytes < 0:
        raise ValueError("Byte count cannot be negative")
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"  # pragma: no cover - loop always returns


def human_duration(seconds: float) -> str:
    """Convert seconds into a compact duration, e.g. 93784 -> '1d 2h 3m'."""
    delta = timedelta(seconds=int(max(seconds, 0)))
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes = remainder // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def threshold_status(percent: float, warn: float, fail: float) -> Status:
    """Map a usage percentage to PASS / WARN / FAIL using the given thresholds."""
    if percent >= fail:
        return Status.FAIL
    if percent >= warn:
        return Status.WARN
    return Status.PASS
