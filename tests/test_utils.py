import pytest

from helpdesk_toolkit.utils import CheckResult, Status, human_bytes, human_duration, threshold_status


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "0 B"), (512, "512 B"), (1536, "1.5 KB"), (5 * 1024**3, "5.0 GB"), (2 * 1024**4, "2.0 TB")],
)
def test_human_bytes(value, expected):
    assert human_bytes(value) == expected


def test_human_bytes_rejects_negative():
    with pytest.raises(ValueError):
        human_bytes(-1)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(59, "0m"), (3600, "1h 0m"), (93784, "1d 2h 3m"), (-5, "0m")],
)
def test_human_duration(seconds, expected):
    assert human_duration(seconds) == expected


@pytest.mark.parametrize(
    ("percent", "expected"),
    [(10, Status.PASS), (85, Status.WARN), (94.9, Status.WARN), (95, Status.FAIL)],
)
def test_threshold_status(percent, expected):
    assert threshold_status(percent, warn=85, fail=95) is expected


def test_check_result_to_dict_uses_plain_status():
    data = CheckResult("DNS", Status.FAIL, "timeout", 12.5).to_dict()
    assert data == {"name": "DNS", "status": "FAIL", "detail": "timeout", "elapsed_ms": 12.5}
