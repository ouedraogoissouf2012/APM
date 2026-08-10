"""Email normalization for the auth boundary (issue #220).

`EmailStr` only lowercases the domain, not the local part, and the users table's
uniqueness was case-sensitive. Mobile keyboards auto-capitalize, so without
normalization the same person creates duplicate accounts and gets a 401 on a
correct password.

This is the single source of truth for the canonical email form, used by both
the request schema (early, at the API boundary) and the service (authoritative,
independent of the caller).
"""


def normalize_email(email: str) -> str:
    """Return the canonical form of an email: trimmed and lowercased."""
    return email.strip().lower()
