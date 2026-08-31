from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MoneyAmount(BaseModel):
    amount: int
    currency: str


class RevenueSnapshot(BaseModel):
    provider: str
    connection: Literal["not_configured", "connected", "unavailable"]
    livemode: bool | None
    payouts_enabled: bool
    recorded_receipts: list[MoneyAmount]
    recorded_receipts_30d: list[MoneyAmount]
    available: list[MoneyAmount]
    pending: list[MoneyAmount]
    recent_payouts: list[dict]
    notice: str | None = None


class PayoutRequest(BaseModel):
    amount: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    confirmation: str
    request_id: UUID

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.lower()


class PayoutResponse(BaseModel):
    id: str
    amount: int
    currency: str
    status: str
    arrival_date: datetime | None
    livemode: bool
