import uuid
from typing import Literal

from pydantic import BaseModel


class KnowledgeNode(BaseModel):
    id: str
    kind: str
    label: str
    href: str | None
    detail: str | None = None


class KnowledgeEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str


class FilmKnowledgeGraph(BaseModel):
    root_id: str
    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]
    derived_from: Literal["normalized_verified_catalog"] = "normalized_verified_catalog"


class CreditTitle(BaseModel):
    id: uuid.UUID
    kind: Literal["movie", "series", "episode"]
    title: str
    href: str
    role: str
    character_name: str | None


class CreditDestination(BaseModel):
    id: uuid.UUID
    kind: Literal["person", "company"]
    name: str
    slug: str
    biography: str | None = None
    country_code: str | None = None
    titles: list[CreditTitle]
