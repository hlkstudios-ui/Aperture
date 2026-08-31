import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import DbSession, require_admin, require_trusted_origin
from app.catalog_models import CatalogStatus, Genre, Movie
from app.models import Admin, AuditLog
from app.search_schemas import UniversalTitleResult
from app.tmdb_discovery import search_tmdb, tmdb_movie_import_data, tmdb_trending

router = APIRouter(
    prefix="/admin/tmdb",
    tags=["administrator TMDB discovery"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


class TmdbMovieSearch(BaseModel):
    query: str
    total: int
    results: list[UniversalTitleResult]


class TmdbMovieImport(BaseModel):
    external_id: str


class TmdbTrendingTitle(BaseModel):
    external_id: str
    title: str
    overview: str
    release_date: str | None
    poster_url: str | None
    backdrop_url: str | None
    popularity: float
    vote_average: float


class TmdbTrendingPulse(BaseModel):
    available: bool
    movies: list[TmdbTrendingTitle]
    series: list[TmdbTrendingTitle]


def slugify(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.lower()))


@router.get("/movies", response_model=TmdbMovieSearch)
def search_movies(q: str = Query(min_length=2, max_length=120), page: int = Query(1, ge=1, le=500)):
    results, total = search_tmdb(q, page)
    return TmdbMovieSearch(
        query=q,
        total=total,
        results=[result for result in results if result.kind == "movie"],
    )


@router.get("/trending", response_model=TmdbTrendingPulse)
def trending_pulse():
    return tmdb_trending()


@router.post("/movies/import", status_code=status.HTTP_201_CREATED)
def import_movie(
    payload: TmdbMovieImport,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> dict[str, str]:
    requested_id = payload.external_id.strip()
    if not requested_id or len(requested_id) > 200:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Movie identity is invalid")
    provider = "aperture_movie_api" if requested_id.startswith("amt_") else "tmdb"
    external_id = requested_id
    if requested_id.startswith("tmdb:movie:"):
        external_id = requested_id.rsplit(":", 1)[-1]
    if provider == "tmdb" and not external_id.isdigit():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Movie identity is invalid")
    existing = db.scalar(
        select(Movie).where(
            Movie.metadata_provider == provider,
            Movie.external_id == external_id,
        )
    )
    if existing:
        return {"id": str(existing.id), "status": "existing"}
    data = tmdb_movie_import_data(external_id)
    if data is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "TMDB movie details are unavailable")
    base_slug = f"{slugify(data['title'])}-{external_id[:24].lower()}"
    genres = list(db.scalars(select(Genre).where(Genre.name.in_(data["genres"]))))
    movie = Movie(
        title=data["title"],
        slug=base_slug,
        original_title=data["original_title"],
        short_description=data["overview"][:500],
        synopsis=data["overview"],
        release_date=date.fromisoformat(data["release_date"]) if data["release_date"] else None,
        runtime_minutes=data["runtime_minutes"],
        status=CatalogStatus.draft,
        original_language_code=data["original_language_code"],
        country_code=data["country_code"],
        metadata_provider=provider,
        external_id=external_id,
        poster_url=data["poster_url"],
        backdrop_url=data["backdrop_url"],
        content_format="movie",
        studios=data["studios"],
        genres=genres,
    )
    db.add(movie)
    db.flush()
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action="catalog.movie.imported",
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail={"movie_id": str(movie.id), "provider": provider, "external_id": external_id},
        )
    )
    db.commit()
    return {"id": str(movie.id), "status": "imported"}
