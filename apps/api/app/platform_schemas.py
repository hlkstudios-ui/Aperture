import re
import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas import RegisterRequest


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _safe_public_url(value: str) -> str:
    if any(ord(character) < 32 for character in value) or "\\" in value:
        raise ValueError("Public URL is invalid")
    parsed = urlsplit(value)
    if value.startswith("/"):
        if value.startswith("//") or parsed.scheme or parsed.netloc:
            raise ValueError("Application-relative URLs must begin with exactly one slash")
        return value
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Public URLs must use HTTPS or an application-relative path")
    return value


class PlatformRegisterRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    captcha_token: str | None = Field(default=None, max_length=2048)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return RegisterRequest.strong_password(value)


class PlatformLoginRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    captcha_token: str | None = Field(default=None, max_length=2048)


class PlatformAccountResponse(StrictModel):
    id: uuid.UUID
    email: EmailStr
    created_at: datetime


class CaptchaConfiguration(StrictModel):
    required: bool
    test_mode: bool


class PlatformAuthConfiguration(StrictModel):
    captcha: CaptchaConfiguration


class TemplatePreviewAsset(StrictModel):
    kind: Literal["image", "video"]
    url: str = Field(min_length=1, max_length=1000)
    alt: str = Field(min_length=1, max_length=240)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        return _safe_public_url(value)


class PlatformTemplatePricing(StrictModel):
    price_cents: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    interval: Literal["month", "year"]


class PlatformTemplateVersionPublic(StrictModel):
    id: uuid.UUID
    version: str
    feature_manifest: dict[str, object]
    configuration_schema: dict[str, object]


class RentalAgreementPublic(StrictModel):
    id: uuid.UUID
    version: str
    title: str
    content: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at: datetime


class PlatformTemplateSummary(StrictModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    category: str
    thumbnail_url: str | None
    preview_assets: list[TemplatePreviewAsset]
    demo_url: str | None
    status: Literal["preview", "published"]
    current_version: PlatformTemplateVersionPublic | None
    starting_price: PlatformTemplatePricing | None
    rental_available: bool
    unavailable_reason: str | None

    @field_validator("thumbnail_url", "demo_url")
    @classmethod
    def safe_optional_url(cls, value: str | None) -> str | None:
        return _safe_public_url(value) if value is not None else None


class PlatformTemplateDetail(PlatformTemplateSummary):
    rental_agreement: RentalAgreementPublic | None


class PlatformTemplateCollection(StrictModel):
    schema_version: Literal[1] = 1
    items: list[PlatformTemplateSummary]


class RentalIntentCreate(StrictModel):
    template_slug: str = Field(min_length=1, max_length=63)
    template_version_id: uuid.UUID
    agreement_version_id: uuid.UUID
    agreement_version: str = Field(min_length=1, max_length=64)
    agreement_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted: Literal[True]
    business_name: str = Field(min_length=2, max_length=120)
    requested_tenant_slug: str = Field(min_length=2, max_length=63)

    @field_validator("template_slug", "requested_tenant_slug")
    @classmethod
    def normalized_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", normalized):
            raise ValueError("Slug must be a lower-case DNS label")
        return normalized

    @field_validator("business_name")
    @classmethod
    def normalized_business_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2 or any(ord(character) < 32 for character in normalized):
            raise ValueError("Business name is invalid")
        return normalized


class RentalTenantResponse(StrictModel):
    id: uuid.UUID
    slug: str
    business_name: str
    hosted_hostname: str
    status: Literal["reserved"]


class RentalTemplateResponse(StrictModel):
    id: uuid.UUID
    slug: str
    name: str
    version_id: uuid.UUID
    version: str


class RentalAcceptanceResponse(StrictModel):
    id: uuid.UUID
    agreement_version_id: uuid.UUID
    version: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_at: datetime


class PlatformBillingResponse(StrictModel):
    status: Literal["disabled"] = "disabled"
    checkout_available: Literal[False] = False


class TemplateRentalResponse(StrictModel):
    schema_version: Literal[1] = 1
    id: uuid.UUID
    status: Literal["awaiting_payment"]
    tenant: RentalTenantResponse
    template: RentalTemplateResponse
    price_snapshot: PlatformTemplatePricing
    legal_acceptance: RentalAcceptanceResponse
    platform_billing: PlatformBillingResponse = Field(default_factory=PlatformBillingResponse)
    provisioning_status: Literal["not_started"] = "not_started"
    domain_status: Literal["not_created"] = "not_created"
    next_action: Literal["platform_billing_unavailable"] = "platform_billing_unavailable"
    created_at: datetime


class TemplateRentalCollection(StrictModel):
    schema_version: Literal[1] = 1
    rentals: list[TemplateRentalResponse]
