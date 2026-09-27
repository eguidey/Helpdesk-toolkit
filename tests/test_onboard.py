import csv
import string

import pytest

from helpdesk_toolkit import onboard


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("José", "jose"), ("O'Brien", "obrien"), ("Mary-Kate", "marykate"), ("  Li ", "li")],
)
def test_normalise_name(raw, expected):
    assert onboard.normalise_name(raw) == expected


def test_make_username_deduplicates():
    taken = set()
    assert onboard.make_username("John", "Smith", taken) == "jsmith"
    assert onboard.make_username("Jane", "Smith", taken) == "jsmith2"
    assert onboard.make_username("Jim", "Smith", taken) == "jsmith3"


def test_make_username_respects_existing_accounts():
    assert onboard.make_username("Ian", "Guidry", {"iguidry"}) == "iguidry2"


def test_make_username_truncates_long_names():
    name = onboard.make_username("Alexandria", "Vanderbiltsworthington", set(), max_length=20)
    assert len(name) == 20


def test_make_username_rejects_empty():
    with pytest.raises(ValueError):
        onboard.make_username("", "Smith", set())


def test_temp_password_has_every_character_type():
    for _ in range(50):
        pw = onboard.generate_temp_password(14)
        assert len(pw) == 14
        assert any(c.islower() for c in pw)
        assert any(c.isupper() for c in pw)
        assert any(c.isdigit() for c in pw)
        assert any(c in onboard.SAFE_SYMBOLS for c in pw)
        assert not set(pw) & set("0O1lI")  # no look-alike characters


def test_temp_passwords_are_unique():
    assert len({onboard.generate_temp_password() for _ in range(200)}) == 200


def test_temp_password_minimum_length():
    with pytest.raises(ValueError):
        onboard.generate_temp_password(6)


def test_end_to_end_csv(tmp_path):
    source = tmp_path / "hires.csv"
    source.write_text("First_Name,Last_Name,Department,Title\nAva,Nguyen,Finance,Analyst\nAdam,Nguyen,IT,Technician\n",
                      encoding="utf-8")
    rows = onboard.load_new_hires(source)
    accounts = onboard.build_accounts(rows, domain="example.com")

    out = tmp_path / "out.csv"
    onboard.write_accounts(accounts, out)
    with open(out, newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))

    assert [r["username"] for r in written] == ["anguyen", "anguyen2"]
    assert written[1]["email"] == "anguyen2@example.com"
    assert all(set(r["temp_password"]) <= set(string.printable) for r in written)


def test_missing_columns_raise(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("first_name,last_name\nA,B\n", encoding="utf-8")
    with pytest.raises(ValueError, match="department"):
        onboard.load_new_hires(source)
