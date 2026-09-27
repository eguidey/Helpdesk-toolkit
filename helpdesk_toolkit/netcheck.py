"""Answer the classic ticket: "Is it the network?"

Runs a layered set of checks (adapter -> gateway -> internet -> DNS -> web)
and then explains in plain English where the problem most likely is.
"""

from __future__ import annotations

import platform
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request

from helpdesk_toolkit.utils import CheckResult, Status

DEFAULT_DNS_NAMES = ("www.google.com", "www.microsoft.com")
PUBLIC_IP = "1.1.1.1"
WEB_URL = "https://www.google.com/generate_204"


def get_local_ip() -> str | None:
    """Find the IP address the computer would use to reach the internet.

    Connecting a UDP socket sends no packets; it only asks the OS to pick a route.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((PUBLIC_IP, 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def parse_default_gateway(output: str, system: str) -> str | None:
    """Pull the default gateway IP out of the OS routing-table output."""
    if system == "Windows":
        match = re.search(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", output, re.MULTILINE)
    elif system == "Darwin":
        match = re.search(r"gateway:\s*(\d+\.\d+\.\d+\.\d+)", output)
    else:
        match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", output)
    return match.group(1) if match else None


def get_default_gateway() -> str | None:
    """Look up the default gateway using the operating system's own tools."""
    system = platform.system()
    commands = {
        "Windows": ["route", "print", "-4"],
        "Darwin": ["route", "-n", "get", "default"],
    }
    command = commands.get(system, ["ip", "route", "show", "default"])
    try:
        output = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_default_gateway(output, system)


def ping(host: str, timeout_s: int = 2) -> tuple[bool, float | None]:
    """Ping a host once. Returns (reachable, round-trip milliseconds)."""
    if platform.system() == "Windows":
        command = ["ping", "-n", "1", "-w", str(timeout_s * 1000), host]
    else:
        command = ["ping", "-c", "1", "-W", str(timeout_s), host]
    start = time.perf_counter()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s + 2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False, None
    elapsed = (time.perf_counter() - start) * 1000
    # Windows returns 0 even for "Destination host unreachable", so also check for a TTL.
    ok = result.returncode == 0 and "ttl=" in result.stdout.lower()
    return ok, (round(elapsed, 1) if ok else None)


def tcp_check(host: str, port: int, timeout_s: float = 3) -> tuple[bool, float | None]:
    """Try to open a TCP connection. Works even where ICMP ping is blocked."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True, round((time.perf_counter() - start) * 1000, 1)
    except OSError:
        return False, None


def dns_lookup(name: str) -> tuple[bool, str, float | None]:
    """Resolve a hostname. Returns (ok, address-or-error, milliseconds)."""
    start = time.perf_counter()
    try:
        address = socket.gethostbyname(name)
        return True, address, round((time.perf_counter() - start) * 1000, 1)
    except OSError as exc:
        return False, str(exc), None


def http_check(url: str = WEB_URL, timeout_s: float = 5) -> tuple[bool, str, float | None]:
    """Fetch a URL and report the HTTP status."""
    if not url.lower().startswith(("https://", "http://")):
        raise ValueError("Only http(s) URLs are allowed")
    start = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": "helpdesk-toolkit"})  # noqa: S310 - scheme validated above
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - scheme validated above
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            return 200 <= response.status < 400, f"HTTP {response.status}", elapsed
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}", None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return False, str(reason), None


def run_network_checks(extra_hosts: list[str] | None = None) -> list[CheckResult]:
    """Run every layer of checks, from the local adapter out to the web."""
    results: list[CheckResult] = []

    local_ip = get_local_ip()
    if local_ip:
        status = Status.WARN if local_ip.startswith("169.254.") else Status.PASS
        note = " (APIPA - DHCP server not reachable)" if status is Status.WARN else ""
        results.append(CheckResult("Local IP", status, local_ip + note))
    else:
        results.append(CheckResult("Local IP", Status.FAIL, "No route to the internet - adapter down or unplugged"))

    gateway = get_default_gateway()
    if gateway:
        ok, ms = ping(gateway)
        results.append(
            CheckResult("Gateway", Status.PASS if ok else Status.WARN,
                        f"{gateway} {'reachable' if ok else 'did not reply to ping (may be blocked)'}", ms)
        )
    else:
        results.append(CheckResult("Gateway", Status.FAIL, "No default gateway configured"))

    ok, ms = tcp_check(PUBLIC_IP, 443)
    results.append(
        CheckResult("Internet", Status.PASS if ok else Status.FAIL,
                    f"{PUBLIC_IP}:443 {'reachable' if ok else 'unreachable'}", ms)
    )

    for name in DEFAULT_DNS_NAMES:
        ok, detail, ms = dns_lookup(name)
        results.append(CheckResult(f"DNS {name}", Status.PASS if ok else Status.FAIL, detail, ms))

    ok, detail, ms = http_check()
    results.append(CheckResult("Web (HTTPS)", Status.PASS if ok else Status.FAIL, detail, ms))

    for host in extra_hosts or []:
        host_name, _, port = host.partition(":")
        if port:
            ok, ms = tcp_check(host_name, int(port))
            results.append(CheckResult(f"Host {host}", Status.PASS if ok else Status.FAIL,
                                       "port open" if ok else "port closed or filtered", ms))
        else:
            ok, ms = ping(host_name)
            results.append(CheckResult(f"Host {host}", Status.PASS if ok else Status.FAIL,
                                       "replied to ping" if ok else "no reply", ms))

    return results


def diagnose(results: list[CheckResult]) -> str:
    """Explain the most likely root cause, the way you'd write it in a ticket."""
    by_name = {r.name: r.status for r in results}

    def failed(prefix: str) -> bool:
        return any(name.startswith(prefix) and status is Status.FAIL for name, status in by_name.items())

    if by_name.get("Local IP") is Status.FAIL:
        return "No network connection. Check the cable or Wi-Fi, and confirm the network adapter is enabled."
    # Only blame local problems if the internet is actually unreachable - some networks
    # (VPNs, cloud machines) route traffic without a normal gateway and work fine.
    if failed("Internet"):
        if by_name.get("Local IP") is Status.WARN:
            return "The computer has a self-assigned (169.254.x.x) address. DHCP failed - restart the router or run 'ipconfig /renew'."
        if by_name.get("Gateway") is Status.FAIL:
            return "No default gateway. Check the IP settings or DHCP configuration."
        return "The local network works but the internet is unreachable. Likely an ISP, router or firewall issue."
    if failed("DNS"):
        return "The internet is reachable but names don't resolve. This is a DNS problem - try flushing DNS or changing DNS servers."
    if failed("Web"):
        return "DNS works but web traffic fails. Check the proxy settings, firewall, or security software."
    if failed("Host"):
        return "General connectivity is fine. The problem is specific to the host(s) you listed."
    return "All network checks passed. The issue is likely with the specific application or website."
