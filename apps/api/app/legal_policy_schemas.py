from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictInt, field_validator

from app.site_brand_schemas import ISO_COUNTRY_CODES


def _reject_control_characters(value: str) -> None:
    if any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value):
        raise ValueError("Legal policy fields cannot contain control characters")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LegalPolicyEditable(StrictModel):
    legal_operator_name: str | None = Field(max_length=200)
    country_code: str | None = Field(
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
    )
    region: str | None = Field(max_length=120)
    support_email: EmailStr | None = Field(max_length=320)
    privacy_email: EmailStr | None = Field(max_length=320)
    copyright_email: EmailStr | None = Field(max_length=320)
    minimum_user_age: StrictInt | None = Field(ge=0, le=120)
    governing_law_jurisdiction: str | None = Field(max_length=200)

    @field_validator(
        "legal_operator_name",
        "region",
        "governing_law_jurisdiction",
        mode="before",
    )
    @classmethod
    def clean_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        _reject_control_characters(value)
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        _reject_control_characters(value)
        cleaned = " ".join(value.split()).upper()
        return cleaned or None

    @field_validator("country_code")
    @classmethod
    def valid_country_code(cls, value: str | None) -> str | None:
        if value is not None and value not in ISO_COUNTRY_CODES:
            raise ValueError("Country must be an assigned ISO 3166-1 alpha-2 code")
        return value

    @field_validator(
        "support_email",
        "privacy_email",
        "copyright_email",
        mode="before",
    )
    @classmethod
    def clean_email(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        _reject_control_characters(value)
        cleaned = value.strip()
        return cleaned or None


class LegalPolicyPutRequest(LegalPolicyEditable):
    revision: StrictInt = Field(ge=0)


class LegalPolicyAdminResponse(LegalPolicyEditable):
    schema_version: Literal[1] = 1
    revision: int = Field(ge=0)
    status: Literal["draft"] = "draft"
    updated_at: datetime | None = None
