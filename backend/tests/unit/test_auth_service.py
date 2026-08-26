from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import create_access_token, decode_access_token, hash_token
from app.domain.exceptions import (
    AuthenticationError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    NotFoundError,
)
from app.features.auth.service import AuthService
from tests.unit.fakes import InMemoryRefreshTokenRepository, InMemoryUserRepository


class _SpyMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, *, to: str, subject: str, text: str) -> None:
        self.sent.append((to, subject, text))


def _service(*, mailer: _SpyMailer | None = None) -> AuthService:
    return AuthService(
        InMemoryUserRepository(),
        InMemoryRefreshTokenRepository(),
        refresh_ttl_days=30,
        mailer=mailer,
    )


def _backdate_revocation(service: AuthService, raw_token: str, *, seconds: int) -> None:
    """Simulate elapsed time since a token was rotated: move its revoked_at into the
    past so re-presenting it falls OUTSIDE the grace window — a theft replay, not a
    near-simultaneous retry. Reaches into the in-memory fake (a test double)."""
    record = service._refresh._by_hash[hash_token(raw_token)]  # type: ignore[attr-defined]
    record.revoked_at = datetime.now(UTC) - timedelta(seconds=seconds)


@pytest.mark.asyncio
async def test_register_creates_user_and_tokens():
    service = _service()
    result = await service.register("a@b.com", "s3cret!pass", "fr")
    assert result.user.email == "a@b.com"
    assert decode_access_token(result.access_token) == str(result.user.id)
    assert result.refresh_token  # opaque refresh token issued


@pytest.mark.asyncio
async def test_register_duplicate_email_raises():
    service = _service()
    await service.register("dup@b.com", "s3cret!pass", "fr")
    with pytest.raises(EmailAlreadyExistsError):
        await service.register("dup@b.com", "other!", "fr")


@pytest.mark.asyncio
async def test_email_is_stored_lowercased():
    # #220: EmailStr only lowercases the domain; register must canonicalise the
    # whole address so lookups and the unique index are case-insensitive.
    service = _service()
    result = await service.register("Jean.Dupont@GMail.com", "s3cret!pass", "fr")
    assert result.user.email == "jean.dupont@gmail.com"


@pytest.mark.asyncio
async def test_login_is_case_insensitive():
    # A mobile keyboard auto-capitalises the email at register; logging in with a
    # different case must still find the account (#220).
    service = _service()
    await service.register("Case@Example.com", "s3cret!pass", "fr")
    result = await service.login("case@EXAMPLE.com", "s3cret!pass")
    assert result.user.email == "case@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_differing_only_by_case_raises():
    service = _service()
    await service.register("Dup@x.com", "s3cret!pass", "fr")
    with pytest.raises(EmailAlreadyExistsError):
        await service.register("dup@x.com", "other!", "fr")


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password():
    service = _service()
    await service.register("log@b.com", "s3cret!pass", "fr")
    result = await service.login("log@b.com", "s3cret!pass")
    assert decode_access_token(result.access_token) == str(result.user.id)


@pytest.mark.asyncio
async def test_login_wrong_password_raises():
    service = _service()
    await service.register("x@b.com", "s3cret!pass", "fr")
    with pytest.raises(InvalidCredentialsError):
        await service.login("x@b.com", "nope")


@pytest.mark.asyncio
async def test_login_unknown_email_raises():
    service = _service()
    with pytest.raises(InvalidCredentialsError):
        await service.login("ghost@b.com", "whatever")


@pytest.mark.asyncio
async def test_login_succeeds_even_if_purge_expired_would_raise():
    # #407: login() must NOT invoke the best-effort expired-token purge inline —
    # that's the background loop's job (task.py), running in its own session with
    # its own rollback. Sharing login's transaction meant a purge failure could
    # poison it and turn a legitimate login into a raw 500. Proof: a repository
    # whose purge_expired always raises must not stop login from succeeding.
    class _PurgeExplodesRepository(InMemoryRefreshTokenRepository):
        async def purge_expired(self, now, *, commit=True):
            raise RuntimeError("purge_expired must not be called from login")

    service = AuthService(
        InMemoryUserRepository(),
        _PurgeExplodesRepository(),
        refresh_ttl_days=30,
    )
    await service.register("purge@b.com", "s3cret!pass", "fr")
    result = await service.login("purge@b.com", "s3cret!pass")
    assert result.user.email == "purge@b.com"


@pytest.mark.asyncio
async def test_refresh_rotates_and_returns_new_tokens():
    service = _service()
    reg = await service.register("r@b.com", "s3cret!pass", "fr")
    refreshed = await service.refresh(reg.refresh_token)
    assert refreshed.refresh_token != reg.refresh_token  # rotation
    assert decode_access_token(refreshed.access_token) == str(reg.user.id)


