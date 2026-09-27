import hashlib

from helpdesk_toolkit import pwcheck


def test_strong_password_passes_policy():
    result = pwcheck.check_policy("Blue-Harbor-Lantern-42")
    assert result.passed
    assert result.strength in {"Strong", "Very strong"}


def test_common_short_password_fails_with_reasons():
    result = pwcheck.check_policy("password")
    assert not result.passed
    joined = " ".join(result.issues)
    assert "Shorter than" in joined
    assert "common-password" in joined
    assert "character types" in joined


def test_common_password_always_rated_very_weak():
    # Long enough to look "strong" mathematically, but attackers try it first.
    result = pwcheck.check_policy("Summer2024")
    assert result.strength == "Very weak"


def test_repeated_characters_flagged():
    result = pwcheck.check_policy("Aaaa1234!xyzQ")
    assert any("repeated" in issue for issue in result.issues)


def test_entropy_grows_with_length_and_variety():
    assert pwcheck.estimate_entropy("") == 0
    assert pwcheck.estimate_entropy("abcdefgh") < pwcheck.estimate_entropy("abcdefghijkl")
    assert pwcheck.estimate_entropy("abcdefgh") < pwcheck.estimate_entropy("aB3$efgh")


def test_sha1_split_matches_hashlib():
    prefix, suffix = pwcheck.sha1_split("hunter2")
    full = hashlib.sha1(b"hunter2").hexdigest().upper()  # noqa: S324
    assert prefix + suffix == full
    assert len(prefix) == 5 and len(suffix) == 35


def test_parse_range_response_finds_count():
    _, suffix = pwcheck.sha1_split("hunter2")
    body = f"0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n{suffix}:17043\r\nFFFFF00000000000000000000000000000:0"
    assert pwcheck.parse_range_response(body, suffix) == 17043


def test_parse_range_response_absent_returns_zero():
    assert pwcheck.parse_range_response("AAAAA:3\nBBBBB:9", "CCCCC") == 0


def test_breach_count_only_sends_hash_prefix(monkeypatch):
    """The full password/hash must never be sent - only the 5-char prefix in the URL."""
    captured = {}
    prefix, suffix = pwcheck.sha1_split("correct horse battery staple")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return f"{suffix}:42\n".encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setattr(pwcheck.urllib.request, "urlopen", fake_urlopen)

    assert pwcheck.breach_count("correct horse battery staple") == 42
    assert captured["url"].endswith("/range/" + prefix)
    assert suffix not in captured["url"]
