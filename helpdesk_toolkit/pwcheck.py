"""Password policy checker with a privacy-safe breach lookup.

The breach check uses the Have I Been Pwned "k-anonymity" model: only the first
5 characters of the password's SHA-1 hash ever leave the computer, so neither
the password nor its full hash is sent.
"""

from __future__ import annotations

import hashlib
import math
import string
import urllib.request
from dataclasses import dataclass, field

HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"

COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456", "12345678", "123456789", "qwerty",
    "letmein", "welcome", "welcome1", "admin", "iloveyou", "monkey", "dragon", "abc123",
    "football", "baseball", "sunshine", "princess", "changeme", "summer2024", "winter2024",
}


@dataclass
class PolicyResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    entropy_bits: float = 0.0
    strength: str = "Very weak"


def estimate_entropy(password: str) -> float:
    """Rough entropy estimate: length x log2(size of character pool used)."""
    pool = 0
    if any(c in string.ascii_lowercase for c in password):
        pool += 26
    if any(c in string.ascii_uppercase for c in password):
        pool += 26
    if any(c in string.digits for c in password):
        pool += 10
    if any(c in string.punctuation or c == " " for c in password):
        pool += 33
    if any(ord(c) > 127 for c in password):
        pool += 100
    return round(len(password) * math.log2(pool), 1) if pool else 0.0


def strength_label(bits: float) -> str:
    if bits < 28:
        return "Very weak"
    if bits < 36:
        return "Weak"
    if bits < 60:
        return "Reasonable"
    if bits < 80:
        return "Strong"
    return "Very strong"


def check_policy(password: str, min_length: int = 12, require_classes: int = 3) -> PolicyResult:
    """Check a password against a typical corporate policy."""
    issues: list[str] = []
    if len(password) < min_length:
        issues.append(f"Shorter than {min_length} characters")

    classes = sum([
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ])
    if classes < require_classes:
        issues.append(f"Uses {classes} of 4 character types (needs {require_classes})")

    if password.lower() in COMMON_PASSWORDS:
        issues.append("Appears on the common-password list")

    if any(password[i] == password[i + 1] == password[i + 2] for i in range(len(password) - 2)):
        issues.append("Contains 3 or more repeated characters in a row")

    bits = estimate_entropy(password)
    # Attackers try common passwords first, so the maths-based estimate doesn't apply to them.
    strength = "Very weak" if password.lower() in COMMON_PASSWORDS else strength_label(bits)
    return PolicyResult(passed=not issues, issues=issues, entropy_bits=bits, strength=strength)


def sha1_split(password: str) -> tuple[str, str]:
    """Return (first 5 hex chars, remaining 35) of the uppercase SHA-1 hash."""
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()  # noqa: S324 - required by HIBP API
    return digest[:5], digest[5:]


def parse_range_response(body: str, suffix: str) -> int:
    """Find our hash suffix in the API response and return its breach count (0 if absent)."""
    for line in body.splitlines():
        candidate, _, count = line.strip().partition(":")
        if candidate.upper() == suffix:
            try:
                return int(count)
            except ValueError:
                return 0
    return 0


def breach_count(password: str, timeout_s: float = 8) -> int:
    """How many times this password appears in known breaches (via k-anonymity)."""
    prefix, suffix = sha1_split(password)
    request = urllib.request.Request(  # noqa: S310 - fixed https API URL
        HIBP_RANGE_URL.format(prefix=prefix),
        headers={"User-Agent": "helpdesk-toolkit", "Add-Padding": "true"},
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - fixed https URL
        body = response.read().decode("utf-8")
    return parse_range_response(body, suffix)
