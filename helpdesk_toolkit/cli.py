"""Command-line interface: ``helpdesk <command> [options]``."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import urllib.error
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from helpdesk_toolkit import __version__, diskcheck, netcheck, onboard, procs, pwcheck, report, sysinfo
from helpdesk_toolkit.utils import STATUS_STYLE, CheckResult, Status, human_bytes

console = Console()


# --------------------------------------------------------------------------- helpers
def print_checks(title: str, results: list[CheckResult]) -> None:
    table = Table(title=title, title_justify="left", header_style="bold")
    table.add_column("Check")
    table.add_column("Status", justify="center")
    table.add_column("Detail")
    table.add_column("Time", justify="right")
    for r in results:
        ms = f"{r.elapsed_ms:.0f} ms" if r.elapsed_ms is not None else ""
        table.add_row(r.name, f"[{STATUS_STYLE[r.status]}]{r.status.value}[/]", r.detail, ms)
    console.print(table)


def exit_code_for(results: list[CheckResult]) -> int:
    """0 = all good, 1 = warnings, 2 = failures. Handy for scripts and monitoring."""
    statuses = {r.status for r in results}
    if Status.FAIL in statuses:
        return 2
    if Status.WARN in statuses:
        return 1
    return 0


# --------------------------------------------------------------------------- commands
def cmd_sysinfo(args: argparse.Namespace) -> int:
    with console.status("Collecting system information..."):
        info = sysinfo.collect_system_info()
        checks = sysinfo.evaluate_system(info)

    if args.json:
        print(json.dumps({"info": info, "checks": [c.to_dict() for c in checks]}, indent=2))
        return exit_code_for(checks)

    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold cyan")
    details.add_column()
    details.add_row("Hostname", info["hostname"])
    details.add_row("User", info["user"])
    details.add_row("OS", f"{info['os']} ({info['architecture']})")
    details.add_row("CPU", f"{info['cpu_model']} - {info['cpu_cores_physical']} cores / {info['cpu_cores_logical']} threads")
    details.add_row("Memory", human_bytes(info["memory_total"]))
    details.add_row("Last boot", info["boot_time"])
    ips = ", ".join(f"{k}: {v}" for k, v in info["ip_addresses"].items()) or "none"
    details.add_row("IP addresses", ips)
    console.print(Panel(details, title="System information", title_align="left"))
    print_checks("Health checks", checks)
    return exit_code_for(checks)


def cmd_netcheck(args: argparse.Namespace) -> int:
    with console.status("Running network diagnostics..."):
        results = netcheck.run_network_checks(args.host)
        summary = netcheck.diagnose(results)

    if args.json:
        print(json.dumps({"checks": [r.to_dict() for r in results], "diagnosis": summary}, indent=2))
        return exit_code_for(results)

    print_checks("Network diagnostics", results)
    style = STATUS_STYLE[Status.PASS] if exit_code_for(results) == 0 else STATUS_STYLE[Status.WARN]
    console.print(Panel(summary, title="Diagnosis", title_align="left", border_style=style))
    return exit_code_for(results)


def cmd_diskcheck(args: argparse.Namespace) -> int:
    results = diskcheck.check_disks(args.warn, args.fail)
    print_checks("Drive usage", results)

    if args.path:
        root = Path(args.path).expanduser()
        if not root.is_dir():
            console.print(f"[red]Folder not found:[/] {root}")
            return 2
        with console.status(f"Scanning {root} ..."):
            largest, skipped = diskcheck.find_largest_files(root, args.top)
            folders = diskcheck.folder_sizes(root, args.top)

        table = Table(title=f"Largest files in {root}", title_justify="left", header_style="bold")
        table.add_column("Size", justify="right", style="bold")
        table.add_column("File")
        for entry in largest:
            table.add_row(human_bytes(entry.size), entry.path)
        console.print(table)

        table = Table(title=f"Largest folders in {root}", title_justify="left", header_style="bold")
        table.add_column("Size", justify="right", style="bold")
        table.add_column("Folder")
        for entry in folders:
            table.add_row(human_bytes(entry.size), entry.path)
        console.print(table)
        if skipped:
            console.print(f"[dim]{skipped} file(s) skipped (no permission).[/]")

    return exit_code_for(results)


def cmd_procs(args: argparse.Namespace) -> int:
    with console.status("Measuring processes..."):
        top = procs.top_processes(limit=args.top, sort_by=args.sort)

    table = Table(title=f"Top {args.top} processes by {args.sort}", title_justify="left", header_style="bold")
    table.add_column("PID", justify="right")
    table.add_column("Name")
    table.add_column("User")
    table.add_column("CPU %", justify="right")
    table.add_column("Memory", justify="right")
    for p in top:
        cpu_style = "red" if p.cpu_percent >= 50 else ""
        table.add_row(str(p.pid), p.name, p.user, f"[{cpu_style}]{p.cpu_percent:.1f}[/]" if cpu_style else f"{p.cpu_percent:.1f}",
                      human_bytes(p.memory_bytes))
    console.print(table)
    return 0


def cmd_pwcheck(args: argparse.Namespace) -> int:
    password = getpass.getpass("Password to check (input hidden): ")
    if not password:
        console.print("[red]No password entered.[/]")
        return 2

    result = pwcheck.check_policy(password, min_length=args.min_length)
    status = Status.PASS if result.passed else Status.FAIL
    lines = [f"Policy: [{STATUS_STYLE[status]}]{status.value}[/]",
             f"Strength: {result.strength} (~{result.entropy_bits:.0f} bits)"]
    lines += [f"  - {issue}" for issue in result.issues]

    breached = 0
    if not args.offline:
        try:
            breached = pwcheck.breach_count(password)
            if breached:
                lines.append(f"[bold red]Found in {breached:,} known data breaches - do not use this password.[/]")
                status = Status.FAIL
            else:
                lines.append("[green]Not found in known data breaches.[/]")
        except (urllib.error.URLError, OSError) as exc:
            lines.append(f"[yellow]Breach check skipped (offline?): {exc}[/]")
    console.print(Panel("\n".join(lines), title="Password check", title_align="left"))
    return 0 if status is Status.PASS else 2


def cmd_onboard(args: argparse.Namespace) -> int:
    try:
        rows = onboard.load_new_hires(args.csv)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Could not read {args.csv}:[/] {exc}")
        return 2

    existing = set()
    if args.existing:
        existing = {line.strip().lower() for line in Path(args.existing).read_text(encoding="utf-8").splitlines() if line.strip()}

    accounts = onboard.build_accounts(rows, domain=args.domain, existing=existing)
    onboard.write_accounts(accounts, args.output)

    table = Table(title=f"{len(accounts)} account(s) prepared", title_justify="left", header_style="bold")
    for col in ("Name", "Department", "Username", "Email"):
        table.add_column(col)
    for a in accounts:
        table.add_row(f"{a.first_name} {a.last_name}", a.department, a.username, a.email)
    console.print(table)
    console.print(f"Saved to [bold]{args.output}[/] (contains temporary passwords - store it securely and delete after import).")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    with console.status("Building health report (this takes a few seconds)..."):
        info = sysinfo.collect_system_info()
        system_checks = sysinfo.evaluate_system(info)
        disk_checks = diskcheck.check_disks()
        network_checks = netcheck.run_network_checks()
        summary = netcheck.diagnose(network_checks)
        top = procs.top_processes(limit=8)
        html_doc = report.build_html_report(info, system_checks, disk_checks, network_checks, summary, top, args.ticket)
        path = report.save_report(html_doc, args.output, info["hostname"])

    all_checks = system_checks + disk_checks + network_checks
    console.print(f"[green]Report saved:[/] {path.resolve()}")
    return exit_code_for(all_checks)


# --------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="helpdesk",
        description="Help Desk Toolkit - fast diagnostics and automation for everyday IT support.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("sysinfo", help="Computer specs and health (CPU, memory, uptime, battery)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_sysinfo)

    p = sub.add_parser("netcheck", help='Layered network diagnostics - answers "is it the network?"')
    p.add_argument("--host", action="append", metavar="HOST[:PORT]",
                   help="Extra host to test, e.g. fileserver or mail.company.com:443 (repeatable)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.set_defaults(func=cmd_netcheck)

    p = sub.add_parser("diskcheck", help="Drive usage, plus largest files/folders in a path")
    p.add_argument("path", nargs="?", help="Folder to scan for large files (optional)")
    p.add_argument("--top", type=int, default=10, help="How many results to show (default 10)")
    p.add_argument("--warn", type=float, default=85, help="Warn at this %% used (default 85)")
    p.add_argument("--fail", type=float, default=95, help="Fail at this %% used (default 95)")
    p.set_defaults(func=cmd_diskcheck)

    p = sub.add_parser("procs", help="Programs using the most CPU or memory")
    p.add_argument("--sort", choices=["cpu", "memory"], default="cpu")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_procs)

    p = sub.add_parser("pwcheck", help="Check a password against policy and known breaches")
    p.add_argument("--min-length", type=int, default=12)
    p.add_argument("--offline", action="store_true", help="Skip the online breach lookup")
    p.set_defaults(func=cmd_pwcheck)

    p = sub.add_parser("onboard", help="Generate usernames, emails and temp passwords from a new-hire CSV")
    p.add_argument("csv", help="CSV with first_name,last_name,department[,title]")
    p.add_argument("--domain", required=True, help="Email domain, e.g. company.com")
    p.add_argument("--existing", help="Text file of usernames already in use (one per line)")
    p.add_argument("-o", "--output", default="new_accounts.csv", help="Output CSV (default new_accounts.csv)")
    p.set_defaults(func=cmd_onboard)

    p = sub.add_parser("report", help="Full HTML health report to attach to a ticket")
    p.add_argument("--ticket", help="Ticket number to show in the report title")
    p.add_argument("-o", "--output", help="Output file (default health-report_<host>_<time>.html)")
    p.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
