from datetime import UTC, datetime

from sqlalchemy import and_, case, or_, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.catalog_models import CatalogStatus, Edition, Movie, Series


def utc_now() -> datetime:
    return datetime.now(UTC)


def synchronize_due_schedules(db: Session, now: datetime | None = None) -> None:
    """Materialize due publish/unpublish transitions using UTC-aware instants."""
    instant = now or utc_now()
    for model in (Movie, Series):
        due_publish = and_(
            model.publish_at.is_not(None),
            model.publish_at <= instant,
            model.status.in_((CatalogStatus.draft, CatalogStatus.ready)),
            or_(model.unpublish_at.is_(None), model.unpublish_at > instant),
        )
        due_unpublish = and_(
            model.unpublish_at.is_not(None),
            model.unpublish_at <= instant,
            model.status == CatalogStatus.published,
        )
        db.execute(
            update(model)
            .where(or_(due_publish, due_unpublish))
            .values(
                status=case(
                    (due_unpublish, CatalogStatus.archived),
                    (due_publish, CatalogStatus.published),
                    else_=model.status,
                )
            )
        )
    db.commit()


def availability_clause(
    model: type[Movie] | type[Series],
    now: datetime | None = None,
    country: str | None = None,
) -> ColumnElement[bool]:
    instant = now or utc_now()
    return and_(
        model.status == CatalogStatus.published,
        or_(model.rights_start_at.is_(None), model.rights_start_at <= instant),
        or_(model.rights_end_at.is_(None), model.rights_end_at > instant),
        territory_clause(model, country),
    )


def territory_clause(
    model: type[Movie] | type[Series] | type[Edition], country: str | None
) -> ColumnElement[bool]:
    """Empty allowlists are global; restricted records require a trusted country."""
    globally_licensed = model.allowed_territories == []
    if country is None:
        return globally_licensed
    return or_(globally_licensed, model.allowed_territories.contains([country]))
