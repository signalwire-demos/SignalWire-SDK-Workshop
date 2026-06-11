"""
Unit tests for creds_normalize: attendees paste Space URLs in every shape
('https://demo.signalwire.com', trailing slash, dashboard path, uppercase,
bare space name). The normalizer must reduce all of them to the API host
form 'demo.signalwire.com' and reject values that cannot be a space host.

Run from the project root:
    pytest tests/test_creds_normalize.py -v
"""

import pytest

from creds_normalize import normalize_space, normalize_creds


# (raw input, expected normalized host)
VALID_CASES = [
    ("demo.signalwire.com", "demo.signalwire.com"),
    ("https://demo.signalwire.com", "demo.signalwire.com"),
    ("http://demo.signalwire.com", "demo.signalwire.com"),
    ("HTTPS://DEMO.SignalWire.com", "demo.signalwire.com"),
    ("demo.signalwire.com/", "demo.signalwire.com"),
    ("https://demo.signalwire.com/", "demo.signalwire.com"),
    ("https://demo.signalwire.com/dashboard", "demo.signalwire.com"),
    ("demo.signalwire.com/api/fabric", "demo.signalwire.com"),
    ("  demo.signalwire.com  ", "demo.signalwire.com"),
    ("demo.signalwire.com:443", "demo.signalwire.com"),
    ("demo.signalwire.com.", "demo.signalwire.com"),
    ("//demo.signalwire.com", "demo.signalwire.com"),
    # Bare space name: attendees often type only the subdomain.
    ("demo", "demo.signalwire.com"),
    ("my-space", "my-space.signalwire.com"),
]


@pytest.mark.parametrize("raw,expected", VALID_CASES)
def test_normalize_space_valid(raw, expected):
    assert normalize_space(raw) == expected


INVALID_CASES = ["", "   ", "https://", "demo signalwire com", "demo..signalwire.com",
                 "-demo.signalwire.com", "https:///nohost"]


@pytest.mark.parametrize("raw", INVALID_CASES)
def test_normalize_space_invalid(raw):
    with pytest.raises(ValueError):
        normalize_space(raw)


def test_normalize_space_error_message_is_attendee_friendly():
    # The wizard shows this string verbatim; it must say what to enter.
    with pytest.raises(ValueError, match="signalwire.com"):
        normalize_space("not a space url")


def test_normalize_creds_normalizes_space_and_strips_all():
    creds, changes = normalize_creds({
        "SIGNALWIRE_PROJECT_ID": "  abc-123  ",
        "SIGNALWIRE_TOKEN": " PTtok ",
        "SIGNALWIRE_SPACE": "https://Demo.SignalWire.com/",
    })
    assert creds == {
        "SIGNALWIRE_PROJECT_ID": "abc-123",
        "SIGNALWIRE_TOKEN": "PTtok",
        "SIGNALWIRE_SPACE": "demo.signalwire.com",
    }
    # Change notes feed the server log; they must mention the space rewrite
    # and must NEVER contain the token value.
    joined = " ".join(changes)
    assert "demo.signalwire.com" in joined
    assert "PTtok" not in joined


def test_normalize_creds_untouched_input_reports_no_changes():
    creds, changes = normalize_creds({
        "SIGNALWIRE_PROJECT_ID": "abc",
        "SIGNALWIRE_TOKEN": "PTtok",
        "SIGNALWIRE_SPACE": "demo.signalwire.com",
    })
    assert creds["SIGNALWIRE_SPACE"] == "demo.signalwire.com"
    assert changes == []


def test_normalize_creds_invalid_space_raises():
    with pytest.raises(ValueError):
        normalize_creds({"SIGNALWIRE_SPACE": "demo..signalwire.com"})
