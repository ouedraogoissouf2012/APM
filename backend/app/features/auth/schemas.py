from pydantic import BaseModel, EmailStr, Field

# Password policy (NIST 800-63B: 8-character minimum for user-chosen secrets).
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# BCP-47 language tag: https://en.wikipedia.org/wiki/IETF_language_tag
# Patterns: "en", "en-US", "zh-Hans", "de-DE-1996" (max ~8 chars in practice).
NATIVE_LANGUAGE_MAX_LENGTH = 8


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    native_language: str = Field(default="fr", max_length=NATIVE_LANGUAGE_MAX_LENGTH)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class UserOut(BaseModel):
    id: int
    email: EmailStr
    native_language: str
    cefr_level: str
    tier: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=1024)  # JWT/refresh tokens are bounded


class LogoutIn(BaseModel):
    refresh_token: str = Field(max_length=1024)


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class SetActiveIn(BaseModel):
    is_active: bool
