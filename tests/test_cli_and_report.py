import json

import pytest

from helpdesk_toolkit import cli, report
from helpdesk_toolkit.procs import ProcessInfo
from helpdesk_toolkit.utils import CheckResult, Status

FAKE_INFO = {
    "hostname": "LAPTOP-042", "user": "jdoe", "os": "Windows 11", "architecture": "AMD64",
    "cpu_model": "Test CPU", "cpu_cores_physical": 4, "cpu_cores_logical": 8, "cpu_percent": 12.0,
    "memory_total": 16 * 1024**3, "memory_used": 8 * 1024**3, "memory_percent": 50.0, "swap_percent": 0,
    "boot_time": "2026-09-01T08:00:00", "uptime_seconds": 3600, "ip_addresses": {"Ethernet": "10.0.0.5"},
    "battery": None, "python_version": "3.12.0",
}


def test_parser_requires_a_command():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_parser_netcheck_accepts_multiple_hosts():
    args = cli.build_parser().parse_args(["netcheck", "--host", "fileserver", "--host", "mail:443"])
    assert args.host == ["fileserver", "mail:443"]


@pytest.mark.parametrize(
    ("statuses", "code"),
    [([Status.PASS], 0), ([Status.PASS, Status.WARN], 1), ([Status.WARN, Status.FAIL], 2)],
)
def test_exit_codes(statuses, code):
    assert cli.exit_code_for([CheckResult("x", s, "") for s in statuses]) == code


def test_report_contains_key_sections_and_escapes_html():
    checks = [CheckResult("Memory", Status.WARN, "<b>90%</b>")]
    procs = [ProcessInfo(1, "chrome.exe", "jdoe", 30.0, 500 * 1024**2, 3.0)]
    html_doc = report.build_html_report(FAKE_INFO, checks, [], [], "All network checks passed.", procs, ticket="INC-1001")

    assert "Ticket INC-1001" in html_doc
    assert "LAPTOP-042" in html_doc
    assert "chrome.exe" in html_doc
    assert "Overall: WARN" in html_doc
    assert "&lt;b&gt;90%&lt;/b&gt;" in html_doc  # user-controlled text is escaped


def test_save_report_default_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = report.save_report("<html></html>", None, "LAPTOP/042")
    assert path.name.startswith("health-report_LAPTOP042_")
    assert path.read_text() == "<html></html>"


def test_sysinfo_json_output(monkeypatch, capsys):
    monkeypatch.setattr(cli.sysinfo, "collect_system_info", lambda: FAKE_INFO)
    code = cli.main(["sysinfo", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["info"]["hostname"] == "LAPTOP-042"
    assert code == 0


def test_onboard_command(tmp_path):
    source = tmp_path / "hires.csv"
    source.write_text("first_name,last_name,department\nSam,Lee,HR\n", encoding="utf-8")
    out = tmp_path / "accounts.csv"
    assert cli.main(["onboard", str(source), "--domain", "example.com", "-o", str(out)]) == 0
    assert "slee@example.com" in out.read_text()
