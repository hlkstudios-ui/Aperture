import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BillingInterval, SubscriptionStatus
from app.schemas import RegisterRequest


class AccountModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PlanResponse(AccountModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    price_cents: int
    currency: str
    interval: BillingInterval
    max_streams: int
    max_resolution: str


class SubscriptionResponse(AccountModel):
    id: uuid.UUID
    status: SubscriptionStatus
    provider: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    plan: PlanResponse


class EntitlementResponse(AccountModel):
    key: str
    value: dict[str, Any]
    source: str
    starts_at: datetime | None
    ends_at: datetime | None


class SessionResponse(BaseModel):
    id: uuid.UUID
    current: bool
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class BillingState(BaseModel):
    provider: str
    production_ready: bool
    checkout_available: bool
    notice: str | None


class AccountDashboardResponse(BaseModel):
    email: str
    subscription: SubscriptionResponse | None
    entitlements: list[EntitlementResponse]
    sessions: list[SessionResponse]
    plans: list[PlanResponse]
    billing: BillingState


class CheckoutRequest(BaseModel):
    plan_code: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return RegisterRequest.strong_password(value)
