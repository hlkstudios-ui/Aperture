import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.auth import DbSession, require_admin, require_trusted_origin
from app.catalog_models import (
    Artwork,
    Character,
    Company,
    Country,
    Credit,
    Edition,
    EditionDifference,
    Episode,
    Franchise,
    Genre,
    Language,
    Movie,
    Person,
    Season,
    Series,
    Tag,
    Theme,
    TitleRelationship,
    TrailerClip,
)
from app.catalog_schemas import (
    ArtworkCreate,
    ArtworkResponse,
    ArtworkUpdate,
    CreditCreate,
    CreditResponse,
    CreditUpdate,
    EditionCreate,
    EditionDifferenceCreate,
    EditionDifferenceResponse,
    EditionResponse,
    EditionUpdate,
    EpisodeCreate,
    EpisodeResponse,
    EpisodeUpdate,
    LocaleCreate,
    LocaleResponse,
    LocaleUpdate,
    MovieCreate,
    MovieResponse,
    MovieUpdate,
    NamedRecordCreate,
    NamedRecordResponse,
    NamedRecordUpdate,
    PreviewCreate,
    PreviewResponse,
    PreviewUpdate,
    SeasonCreate,
    SeasonResponse,
    SeasonUpdate,
    SeriesCreate,
    SeriesResponse,
    SeriesUpdate,
    TitleRelationshipCreate,
    TitleRelationshipResponse,
)
from app.catalog_service import (
    apply_update,
    commit,
    create_movie,
    create_series,
    get_or_404,
    movie_query,
    series_query,
    update_movie,
    update_series,
)
from app.models import Admin, AuditLog

router = APIRouter(
    prefix="/admin/catalog",
    tags=["administrator catalog"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


def record_audit(db: DbSession, request: Request, admin: Admin, action: str, record: Any) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action=action,
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail={"record_id": str(getattr(record, "id", getattr(record, "code", "unknown")))},
        )
    )


@router.get("/movies", response_model=list[MovieResponse])
def list_movies(db: DbSession) -> list[Movie]:
    return list(db.scalars(movie_query().order_by(Movie.updated_at.desc())).unique())


@router.post("/movies", response_model=MovieResponse, status_code=status.HTTP_201_CREATED)
def add_movie(payload: MovieCreate, request: Request, db: DbSession, admin: AdminIdentity) -> Movie:
    movie = create_movie(db, payload)
    record_audit(db, request, admin, "catalog.movie.created", movie)
    db.commit()
    return movie


@router.get("/movies/{movie_id}", response_model=MovieResponse)
def get_movie(movie_id: uuid.UUID, db: DbSession) -> Movie:
    movie = db.scalar(movie_query().where(Movie.id == movie_id))
    return movie if movie else get_or_404(db, Movie, movie_id)


