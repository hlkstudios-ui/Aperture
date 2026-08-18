import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PassportDistribution(BaseModel):
    key: str
    label: str
    count: int
    percentage: float


class PassportCreator(BaseModel):
    person_id: uuid.UUID
    name: str
    roles: list[str]
    completed_views: int


class PassportHistoryItem(BaseModel):
    kind: Literal["movie", "episode"]
    title: str
    parent_title: str | None = None
    activity_number: int
    is_rewatch: bool
    watched_seconds: float
    completed: bool
    started_at: datetime
    completed_at: datetime | None


class PassportReport(BaseModel):
    profile_id: uuid.UUID
    year: int | None
    available_years: list[int]
    generated_from: Literal["viewing_activities"] = "viewing_activities"
    privacy: Literal["private_to_profile"] = "private_to_profile"
    films_watched: int
    episodes_watched: int
    completed_views: int
    first_watches: int
    rewatches: int
    observed_watch_hours: float
    countries_explored: int
    longest_title: str | None
    shortest_title: str | None
    favorite_genres: list[PassportDistribution]
    favorite_creators: list[PassportCreator]
    country_distribution: list[PassportDistribution]
    decade_distribution: list[PassportDistribution]
    history: list[PassportHistoryItem]
    milestones: list[str]
