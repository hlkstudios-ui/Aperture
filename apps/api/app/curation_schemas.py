import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.curation_models import CollectionKind, CurationStatus


class CurationModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TitleInput(BaseModel):
    movie_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    note: str | None = None

    @model_validator(mode="after")
    def one_title(self):
        if (self.movie_id is None) == (self.series_id is None):
            raise ValueError("Exactly one movie_id or series_id is required")
        return self


class CollectionWrite(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    kind: CollectionKind = CollectionKind.editorial
    status: CurationStatus = CurationStatus.draft
    items: list[TitleInput] = Field(default_factory=list, max_length=500)


class TitleCard(CurationModel):
    item_id: uuid.UUID
    title_id: uuid.UUID
    kind: str
    slug: str
    title: str
    short_description: str
    position: int
    note: str | None = None
    completed: bool = False


class CollectionResponse(CurationModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str
    kind: CollectionKind
    status: CurationStatus
    owner_profile_id: uuid.UUID | None = None
    owner_profile_name: str | None = None
    visibility: str = "private"
    moderation_status: str = "pending"
    items: list[TitleCard]


class UserListWrite(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    visibility: str = Field(default="private", pattern="^(private|unlisted|public)$")
    items: list[TitleInput] = Field(default_factory=list, max_length=500)


class JourneyChapterWrite(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    introduction: str | None = None
    items: list[TitleInput] = Field(default_factory=list, max_length=500)


class JourneyWrite(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    title: str = Field(min_length=1, max_length=200)
    description: str
    status: CurationStatus = CurationStatus.draft
    chapters: list[JourneyChapterWrite] = Field(default_factory=list, max_length=100)


class JourneyChapterResponse(CurationModel):
    title: str
    introduction: str | None
    position: int
    items: list[TitleCard]


class JourneyResponse(CurationModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str
    status: CurationStatus
    chapters: list[JourneyChapterResponse]
    completed_items: int = 0
    total_items: int = 0
    completed: bool = False


class ProgressWrite(BaseModel):
    journey_item_id: uuid.UUID
    completed: bool