@pytest.mark.asyncio
async def test_refresh_with_used_token_is_rejected():
    service = _service()
    reg = await service.register("r2@b.com", "s3cret!pass", "fr")
    await service.refresh(reg.refresh_token)  # consumes/rotates it
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)  # reuse rejected


@pytest.mark.asyncio
async def test_refresh_unknown_token_rejected():
    service = _service()
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh("not-a-real-token")


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token():
    service = _service()
    reg = await service.register("lo@b.com", "s3cret!pass", "fr")
    await service.logout(reg.refresh_token)
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)


@pytest.mark.asyncio
async def test_get_authenticated_user_returns_user():
    service = _service()
    reg = await service.register("me@b.com", "s3cret!pass", "fr")
    user = await service.get_authenticated_user(reg.access_token)
    assert user.email == "me@b.com"


@pytest.mark.asyncio
async def test_get_authenticated_user_invalid_token_raises():
    service = _service()
    with pytest.raises(AuthenticationError):
        await service.get_authenticated_user("not-a-jwt")


@pytest.mark.asyncio
async def test_get_authenticated_user_unknown_user_raises():
    service = _service()
    token = create_access_token(subject="999")
    with pytest.raises(AuthenticationError):
        await service.get_authenticated_user(token)


# ---- Account lifecycle (#232) ----


@pytest.mark.asyncio
async def test_deactivated_user_cannot_authenticate():
    service = _service()
    reg = await service.register("d@b.com", "s3cret!pass", "fr")
    reg.user.is_active = False  # an admin suspended the account
    with pytest.raises(AuthenticationError):
        await service.get_authenticated_user(reg.access_token)


@pytest.mark.asyncio
async def test_deactivated_user_cannot_refresh():
    service = _service()
    reg = await service.register("d2@b.com", "s3cret!pass", "fr")
    reg.user.is_active = False
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)


@pytest.mark.asyncio
async def test_deactivated_user_cannot_login():
    # #416: login must refuse a deactivated account with the same error as a
    # wrong password — and must not mint a fresh living refresh token.
    service = _service()
    reg = await service.register("d3@b.com", "s3cret!pass", "fr")
    await service.set_active(reg.user.id, False)
    tokens_before = len(service._refresh._by_hash)
    with pytest.raises(InvalidCredentialsError):
        await service.login("d3@b.com", "s3cret!pass")
    assert len(service._refresh._by_hash) == tokens_before


@pytest.mark.asyncio
async def test_refresh_reuse_beyond_grace_revokes_the_whole_family():
    # Re-presenting a rotated token LONG after rotation is a theft replay: EVERY
    # session (incl. the attacker's freshly-rotated one) must die (#232).
    service = _service()
    reg = await service.register("reuse@b.com", "s3cret!pass", "fr")
    rotated = await service.refresh(reg.refresh_token)  # reg token now revoked
    _backdate_revocation(service, reg.refresh_token, seconds=120)  # past the grace window
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)  # stale reuse -> revoke the family
    # The attacker's rotated token is now dead too.
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(rotated.refresh_token)


@pytest.mark.asyncio
async def test_refresh_reuse_within_grace_does_not_nuke_sessions():
    # A near-simultaneous benign retry (a network retry, or a second device racing
    # the rotation) must NOT log the learner out everywhere (#253): the stale token
    # is rejected, but the freshly-rotated one keeps working.
    service = _service()  # default 30 s grace
    reg = await service.register("benign@b.com", "s3cret!pass", "fr")
    rotated = await service.refresh(reg.refresh_token)  # reg.revoked_at = now
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)  # stale token rejected...
    # ...but the family survives: the current session still refreshes.
    again = await service.refresh(rotated.refresh_token)
    assert again.refresh_token != rotated.refresh_token


@pytest.mark.asyncio
async def test_change_password_requires_old_and_revokes_sessions():
    service = _service()
    reg = await service.register("cp@b.com", "s3cret!pass", "fr")
    await service.change_password(reg.user, "s3cret!pass", "n3w!password")
    # The old session is revoked...
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)
    # ...and the new password works.
    result = await service.login("cp@b.com", "n3w!password")
    assert result.user.id == reg.user.id


@pytest.mark.asyncio
async def test_change_password_invalidates_an_outstanding_reset_token():
    service = _service()
    await service.register("rst-chg@b.com", "s3cret!pass", "fr")
    tokens = await service.login("rst-chg@b.com", "s3cret!pass")
    raw = await service.request_password_reset("rst-chg@b.com")
    assert raw
    await service.change_password(tokens.user, "s3cret!pass", "n3w!password")
    with pytest.raises(InvalidCredentialsError):
        await service.reset_password(raw, "another!pass")
    await service.login("rst-chg@b.com", "n3w!password")


