import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.club_models import (
    ClubMembershipStatus,
    ClubRole,
    PartyEventKind,
    PartyMessageKind,
    PartyState,
)


class ClubCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ClubJoin(BaseModel):
    invite_token: str = Field(min_length=32, max_length=200)


class ScheduleCreate(BaseModel):
    movie_id: uuid.UUID
    playback_source_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=160)
    scheduled_at: datetime

    @model_validator(mode="after")
    def timezone_required(self):
        if self.scheduled_at.tzinfo is None:
            raise ValueError("Scheduled time must include a timezone")
        return self


class PollOptionWrite(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    movie_id: uuid.UUID | None = None


class PollCreate(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    closes_at: datetime | None = None
    options: list[PollOptionWrite] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def timezone_required(self):
        if self.closes_at is not None and self.closes_at.tzinfo is None:
            raise ValueError("Poll close time must include a timezone")
        return self


class MembershipWrite(BaseModel):
    role: ClubRole = ClubRole.member
    status: ClubMembershipStatus = ClubMembershipStatus.active


class VoteWrite(BaseModel):
    option_id: uuid.UUID


class DiscussionWrite(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    contains_spoilers: bool = False


class ClubListWrite(BaseModel):
    collection_id: uuid.UUID


class PartyCreate(BaseModel):
    scheduled_watch_id: uuid.UUID


class PartyJoin(BaseModel):
    access_token: str = Field(min_length=32, max_length=200)


class PartyControl(BaseModel):
    kind: PartyEventKind
    position_seconds: float = Field(ge=0)
    expected_revision: int = Field(ge=0)


class PartyHeartbeat(BaseModel):
    client_position_seconds: float = Field(ge=0)
    expected_revision: int = Field(ge=0)


class PartyMessageWrite(BaseModel):
    kind: PartyMessageKind = PartyMessageKind.message
    body: str = Field(min_length=1, max_length=500)


class ClubResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    role: str
    members: list[dict]
    scheduled_watches: list[dict]
    polls: list[dict]
    discussion: list[dict]
    lists: list[dict]
    watch_history: list[dict]
    invite_token: str | None = None


class PartyResponse(BaseModel):
    id: uuid.UUID
    scheduled_watch_id: uuid.UUID
    playback_source_id: uuid.UUID
    host_profile_id: uuid.UUID
    state: PartyState
    position_seconds: float
    effective_position_seconds: float
    revision: int
    server_time: datetime
    state_changed_at: datetime
    correction_required: bool = False
    seek_to_seconds: float | None = None
    participants: list[dict]
    messages: list[dict]
    access_token: str | None = None
    watch_href: str
