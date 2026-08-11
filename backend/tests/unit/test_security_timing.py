"""Login timing-attack guard (#239): the dummy password hash must be PRECOMPUTED,
not re-hashed on every non-existent-email login — re-hashing would add a second
argon2 op to each miss, making a miss ~2x slower and re-opening the timing oracle
the guard exists to close.
"""

from app.core.security import dummy_password_hash, verify_password


def test_dummy_password_hash_is_computed_once_and_reused():
    # Same object every call → cached (computed once), never re-hashed per miss.
    assert dummy_password_hash() is dummy_password_hash()


def test_dummy_password_hash_is_a_real_argon2_hash():
    # It must be a genuine argon2 hash so verifying against it has the SAME cost as
    # verifying a real user's password — that equal cost is the whole point.
    h = dummy_password_hash()
    assert "argon2" in h
    assert verify_password("anything", h) is False  # a random secret → never matches
