from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ViewerMonetizationStatus(StrictModel):
    schema_version: Literal[1] = 1
    revision: int = Field(ge=0)
    access_mode: Literal["free", "subscription_required"]
    access_mode_change_available: bool
    provider: Literal["disabled", "stripe_connect"]
    connection: Literal[
        "disabled",
        "not_connected",
        "onboarding_required",
        "restricted",
        "ready",
    ]
    connected_account_id: str | None
    livemode: bool | None
    details_submitted: bool
    charges_enabled: bool
    payouts_enabled: bool
    requirements_due: list[str]
    active_plan_count: int = Field(ge=0)
    subscription_mode_eligible: bool
    updated_at: datetime | None
    notice: str | None


class StripeConnectOnboardingResponse(StrictModel):
    onboarding_url: str
    expires_at: int | None = Field(default=None, ge=0)
