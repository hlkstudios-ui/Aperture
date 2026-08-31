import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BillingInterval

PLAN_CODE_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
MAX_PLAN_PRICE_CENTS = 100_000_000
PlanResolution = Literal["720p", "1080p", "4K"]
PlanCurrency = Literal["AUD", "CAD", "EUR", "GBP", "USD"]


class ViewerPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=64, pattern=PLAN_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    price_cents: int = Field(gt=0, le=MAX_PLAN_PRICE_CENTS, strict=True)
    currency: PlanCurrency
    interval: BillingInterval
    max_streams: int = Field(ge=1, le=100, strict=True)
    max_resolution: PlanResolution

    @field_validator("name", "description")
    @classmethod
    def normalize_copy(cls, value: str) -> str:
        if re.search(r"[\x00-\x1f\x7f-\x9f]", value):
            raise ValueError("Plan copy contains unsupported control characters")
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Plan copy cannot be blank")
        return normalized


class ViewerPlanAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str
    price_cents: int
    currency: str
    interval: BillingInterval
    max_streams: int
    max_resolution: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ViewerPlanArchive(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    confirmation_code: str = Field(min_length=1, max_length=64)
