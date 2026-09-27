"""Collect a snapshot of the computer's hardware, OS and resource usage."""

from __future__ import annotations

import getpass
import platform
import socket
import time
from datetime import datetime

import psutil

from helpdesk_toolkit.utils import CheckResult, Status, human_bytes, human_duration, threshold_status


def _cpu_model() -> str:
    """Best-effort CPU model name across Windows, macOS and Linux."""
    model = platform.processor()
    if model and model not in {"x86_64", "AMD64", "arm", "i386"}:
        return model
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return model or platform.machine() or "Unknown"


def _ipv4_addresses() -> dict[str, str]:
    """Return {interface: IPv4 address}, skipping loopback."""
    addresses: dict[str, str] = {}
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                addresses[iface] = addr.address
    return addresses


def collect_system_info(cpu_sample_seconds: float = 0.5) -> dict:
    """Gather system details into a plain dictionary (easy to print or export as JSON)."""
    uname = platform.uname()
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    boot_time = psutil.boot_time()

    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - getuser can fail in containers/services
        user = "unknown"

    battery = None
    try:
        batt = psutil.sensors_battery()
        if batt is not None:
            battery = {"percent": round(batt.percent), "plugged_in": bool(batt.power_plugged)}
    except (AttributeError, NotImplementedError):
        battery = None

    return {
        "hostname": socket.gethostname(),
        "user": user,
        "os": f"{uname.system} {uname.release}",
        "os_version": uname.version,
        "architecture": uname.machine,
        "cpu_model": _cpu_model(),
        "cpu_cores_physical": psutil.cpu_count(logical=False) or 0,
        "cpu_cores_logical": psutil.cpu_count(logical=True) or 0,
        "cpu_percent": psutil.cpu_percent(interval=cpu_sample_seconds),
        "memory_total": memory.total,
        "memory_used": memory.total - memory.available,
        "memory_percent": memory.percent,
        "swap_percent": swap.percent,
        "boot_time": datetime.fromtimestamp(boot_time).isoformat(timespec="seconds"),
        "uptime_seconds": int(time.time() - boot_time),
        "ip_addresses": _ipv4_addresses(),
        "battery": battery,
        "python_version": platform.python_version(),
    }


def evaluate_system(info: dict) -> list[CheckResult]:
    """Turn raw system info into help-desk style health checks."""
    results = [
        CheckResult(
            "CPU load",
            threshold_status(info["cpu_percent"], warn=80, fail=95),
            f"{info['cpu_percent']:.0f}% in use",
        ),
        CheckResult(
            "Memory",
            threshold_status(info["memory_percent"], warn=85, fail=95),
            f"{human_bytes(info['memory_used'])} of {human_bytes(info['memory_total'])} "
            f"({info['memory_percent']:.0f}%)",
        ),
    ]

    uptime_days = info["uptime_seconds"] / 86400
    uptime_status = Status.WARN if uptime_days >= 14 else Status.PASS
    uptime_note = " - a restart is recommended" if uptime_status is Status.WARN else ""
    results.append(
        CheckResult("Uptime", uptime_status, human_duration(info["uptime_seconds"]) + uptime_note)
    )

    battery = info.get("battery")
    if battery:
        batt_status = Status.WARN if battery["percent"] < 20 and not battery["plugged_in"] else Status.PASS
        plugged = "plugged in" if battery["plugged_in"] else "on battery"
        results.append(CheckResult("Battery", batt_status, f"{battery['percent']}% ({plugged})"))

    if not info["ip_addresses"]:
        results.append(CheckResult("Network adapter", Status.FAIL, "No IPv4 address assigned"))

    return results
