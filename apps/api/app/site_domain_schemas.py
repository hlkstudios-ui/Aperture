from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SiteDomainStatusValue = Literal[
    "provisioning",
    "pending_dns",
    "pending_tls",
    "pending_edge",
    "active",
    "failed",
    "removing",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SiteDomainDnsRecord(StrictModel):
    type: Literal["CNAME", "TXT", "HTTP"]
    name: str = Field(min_length=1, max_length=2048)
    value: str = Field(min_length=1, max_length=4096)
    purpose: Literal["routing", "ownership", "tls"]


class SiteDomainResponse(StrictModel):
    id: UUID
    hostname: str
    status: SiteDomainStatusValue
    is_primary: bool
    revision: int = Field(ge=0)
    dns_records: list[SiteDomainDnsRecord]
    verified_at: datetime | None
    activated_at: datetime | None
    last_checked_at: datetime | None
    failure_reason: str | None


class SiteDomainCollectionResponse(StrictModel):
    revision: int = Field(ge=0)
    custom_domains_available: bool
    platform_hostname: str
    primary_domain_id: UUID | None
    domains: list[SiteDomainResponse]


class SiteDomainPublicResponse(StrictModel):
    primary_origin: str


class SiteDomainCreateRequest(StrictModel):
    hostname: str = Field(min_length=1, max_length=2048)


class SiteDomainMutationRequest(StrictModel):
    revision: int = Field(ge=0)
