from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterIn,
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
    result = await service.register(payload.email, payload.password, payload.native_language)
    return TokenOut(access_token=result.access_token, user=UserOut.model_validate(result.user))


@router.post("/login", response_model=TokenOut)
async def login(
    payload: LoginIn,
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
    result = await service.login(payload.email, payload.password)
    return TokenOut(access_token=result.access_token, user=UserOut.model_validate(result.user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