@router.patch("/movies/{movie_id}", response_model=MovieResponse)
def edit_movie(
    movie_id: uuid.UUID,
    payload: MovieUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> Movie:
    movie = get_or_404(db, Movie, movie_id)
    movie = update_movie(db, movie, payload)
    record_audit(db, request, admin, "catalog.movie.updated", movie)
    db.commit()
    return movie


@router.delete("/movies/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_movie(
    movie_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> None:
    movie = get_or_404(db, Movie, movie_id)
    record_audit(db, request, admin, "catalog.movie.deleted", movie)
    db.delete(movie)
    db.commit()


@router.get("/series", response_model=list[SeriesResponse])
def list_series(db: DbSession) -> list[Series]:
    return list(db.scalars(series_query().order_by(Series.updated_at.desc())).unique())


@router.post("/series", response_model=SeriesResponse, status_code=status.HTTP_201_CREATED)
def add_series(
    payload: SeriesCreate, request: Request, db: DbSession, admin: AdminIdentity
) -> Series:
    series = create_series(db, payload)
    record_audit(db, request, admin, "catalog.series.created", series)
    db.commit()
    return series


@router.get("/series/{series_id}", response_model=SeriesResponse)
def get_series(series_id: uuid.UUID, db: DbSession) -> Series:
    series = db.scalar(series_query().where(Series.id == series_id))
    return series if series else get_or_404(db, Series, series_id)


@router.patch("/series/{series_id}", response_model=SeriesResponse)
def edit_series(
    series_id: uuid.UUID,
    payload: SeriesUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> Series:
    series = update_series(db, get_or_404(db, Series, series_id), payload)
    record_audit(db, request, admin, "catalog.series.updated", series)
    db.commit()
    return series


@router.delete("/series/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_series(
    series_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> None:
    series = get_or_404(db, Series, series_id)
    record_audit(db, request, admin, "catalog.series.deleted", series)
    db.delete(series)
    db.commit()


@router.get("/seasons", response_model=list[SeasonResponse])
def list_seasons(db: DbSession) -> list[Season]:
    return list(db.scalars(select(Season).order_by(Season.series_id, Season.number)))


@router.get("/seasons/{season_id}", response_model=SeasonResponse)
def get_season(season_id: uuid.UUID, db: DbSession) -> Season:
    return get_or_404(db, Season, season_id)


@router.post("/seasons", response_model=SeasonResponse, status_code=status.HTTP_201_CREATED)
def add_season(
    payload: SeasonCreate, request: Request, db: DbSession, admin: AdminIdentity
) -> Season:
    get_or_404(db, Series, payload.series_id)
    season = Season(**payload.model_dump())
    db.add(season)
    commit(db, "This season number already exists for the series")
    record_audit(db, request, admin, "catalog.season.created", season)
    db.commit()
    return season


@router.patch("/seasons/{season_id}", response_model=SeasonResponse)
def edit_season(
    season_id: uuid.UUID,
    payload: SeasonUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> Season:
    season = get_or_404(db, Season, season_id)
    apply_update(season, payload)
    commit(db, "This season number already exists for the series")
    record_audit(db, request, admin, "catalog.season.updated", season)
    db.commit()
    return season


@router.delete("/seasons/{season_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_season(
    season_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> None:
    season = get_or_404(db, Season, season_id)
    record_audit(db, request, admin, "catalog.season.deleted", season)
    db.delete(season)
    db.commit()


@router.get("/episodes", response_model=list[EpisodeResponse])
def list_episodes(db: DbSession) -> list[Episode]:
    return list(db.scalars(select(Episode).order_by(Episode.season_id, Episode.number)))


@router.get("/episodes/{episode_id}", response_model=EpisodeResponse)
def get_episode(episode_id: uuid.UUID, db: DbSession) -> Episode:
    return get_or_404(db, Episode, episode_id)


@router.post("/episodes", response_model=EpisodeResponse, status_code=status.HTTP_201_CREATED)
def add_episode(
    payload: EpisodeCreate, request: Request, db: DbSession, admin: AdminIdentity
) -> Episode:
    get_or_404(db, Season, payload.season_id)
    episode = Episode(**payload.model_dump())
    db.add(episode)
    commit(db, "This episode number already exists for the season")
    record_audit(db, request, admin, "catalog.episode.created", episode)
    db.commit()
    return episode


@router.patch("/episodes/{episode_id}", response_model=EpisodeResponse)
def edit_episode(
    episode_id: uuid.UUID,
    payload: EpisodeUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> Episode:
    episode = get_or_404(db, Episode, episode_id)
    apply_update(episode, payload)
    commit(db, "This episode number already exists for the season")
    record_audit(db, request, admin, "catalog.episode.updated", episode)
    db.commit()
    return episode


@router.delete("/episodes/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_episode(
    episode_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> None:
    episode = get_or_404(db, Episode, episode_id)
    record_audit(db, request, admin, "catalog.episode.deleted", episode)
    db.delete(episode)
    db.commit()


NAMED_RESOURCES = {
    "genres": Genre,
    "themes": Theme,
    "tags": Tag,
    "franchises": Franchise,
    "companies": Company,
    "people": Person,
    "characters": Character,
}


def named_model(resource: str):
    model = NAMED_RESOURCES.get(resource)
    if model is None:
        from fastapi import HTTPException

        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catalog resource was not found")
    return model


@router.get("/named/{resource}", response_model=list[NamedRecordResponse])
def list_named(resource: str, db: DbSession):
    model = named_model(resource)
    return list(db.scalars(select(model).order_by(model.name)))


@router.post(
    "/named/{resource}", response_model=NamedRecordResponse, status_code=status.HTTP_201_CREATED
)
def add_named(
    resource: str,
    payload: NamedRecordCreate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    model = named_model(resource)
    record = model(**payload.model_dump())
    db.add(record)
    commit(db, f"A {model.__name__.lower()} with this slug already exists")
    record_audit(db, request, admin, f"catalog.{model.__name__.lower()}.created", record)
    db.commit()
    return record


@router.patch("/named/{resource}/{record_id}", response_model=NamedRecordResponse)
def edit_named(
    resource: str,
    record_id: uuid.UUID,
    payload: NamedRecordUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    model = named_model(resource)
    record = get_or_404(db, model, record_id)
    apply_update(record, payload)
    commit(db, f"A {model.__name__.lower()} with this slug already exists")
    record_audit(db, request, admin, f"catalog.{model.__name__.lower()}.updated", record)
    db.commit()
    return record


@router.delete("/named/{resource}/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_named(
    resource: str,
    record_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> None:
    model = named_model(resource)
    record = get_or_404(db, model, record_id)
    record_audit(db, request, admin, f"catalog.{model.__name__.lower()}.deleted", record)
    db.delete(record)
    db.commit()


LOCALE_RESOURCES = {"languages": Language, "countries": Country}


@router.get("/locales/{resource}", response_model=list[LocaleResponse])
def list_locales(resource: str, db: DbSession):
    model = LOCALE_RESOURCES.get(resource)
    if model is None:
        return []
    return list(db.scalars(select(model).order_by(model.name)))


@router.post(
    "/locales/{resource}", response_model=LocaleResponse, status_code=status.HTTP_201_CREATED
)
def add_locale(
    resource: str,
    payload: LocaleCreate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    model = LOCALE_RESOURCES.get(resource)
    if model is None:
        from fastapi import HTTPException

        raise HTTPException(status.HTTP_404_NOT_FOUND, "Locale resource was not found")
    record = model(**payload.model_dump())
    db.add(record)
    commit(db, "This locale already exists")
    record_audit(db, request, admin, f"catalog.{model.__name__.lower()}.created", record)
    db.commit()
    return record


@router.patch("/locales/{resource}/{code}", response_model=LocaleResponse)
def edit_locale(
    resource: str,
    code: str,
    payload: LocaleUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    model = LOCALE_RESOURCES.get(resource)
    if model is None:
        from fastapi import HTTPException

        raise HTTPException(status.HTTP_404_NOT_FOUND, "Locale resource was not found")
    record = get_or_404(db, model, code)
    apply_update(record, payload)
    commit(db, "A locale with this name already exists")
    record_audit(db, request, admin, f"catalog.{model.__name__.lower()}.updated", record)
    db.commit()
    return record


@router.delete("/locales/{resource}/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_locale(
    resource: str, code: str, request: Request, db: DbSession, admin: AdminIdentity
) -> None:
    model = LOCALE_RESOURCES.get(resource)
    if model is None:
        from fastapi import HTTPException

        raise HTTPException(status.HTTP_404_NOT_FOUND, "Locale resource was not found")
    record = get_or_404(db, model, code)
    record_audit(db, request, admin, f"catalog.{model.__name__.lower()}.deleted", record)
    db.delete(record)
    commit(db, "This locale is still referenced by catalog records")


COMPONENTS = {
    "editions": (Edition, EditionCreate, EditionResponse),
    "credits": (Credit, CreditCreate, CreditResponse),
    "artwork": (Artwork, ArtworkCreate, ArtworkResponse),
    "previews": (TrailerClip, PreviewCreate, PreviewResponse),
}


@router.get("/editions", response_model=list[EditionResponse])
def list_editions(db: DbSession):
    return list(db.scalars(select(Edition)))


@router.post("/editions", response_model=EditionResponse, status_code=status.HTTP_201_CREATED)
def add_edition(payload: EditionCreate, request: Request, db: DbSession, admin: AdminIdentity):
    record = Edition(**payload.model_dump())
    db.add(record)
    commit(db, "This edition already exists or has an invalid parent")
    record_audit(db, request, admin, "catalog.edition.created", record)
    db.commit()
    return record


@router.get("/editions/{record_id}", response_model=EditionResponse)
def get_edition(record_id: uuid.UUID, db: DbSession):
    return get_or_404(db, Edition, record_id)


@router.patch("/editions/{record_id}", response_model=EditionResponse)
def edit_edition(
    record_id: uuid.UUID,
    payload: EditionUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    record = get_or_404(db, Edition, record_id)
    apply_update(record, payload)
    commit(db, "This edition already exists or has an invalid parent")
    record_audit(db, request, admin, "catalog.edition.updated", record)
    db.commit()
    return record


@router.get("/edition-differences", response_model=list[EditionDifferenceResponse])
def list_edition_differences(db: DbSession):
    return list(db.scalars(select(EditionDifference)))


@router.post(
    "/edition-differences",
    response_model=EditionDifferenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_edition_difference(
    payload: EditionDifferenceCreate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    source = get_or_404(db, Edition, payload.source_edition_id)
    target = get_or_404(db, Edition, payload.target_edition_id)
    if source.movie_id != target.movie_id or source.episode_id != target.episode_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Compared editions must belong to the same title",
        )
    record = EditionDifference(**payload.model_dump())
    db.add(record)
    commit(db, "This verified edition difference already exists")
    record_audit(db, request, admin, "catalog.edition_difference.created", record)
    db.commit()
    return record


@router.get("/title-relationships", response_model=list[TitleRelationshipResponse])
def list_title_relationships(db: DbSession):
    return list(db.scalars(select(TitleRelationship).order_by(TitleRelationship.kind)))


@router.post(
    "/title-relationships",
    response_model=TitleRelationshipResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_title_relationship(
    payload: TitleRelationshipCreate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    get_or_404(db, Movie, payload.source_movie_id)
    get_or_404(db, Movie, payload.target_movie_id)
    record = TitleRelationship(**payload.model_dump())
    db.add(record)
    commit(db, "This title relationship already exists")
    record_audit(db, request, admin, "catalog.title_relationship.created", record)
    db.commit()
    return record


@router.delete("/title-relationships/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_title_relationship(
    record_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> None:
    record = get_or_404(db, TitleRelationship, record_id)
    record_audit(db, request, admin, "catalog.title_relationship.deleted", record)
    db.delete(record)
    db.commit()


@router.get("/credits", response_model=list[CreditResponse])
def list_credits(db: DbSession):
    return list(db.scalars(select(Credit)))


@router.post("/credits", response_model=CreditResponse, status_code=status.HTTP_201_CREATED)
def add_credit(payload: CreditCreate, request: Request, db: DbSession, admin: AdminIdentity):
    record = Credit(**payload.model_dump())
    db.add(record)
    commit(db, "The credit references invalid catalog records")
    record_audit(db, request, admin, "catalog.credit.created", record)
    db.commit()
    return record


@router.get("/credits/{record_id}", response_model=CreditResponse)
def get_credit(record_id: uuid.UUID, db: DbSession):
    return get_or_404(db, Credit, record_id)


@router.patch("/credits/{record_id}", response_model=CreditResponse)
def edit_credit(
    record_id: uuid.UUID,
    payload: CreditUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    record = get_or_404(db, Credit, record_id)
    apply_update(record, payload)
    commit(db, "The credit references invalid catalog records")
    record_audit(db, request, admin, "catalog.credit.updated", record)
    db.commit()
    return record


@router.get("/artwork", response_model=list[ArtworkResponse])
def list_artwork(db: DbSession):
    return list(db.scalars(select(Artwork)))


@router.post("/artwork", response_model=ArtworkResponse, status_code=status.HTTP_201_CREATED)
def add_artwork(payload: ArtworkCreate, request: Request, db: DbSession, admin: AdminIdentity):
    record = Artwork(**payload.model_dump())
    db.add(record)
    commit(db, "The artwork references an invalid catalog record")
    record_audit(db, request, admin, "catalog.artwork.created", record)
    db.commit()
    return record


@router.get("/artwork/{record_id}", response_model=ArtworkResponse)
def get_artwork(record_id: uuid.UUID, db: DbSession):
    return get_or_404(db, Artwork, record_id)


@router.patch("/artwork/{record_id}", response_model=ArtworkResponse)
def edit_artwork(
    record_id: uuid.UUID,
    payload: ArtworkUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    record = get_or_404(db, Artwork, record_id)
    apply_update(record, payload)
    commit(db, "The artwork references an invalid catalog record")
    record_audit(db, request, admin, "catalog.artwork.updated", record)
    db.commit()
    return record


@router.get("/previews", response_model=list[PreviewResponse])
def list_previews(db: DbSession):
    return list(db.scalars(select(TrailerClip)))


@router.post("/previews", response_model=PreviewResponse, status_code=status.HTTP_201_CREATED)
def add_preview(payload: PreviewCreate, request: Request, db: DbSession, admin: AdminIdentity):
    record = TrailerClip(**payload.model_dump())
    db.add(record)
    commit(db, "The preview references an invalid catalog record")
    record_audit(db, request, admin, "catalog.preview.created", record)
    db.commit()
    return record


@router.get("/previews/{record_id}", response_model=PreviewResponse)
def get_preview(record_id: uuid.UUID, db: DbSession):
    return get_or_404(db, TrailerClip, record_id)


@router.patch("/previews/{record_id}", response_model=PreviewResponse)
def edit_preview(
    record_id: uuid.UUID,
    payload: PreviewUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    record = get_or_404(db, TrailerClip, record_id)
    apply_update(record, payload)
    commit(db, "The preview references an invalid catalog record")
    record_audit(db, request, admin, "catalog.preview.updated", record)
    db.commit()
    return record


@router.delete("/{resource}/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_component(
    resource: str,
    record_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> None:
    component = COMPONENTS.get(resource)
    if component is None:
        from fastapi import HTTPException

        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catalog component was not found")
    record = get_or_404(db, component[0], record_id)
    record_audit(db, request, admin, f"catalog.{component[0].__name__.lower()}.deleted", record)
    db.delete(record)
    db.commit()
