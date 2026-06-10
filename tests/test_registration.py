from estudent_mcp.models import RegistrationItem
from estudent_mcp.registration import compute_fingerprint, summarize


def test_fingerprint_is_order_independent():
    a = [
        RegistrationItem("add", "COMP2011", "1A"),
        RegistrationItem("drop", "MATH1011"),
    ]
    b = list(reversed(a))
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_fingerprint_changes_with_content():
    a = [RegistrationItem("add", "COMP2011", "1A")]
    b = [RegistrationItem("add", "COMP2011", "2B")]
    assert compute_fingerprint(a) != compute_fingerprint(b)


def test_fingerprint_normalizes_case_and_whitespace():
    a = [RegistrationItem("add", "comp2011", " 1a ")]
    b = [RegistrationItem("add", "COMP2011", "1A")]
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_summarize_lists_actions():
    items = [
        RegistrationItem("add", "COMP2011", "1A"),
        RegistrationItem("drop", "MATH1011"),
    ]
    text = summarize(items)
    assert "ADD COMP2011 [1A]" in text
    assert "DROP MATH1011" in text
