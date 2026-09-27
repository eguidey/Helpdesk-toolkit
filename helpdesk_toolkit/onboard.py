"""Bulk new-hire account preparation from a CSV file.

Input CSV columns:  first_name, last_name, department   (title is optional)
Output CSV adds:    username, email, temp_password

The output is ready to review and then import into Active Directory
(for example with PowerShell's New-ADUser) or another identity system.
"""

from __future__ import annotations

import csv
import re
import secrets
import string
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

REQUIRED_COLUMNS = {"first_name", "last_name", "department"}
# Leave out look-alike characters (0/O, 1/l/I) so temporary passwords are easy to read over the phone.
SAFE_LETTERS = "".join(c for c in string.ascii_letters if c not in "OolI")
SAFE_DIGITS = "23456789"
SAFE_SYMBOLS = "!@#$%*?"


@dataclass
class NewAccount:
    first_name: str
    last_name: str
    department: str
    title: str
    username: str
    email: str
    temp_password: str


def normalise_name(value: str) -> str:
    """Lowercase, strip accents and remove anything that isn't a letter.

    'José' -> 'jose', "O'Brien" -> 'obrien', 'Mary-Kate' -> 'marykate'
    """
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", ascii_text.lower())


def make_username(first: str, last: str, taken: set[str], max_length: int = 20) -> str:
    """First initial + last name, adding a number if the name is already used (jsmith, jsmith2...)."""
    first_n, last_n = normalise_name(first), normalise_name(last)
    if not first_n or not last_n:
        raise ValueError(f"Cannot build a username from {first!r} {last!r}")
    base = (first_n[0] + last_n)[:max_length]
    candidate, counter = base, 2
    while candidate in taken:
        suffix = str(counter)
        candidate = base[: max_length - len(suffix)] + suffix
        counter += 1
    taken.add(candidate)
    return candidate


def generate_temp_password(length: int = 14) -> str:
    """Cryptographically random password with every character type guaranteed."""
    if length < 8:
        raise ValueError("Temporary passwords should be at least 8 characters")
    rng = secrets.SystemRandom()
    required = [
        rng.choice([c for c in SAFE_LETTERS if c.islower()]),
        rng.choice([c for c in SAFE_LETTERS if c.isupper()]),
        rng.choice(SAFE_DIGITS),
        rng.choice(SAFE_SYMBOLS),
    ]
    pool = SAFE_LETTERS + SAFE_DIGITS + SAFE_SYMBOLS
    rest = [rng.choice(pool) for _ in range(length - len(required))]
    chars = required + rest
    rng.shuffle(chars)
    return "".join(chars)


def load_new_hires(path: str | Path) -> list[dict[str, str]]:
    """Read and validate the input CSV."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = {h.strip().lower() for h in (reader.fieldnames or [])}
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise ValueError(f"CSV is missing required column(s): {', '.join(sorted(missing))}")
        rows = []
        for line_no, row in enumerate(reader, start=2):
            clean = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not clean.get("first_name") or not clean.get("last_name"):
                raise ValueError(f"Line {line_no}: first_name and last_name are required")
            rows.append(clean)
    return rows


def build_accounts(rows: list[dict[str, str]], domain: str, existing: set[str] | None = None) -> list[NewAccount]:
    """Create account records, avoiding clashes with each other and with existing usernames."""
    taken = set(existing or set())
    accounts = []
    for row in rows:
        username = make_username(row["first_name"], row["last_name"], taken)
        accounts.append(
            NewAccount(
                first_name=row["first_name"],
                last_name=row["last_name"],
                department=row.get("department", ""),
                title=row.get("title", ""),
                username=username,
                email=f"{username}@{domain}",
                temp_password=generate_temp_password(),
            )
        )
    return accounts


def write_accounts(accounts: list[NewAccount], path: str | Path) -> None:
    fields = list(NewAccount.__dataclass_fields__)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for account in accounts:
            writer.writerow(asdict(account))
