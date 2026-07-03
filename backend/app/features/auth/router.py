from fastapi import APIRouter, Depends, Request, status

from app.core.rate_limit import RateLimiter
from app.core.security import hash_token
from app.features.auth.dependencies import (
    get_auth_service,
    get_current_user,
    get_login_rate_limiter,
    get_refresh_rate_limiter,
    get_register_rate_limiter,
)
from app.features.auth.models import User
from app.features.auth.schemas import (
    LoginIn,
    LogoutIn,
    RefreshIn,
    RegisterIn,
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
    return request.client.host if request.client else "anonymous"


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterIn,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    limiter: RateLimiter = Depends(get_register_rate_limiter),
) -> TokenOut:
    await limiter.check(f"register:{_client_host(request)}:{str(payload.email).lower()}")
    result = await service.register(payload.email, payload.password, payload.native_language)
    return _to_token_out(result)


@router.post("/login", response_model=TokenOut)
async def login(
    payload: LoginIn,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    limiter: RateLimiter = Depends(get_login_rate_limiter),
) -> TokenOut:
    await limiter.check(f"login:{_client_host(request)}:{str(payload.email).lower()}")
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
