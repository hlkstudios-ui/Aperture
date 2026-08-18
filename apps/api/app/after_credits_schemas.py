import uuid
from typing import Literal

from pydantic import BaseModel


class AfterCreditsModule(BaseModel):
    id: uuid.UUID
    kind: Literal[
        "ending_analysis",
        "easter_egg",
        "production_story",
        "behind_the_scenes",
        "deleted_scene",
        "commentary",
        "critical_essay",
    ]
    title: str
    body: str
    source_label: str


class AfterCreditsPerson(BaseModel):
    name: str
    slug: str
    role: str


class AfterCreditsRecommendation(BaseModel):
    kind: Literal["movie", "series", "episode"]
    title: str
    href: str
    reason: str


class AfterCreditsResponse(BaseModel):
    playback_source_id: uuid.UUID
    title: str
    unlocked: bool
    completed_at: str | None
    modules: list[AfterCreditsModule]
    people: list[AfterCreditsPerson]
    recommended_next: list[AfterCreditsRecommendation]
    community_available: bool = False
    safety_state: str
