"""Disk space checks and a "what's eating my space?" finder."""

from __future__ import annotations

import heapq
import os
from dataclasses import dataclass
from pathlib import Path

import psutil

from helpdesk_toolkit.utils import CheckResult, human_bytes, threshold_status

SKIP_FSTYPES = {"squashfs", "tmpfs", "devtmpfs", "overlay", "proc", "sysfs", "cdfs", "udf"}


@dataclass
class FileEntry:
    path: str
    size: int


def check_disks(warn_percent: float = 85, fail_percent: float = 95) -> list[CheckResult]:
    """Report usage for every real drive/partition."""
    results: list[CheckResult] = []
    seen: set[str] = set()
    for part in psutil.disk_partitions(all=False):
        if part.fstype.lower() in SKIP_FSTYPES or part.mountpoint in seen:
            continue
        seen.add(part.mountpoint)
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue  # e.g. an empty card reader on Windows
        status = threshold_status(usage.percent, warn_percent, fail_percent)
        detail = (f"{human_bytes(usage.free)} free of {human_bytes(usage.total)} "
                  f"({usage.percent:.0f}% used)")
        results.append(CheckResult(f"Drive {part.mountpoint}", status, detail))
    return results


def find_largest_files(root: str | Path, top_n: int = 10, min_size: int = 0) -> tuple[list[FileEntry], int]:
    """Walk a folder and return the N largest files plus the number of unreadable items.

    Uses a small heap so memory stays low even when scanning millions of files.
    """
    heap: list[tuple[int, str]] = []
    skipped = 0

    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _err: None):
        # Don't follow symlinked folders - avoids loops and double counting.
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            try:
                if os.path.islink(full_path):
                    continue
                size = os.path.getsize(full_path)
            except OSError:
                skipped += 1
                continue
            if size < min_size:
                continue
            if len(heap) < top_n:
                heapq.heappush(heap, (size, full_path))
            elif size > heap[0][0]:
                heapq.heapreplace(heap, (size, full_path))

    largest = [FileEntry(path, size) for size, path in sorted(heap, reverse=True)]
    return largest, skipped


def folder_sizes(root: str | Path, top_n: int = 10) -> list[FileEntry]:
    """Total size of each direct sub-folder of ``root`` - great for finding bloated folders."""
    totals: list[FileEntry] = []
    try:
        entries = list(os.scandir(root))
    except OSError:
        return totals
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        total = 0
        for dirpath, _dirnames, filenames in os.walk(entry.path, onerror=lambda _err: None):
            for filename in filenames:
                try:
                    fp = os.path.join(dirpath, filename)
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
                except OSError:
                    continue
        totals.append(FileEntry(entry.path, total))
    totals.sort(key=lambda item: item.size, reverse=True)
    return totals[:top_n]
