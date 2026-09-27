import pytest

from helpdesk_toolkit import netcheck
from helpdesk_toolkit.utils import CheckResult, Status

WINDOWS_ROUTE = """
IPv4 Route Table
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      192.168.1.1    192.168.1.50     35
        127.0.0.0        255.0.0.0         On-link         127.0.0.1    331
"""
LINUX_ROUTE = "default via 10.0.0.1 dev eth0 proto dhcp src 10.0.0.23 metric 100\n"
MAC_ROUTE = "   route to: default\ndestination: default\n    gateway: 172.16.0.1\n  interface: en0\n"


@pytest.mark.parametrize(
    ("output", "system", "expected"),
    [
        (WINDOWS_ROUTE, "Windows", "192.168.1.1"),
        (LINUX_ROUTE, "Linux", "10.0.0.1"),
        (MAC_ROUTE, "Darwin", "172.16.0.1"),
        ("", "Linux", None),
    ],
)
def test_parse_default_gateway(output, system, expected):
    assert netcheck.parse_default_gateway(output, system) == expected


def _results(**statuses):
    names = {
        "local": "Local IP", "gateway": "Gateway", "internet": "Internet",
        "dns": "DNS www.google.com", "web": "Web (HTTPS)", "host": "Host fileserver",
    }
    base = {key: Status.PASS for key in names}
    base.update(statuses)
    return [CheckResult(names[k], v, "") for k, v in base.items()]


@pytest.mark.parametrize(
    ("statuses", "keyword"),
    [
        ({}, "All network checks passed"),
        ({"local": Status.FAIL}, "No network connection"),
        ({"local": Status.WARN, "internet": Status.FAIL}, "self-assigned"),
        ({"gateway": Status.FAIL, "internet": Status.FAIL}, "No default gateway"),
        # Gateway missing but the internet works (VPN / cloud) - not the root cause.
        ({"gateway": Status.FAIL}, "All network checks passed"),
        ({"gateway": Status.FAIL, "web": Status.FAIL}, "proxy"),
        ({"internet": Status.FAIL}, "internet is unreachable"),
        ({"dns": Status.FAIL}, "DNS problem"),
        ({"web": Status.FAIL}, "proxy"),
        ({"host": Status.FAIL}, "specific to the host"),
    ],
)
def test_diagnose_identifies_root_cause(statuses, keyword):
    assert keyword in netcheck.diagnose(_results(**statuses))


def test_diagnose_reports_earliest_failure_first():
    # If the adapter is down, everything after it fails too - the adapter is the real cause.
    results = _results(local=Status.FAIL, gateway=Status.FAIL, internet=Status.FAIL, dns=Status.FAIL)
    assert "No network connection" in netcheck.diagnose(results)


def test_dns_lookup_handles_bad_name():
    ok, detail, ms = netcheck.dns_lookup("this-name-does-not-exist.invalid")
    assert ok is False and ms is None and detail


def test_tcp_check_closed_port_on_localhost():
    ok, ms = netcheck.tcp_check("127.0.0.1", 1, timeout_s=1)
    assert ok is False and ms is None
