"""Unit tests for email normalization (issue #220).

`EmailStr` only lowercases the domain, not the local part, and the users table's
uniqueness was case-sensitive. Mobile keyboards auto-capitalize the first
letter, so without normalization the same person creates duplicate accounts and
gets a 401 on a correct password. These tests pin the canonical form.
"""

from app.features.auth.emails import normalize_email


def test_lowercases_local_part_and_domain():
    assert normalize_email("John.DOE@Gmail.COM") == "john.doe@gmail.com"


def test_strips_surrounding_whitespace():
    assert normalize_email("  A@B.com \n") == "a@b.com"


def test_already_normalized_is_unchanged():
    assert normalize_email("already@lower.com") == "already@lower.com"
