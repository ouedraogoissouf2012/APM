from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.features.auth.emails import normalize_email

# Password policy (NIST 800-63B: 8-character minimum for user-chosen secrets).
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# Email that is validated (EmailStr) then normalized to its canonical lowercase
# form (issue #220). Shared by register + login so both compare/store the same
# value and case never creates duplicate accounts or breaks a login.
NormalizedEmail = Annotated[EmailStr, AfterValidator(normalize_email)]


class RegisterIn(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    native_language: str = "fr"


class LoginIn(BaseModel):
    email: NormalizedEmail
    password: str


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
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str
