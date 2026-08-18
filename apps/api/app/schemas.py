import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import MaturityLevel


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    profile_name: str = Field(min_length=1, max_length=50)
    captcha_token: str | None = Field(default=None, max_length=2048)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if (
            not any(c.islower() for c in value)
            or not any(c.isupper() for c in value)
            or not any(c.isdigit() for c in value)
        ):
            raise ValueError("Password must contain uppercase, lowercase, and numeric characters")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    captcha_token: str | None = Field(default=None, max_length=2048)


class AdminLoginRequest(LoginRequest):
    mfa_code: str | None = Field(default=None, min_length=6, max_length=32)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    message: str
    development_reset_token: str | None = None


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return RegisterRequest.strong_password(value)


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MfaEnrollmentResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaConfirmationResponse(BaseModel):
    enabled: bool
    recovery_codes: list[str]


class ProfilePreferenceData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    autoplay_next: bool = True
    autoplay_previews: bool = True
    preferred_audio_language: str | None = Field(default=None, max_length=16)
    preferred_subtitle_language: str | None = Field(default=None, max_length=16)
    preferred_secondary_subtitle_language: str | None = Field(default=None, max_length=16)
    subtitles_enabled: bool = False
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    caption_size: str = Field(default="medium", pattern="^(small|medium|large)$")
    caption_background: str = Field(default="shadow", pattern="^(transparent|shadow|solid)$")
    caption_position: str = Field(default="bottom", pattern="^(bottom|top)$")
    cinephile_mode: bool = False
    rewatch_intelligence_enabled: bool = True
    analytics_enabled: bool = False
    consent_updated_at: datetime | None = None
    homepage_mode: str = Field(default="curated", pattern="^(curated|no_algorithm)$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Timezone must be a valid IANA identifier") from error
        return value


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    avatar_key: str | None = Field(default=None, max_length=200)
    maturity_level: MaturityLevel = MaturityLevel.adult
    language: str = Field(default="en", min_length=2, max_length=16)
    is_kids: bool = False
    preference: ProfilePreferenceData = Field(default_factory=ProfilePreferenceData)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    avatar_key: str | None = Field(default=None, max_length=200)
    maturity_level: MaturityLevel | None = None
    language: str | None = Field(default=None, min_length=2, max_length=16)
    is_kids: bool | None = None
    preference: ProfilePreferenceData | None = None


class ProfilePrivacyUpdate(BaseModel):
    analytics_enabled: bool
    homepage_mode: str = Field(pattern="^(curated|no_algorithm)$")


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    avatar_key: str | None
    maturity_level: MaturityLevel
    language: str
    is_kids: bool
    preference: ProfilePreferenceData


class AccountResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    profiles: list[ProfileResponse]
    active_profile_id: uuid.UUID | None = None


class AdminResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    mfa_enabled: bool
