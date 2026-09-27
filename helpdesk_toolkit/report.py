"""Build a single self-contained HTML health report to attach to a ticket."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from helpdesk_toolkit import __version__
from helpdesk_toolkit.utils import CheckResult, Status, human_bytes

STATUS_COLORS = {
    Status.PASS: "#1f9d55",
    Status.WARN: "#d69e2e",
    Status.FAIL: "#e53e3e",
    Status.INFO: "#3182ce",
}


def _checks_table(results: list[CheckResult]) -> str:
    rows = []
    for r in results:
        color = STATUS_COLORS[r.status]
        ms = f"{r.elapsed_ms:.0f} ms" if r.elapsed_ms is not None else ""
        rows.append(
            f"<tr><td>{html.escape(r.name)}</td>"
            f'<td><span class="badge" style="background:{color}">{r.status.value}</span></td>'
            f"<td>{html.escape(r.detail)}</td><td>{ms}</td></tr>"
        )
    return ("<table><thead><tr><th>Check</th><th>Status</th><th>Detail</th><th>Time</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def _overall(results: list[CheckResult]) -> Status:
    statuses = {r.status for r in results}
    if Status.FAIL in statuses:
        return Status.FAIL
    if Status.WARN in statuses:
        return Status.WARN
    return Status.PASS


def build_html_report(
    info: dict,
    system_checks: list[CheckResult],
    disk_checks: list[CheckResult],
    network_checks: list[CheckResult],
    network_summary: str,
    processes: list,
    ticket: str | None = None,
) -> str:
    """Return the full HTML document as a string."""
    all_checks = system_checks + disk_checks + network_checks
    overall = _overall(all_checks)
    counts = {s: sum(1 for c in all_checks if c.status is s) for s in (Status.PASS, Status.WARN, Status.FAIL)}
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"Ticket {ticket} - " if ticket else ""

    details = [
        ("Hostname", info["hostname"]),
        ("User", info["user"]),
        ("Operating system", info["os"]),
        ("CPU", f"{info['cpu_model']} ({info['cpu_cores_physical']} cores / {info['cpu_cores_logical']} threads)"),
        ("Memory", human_bytes(info["memory_total"])),
        ("Last boot", info["boot_time"]),
        ("IP addresses", ", ".join(f"{k}: {v}" for k, v in info["ip_addresses"].items()) or "None"),
    ]
    details_html = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in details)

    proc_rows = "".join(
        f"<tr><td>{html.escape(p.name)}</td><td>{p.pid}</td><td>{p.cpu_percent:.1f}%</td>"
        f"<td>{html.escape(human_bytes(p.memory_bytes))}</td></tr>"
        for p in processes
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}Health Report - {html.escape(info['hostname'])}</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; background: #f5f6f8; color: #1a202c; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 24px 16px 48px; }}
  header {{ background: #1a202c; color: #fff; padding: 20px 16px; }}
  header div {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ margin: 0 0 4px; font-size: 1.4rem; }}
  h2 {{ font-size: 1.05rem; margin: 28px 0 8px; }}
  .meta {{ color: #cbd5e0; font-size: .9rem; }}
  .summary {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }}
  .pill {{ padding: 6px 12px; border-radius: 99px; font-weight: 700; color: #fff; font-size: .85rem; }}
  .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 4px 0; overflow-x: auto; }}
  .diagnosis {{ background: #fff; border-left: 4px solid {STATUS_COLORS[overall]}; padding: 12px 16px; border-radius: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
  th, td {{ text-align: left; padding: 8px 14px; border-bottom: 1px solid #edf2f7; vertical-align: top; }}
  thead th {{ background: #f7fafc; font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; color: #4a5568; }}
  tbody tr:last-child td, tbody tr:last-child th {{ border-bottom: 0; }}
  .badge {{ color: #fff; padding: 2px 8px; border-radius: 4px; font-size: .75rem; font-weight: 700; }}
  footer {{ color: #718096; font-size: .8rem; margin-top: 32px; }}
</style></head>
<body>
<header><div>
  <h1>{html.escape(title)}System Health Report</h1>
  <div class="meta">{html.escape(info['hostname'])} &middot; generated {generated}</div>
  <div class="summary">
    <span class="pill" style="background:{STATUS_COLORS[overall]}">Overall: {overall.value}</span>
    <span class="pill" style="background:{STATUS_COLORS[Status.PASS]}">{counts[Status.PASS]} passed</span>
    <span class="pill" style="background:{STATUS_COLORS[Status.WARN]}">{counts[Status.WARN]} warnings</span>
    <span class="pill" style="background:{STATUS_COLORS[Status.FAIL]}">{counts[Status.FAIL]} failed</span>
  </div>
</div></header>
<main>
  <h2>Network diagnosis</h2>
  <div class="diagnosis">{html.escape(network_summary)}</div>
  <h2>Computer details</h2>
  <div class="card"><table><tbody>{details_html}</tbody></table></div>
  <h2>System health</h2>
  <div class="card">{_checks_table(system_checks)}</div>
  <h2>Storage</h2>
  <div class="card">{_checks_table(disk_checks)}</div>
  <h2>Network</h2>
  <div class="card">{_checks_table(network_checks)}</div>
  <h2>Top processes by CPU</h2>
  <div class="card"><table><thead><tr><th>Process</th><th>PID</th><th>CPU</th><th>Memory</th></tr></thead>
  <tbody>{proc_rows}</tbody></table></div>
  <footer>Generated by Help Desk Toolkit v{__version__}</footer>
</main>
</body></html>
"""


def save_report(content: str, output: str | Path | None, hostname: str) -> Path:
    """Write the report, defaulting to health-report_<host>_<timestamp>.html."""
    if output is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_host = "".join(c for c in hostname if c.isalnum() or c in "-_") or "host"
        output = f"health-report_{safe_host}_{stamp}.html"
    path = Path(output)
    path.write_text(content, encoding="utf-8")
    return path
