import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SupportModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserStateUpdate(SupportModel):
    is_active: bool
    reason: str = Field(min_length=3, max_length=500)


class SessionRevocation(SupportModel):
    reason: str = Field(min_length=3, max_length=500)


class CustomerDeletionRequest(SupportModel):
    confirmation_email: EmailStr
    confirmation_phrase: str
    reason: str = Field(min_length=10, max_length=500)
    authorization_reference: str = Field(min_length=3, max_length=200)


class SupportUserSummary(SupportModel):
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime
    profile_count: int
    active_session_count: int
    subscription_status: str | None
    plan_name: str | None


class SupportUserList(SupportModel):
    items: list[SupportUserSummary]
    total: int


class SupportSubscription(SupportModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    plan_name: str
    plan_code: str
    status: str
    provider: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    updated_at: datetime


class SupportSubscriptionList(SupportModel):
    items: list[SupportSubscription]
    total: int