@pytest.mark.asyncio
async def test_change_password_stages_hash_and_revoke_then_one_commit():
    # #421: both writes must be uncommitted until a single commit.
    users = InMemoryUserRepository()
    refresh = InMemoryRefreshTokenRepository()
    save_commits: list[bool] = []
    revoke_commits: list[bool] = []
    commits = 0

    orig_save = users.save

    async def _save(user, *, commit=True):
        save_commits.append(commit)
        return await orig_save(user, commit=commit)

    users.save = _save  # type: ignore[method-assign]
    orig_revoke = refresh.revoke_all_for_user

    async def _revoke(user_id, revoked_at, *, commit=True):
        revoke_commits.append(commit)
        return await orig_revoke(user_id, revoked_at, commit=commit)

    refresh.revoke_all_for_user = _revoke  # type: ignore[method-assign]
    orig_commit = refresh.commit

    async def _commit():
        nonlocal commits
        commits += 1
        await orig_commit()

    refresh.commit = _commit  # type: ignore[method-assign]

    service = AuthService(users, refresh, refresh_ttl_days=30)
    reg = await service.register("cp-atomic@b.com", "s3cret!pass", "fr")
    save_commits.clear()
    revoke_commits.clear()
    commits = 0
    await service.change_password(reg.user, "s3cret!pass", "n3w!password")
    assert save_commits == [False]
    assert revoke_commits == [False]
    assert commits == 1


@pytest.mark.asyncio
async def test_change_password_rolls_back_when_revoke_fails():
    # #421: a failed revoke must not leave a committed new hash (SQL path).
    users = InMemoryUserRepository()
    refresh = InMemoryRefreshTokenRepository()
    rolled_back = False

    async def _explode(user_id, revoked_at, *, commit=True):
        raise RuntimeError("revoke failed")

    async def _rollback():
        nonlocal rolled_back
        rolled_back = True

    refresh.revoke_all_for_user = _explode  # type: ignore[method-assign]
    refresh.rollback = _rollback  # type: ignore[method-assign]
    service = AuthService(users, refresh, refresh_ttl_days=30)
    reg = await service.register("cp-fail@b.com", "s3cret!pass", "fr")
    with pytest.raises(RuntimeError, match="revoke failed"):
        await service.change_password(reg.user, "s3cret!pass", "n3w!password")
    assert rolled_back is True


@pytest.mark.asyncio
async def test_forgot_unknown_email_returns_none():
    mailer = _SpyMailer()
    service = _service(mailer=mailer)
    assert await service.request_password_reset("ghost@b.com") is None
    assert mailer.sent == []


@pytest.mark.asyncio
async def test_forgot_known_email_sends_reset_mail_with_token():
    mailer = _SpyMailer()
    service = _service(mailer=mailer)
    await service.register("rst-mail@b.com", "s3cret!pass", "fr")
    mailer.sent.clear()
    raw = await service.request_password_reset("rst-mail@b.com")
    assert raw
    assert len(mailer.sent) == 1
    to, subject, text = mailer.sent[0]
    assert to == "rst-mail@b.com"
    assert "mot de passe" in subject.lower()
    assert raw in text


@pytest.mark.asyncio
async def test_register_sends_welcome_mail():
    mailer = _SpyMailer()
    service = _service(mailer=mailer)
    await service.register("hi@b.com", "s3cret!pass", "fr")
    assert any(s[0] == "hi@b.com" and "Bienvenue" in s[1] for s in mailer.sent)


@pytest.mark.asyncio
async def test_reset_password_with_issued_token_then_old_password_fails():
    service = _service()
    await service.register("rst@b.com", "s3cret!pass", "fr")
    raw = await service.request_password_reset("rst@b.com")
    assert raw
    await service.reset_password(raw, "n3w!password")
    with pytest.raises(InvalidCredentialsError):
        await service.login("rst@b.com", "s3cret!pass")
    tokens = await service.login("rst@b.com", "n3w!password")
    assert tokens.access_token


@pytest.mark.asyncio
async def test_reset_password_rejects_unknown_token():
    service = _service()
    with pytest.raises(InvalidCredentialsError):
        await service.reset_password("not-a-real-token-xx", "n3w!password")


@pytest.mark.asyncio
async def test_change_password_wrong_old_raises():
    service = _service()
    reg = await service.register("cp2@b.com", "s3cret!pass", "fr")
    with pytest.raises(InvalidCredentialsError):
        await service.change_password(reg.user, "WRONG", "n3w!password")


@pytest.mark.asyncio
async def test_set_active_deactivates_and_revokes_sessions():
    service = _service()
    reg = await service.register("sa@b.com", "s3cret!pass", "fr")
    await service.set_active(reg.user.id, False)
    assert reg.user.is_active is False
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(reg.refresh_token)


@pytest.mark.asyncio
async def test_set_active_unknown_user_raises():
    service = _service()
    with pytest.raises(NotFoundError):
        await service.set_active(9999, False)
