from fastapi import APIRouter, Depends, Request, status

from app.api.client_ip import client_ip
from app.config import get_settings
from app.core.rate_limit import RateLimiter, user_rate_limit_key
from app.core.security import hash_token
from app.features.auth.dependencies import (
    get_auth_service,
    get_change_password_rate_limiter,
    get_current_admin,
    get_current_user,
    get_login_ip_rate_limiter,
    get_login_rate_limiter,
    get_refresh_rate_limiter,
    get_register_ip_rate_limiter,
    get_register_rate_limiter,
)
from app.features.auth.models import User
from app.features.auth.schemas import (
    ChangePasswordIn,
    LoginIn,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    SetActiveIn,
    TokenOut,
    UserOut,
)
from app.features.auth.service import AuthResult, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_token_out(result: AuthResult) -> TokenOut:
    return TokenOut(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user=UserOut.model_validate(result.user),
    )


def _client_host(request: Request) -> str:
    s = get_settings()
    return client_ip(request, s.trust_proxy_headers, s.trusted_proxy_count)


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterIn,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    limiter: RateLimiter = Depends(get_register_rate_limiter),
    ip_limiter: RateLimiter = Depends(get_register_ip_rate_limiter),
) -> TokenOut:
    client_host = _client_host(request)
    # #355: the (ip, email) limiter below is bypassed by varying the email on
    # every attempt from the same IP — checked first as a coarse per-IP backstop.
    await ip_limiter.check(f"register-ip:{client_host}")
    await limiter.check(f"register:{client_host}:{str(payload.email).lower()}")
    result = await service.register(payload.email, payload.password, payload.native_language)
    return _to_token_out(result)


@router.post("/login", response_model=TokenOut)
async def login(
    payload: LoginIn,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    limiter: RateLimiter = Depends(get_login_rate_limiter),
    ip_limiter: RateLimiter = Depends(get_login_ip_rate_limiter),
) -> TokenOut:
    client_host = _client_host(request)
    # #355: the (ip, email) limiter below is bypassed by varying the email on
    # every attempt from the same IP — checked first as a coarse per-IP backstop.
    await ip_limiter.check(f"login-ip:{client_host}")
    await limiter.check(f"login:{client_host}:{str(payload.email).lower()}")
    result = await service.login(payload.email, payload.password)
    return _to_token_out(result)


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    payload: RefreshIn,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    limiter: RateLimiter = Depends(get_refresh_rate_limiter),
) -> TokenOut:
    await limiter.check(f"refresh:{_client_host(request)}:{hash_token(payload.refresh_token)}")
    result = await service.refresh(payload.refresh_token)
    return _to_token_out(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutIn,
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.logout(payload.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordIn,
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
    limiter: RateLimiter = Depends(get_change_password_rate_limiter),
) -> None:
    # Keyed by user_id, not IP (#300): the caller is already authenticated via
    # get_current_user, so this throttles brute-forcing old_password with a
    # stolen access token regardless of which IP the attacker calls from.
    # Via the canonical helper (#374), not a hand-rolled f-string — the single
    # place the "per-user, no IP" invariant lives (#356).
    await limiter.check(user_rate_limit_key("change_password", current_user.id))
    await service.change_password(current_user, payload.old_password, payload.new_password)


@router.post("/admin/users/{user_id}/active", status_code=status.HTTP_204_NO_CONTENT)
async def set_user_active(
    user_id: int,
    payload: SetActiveIn,
    _admin: User = Depends(get_current_admin),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.set_active(user_id, payload.is_active)
