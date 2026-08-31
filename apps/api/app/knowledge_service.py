from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.catalog_models import (
    CatalogStatus,
    Character,
    Company,
    Country,
    Credit,
    Episode,
    Franchise,
    Language,
    Movie,
    Person,
    Season,
    Series,
    TitleRelationship,
)
from app.catalog_service import movie_query
from app.catalog_visibility import public_title_conditions
from app.knowledge_schemas import (
    CreditDestination,
    CreditTitle,
    FilmKnowledgeGraph,
    KnowledgeEdge,
    KnowledgeNode,
)


def film_graph(db: Session, movie: Movie, country: str | None = None) -> FilmKnowledgeGraph:
    root_id = f"movie:{movie.id}"
    nodes: dict[str, KnowledgeNode] = {
        root_id: KnowledgeNode(
            id=root_id,
            kind="movie",
            label=movie.title,
            href=f"/movies/{movie.slug}",
            detail="Current film",
        )
    }
    edges: dict[str, KnowledgeEdge] = {}

    def connect(kind: str, key: str, label: str, edge_label: str, href: str | None) -> str:
        node_id = f"{kind}:{key}"
        nodes[node_id] = KnowledgeNode(id=node_id, kind=kind, label=label, href=href)
        edge_id = f"{root_id}|{edge_label}|{node_id}"
        edges[edge_id] = KnowledgeEdge(id=edge_id, source=root_id, target=node_id, label=edge_label)
        return node_id

    for genre in movie.genres:
        connect("genre", str(genre.id), genre.name, "genre", f"/search?q={genre.slug}")
    for theme in movie.themes:
        connect("theme", str(theme.id), theme.name, "theme", f"/search?q={theme.slug}")
    if movie.franchise_id:
        franchise = db.get(Franchise, movie.franchise_id)
        if franchise:
            franchise_id = connect(
                "franchise",
                str(franchise.id),
                franchise.name,
                "franchise",
                f"/search?q={franchise.slug}",
            )
            related = db.scalars(
                movie_query().where(
                    Movie.franchise_id == franchise.id,
                    Movie.id != movie.id,
                    *public_title_conditions(Movie, country=country),
                )
            ).unique()
            for item in related:
                node_id = f"movie:{item.id}"
                nodes[node_id] = KnowledgeNode(
                    id=node_id,
                    kind="movie",
                    label=item.title,
                    href=f"/movies/{item.slug}",
                    detail="Related franchise title",
                )
                edge_id = f"{franchise_id}|contains|{node_id}"
                edges[edge_id] = KnowledgeEdge(
                    id=edge_id, source=franchise_id, target=node_id, label="contains"
                )
    if movie.country_code:
        country = db.get(Country, movie.country_code)
        connect(
            "country",
            movie.country_code,
            country.name if country else movie.country_code,
            "country",
            f"/search?q={movie.country_code}",
        )
    if movie.original_language_code:
        language = db.get(Language, movie.original_language_code)
        connect(
            "language",
            movie.original_language_code,
            language.name if language else movie.original_language_code,
            "original language",
            f"/search?q={movie.original_language_code}",
        )
    credits = list(
        db.scalars(
            select(Credit)
            .where(Credit.movie_id == movie.id)
            .order_by(Credit.billing_order.asc().nullslast(), Credit.id)
        )
    )
    for credit in credits:
        person = db.get(Person, credit.person_id)
        if person:
            person_id = connect(
                "person",
                str(person.id),
                person.name,
                credit.role,
                f"/people/{person.slug}",
            )
            if credit.character_id:
                character = db.get(Character, credit.character_id)
                if character:
                    character_id = f"character:{character.id}"
                    nodes[character_id] = KnowledgeNode(
                        id=character_id,
                        kind="character",
                        label=character.name,
                        href=f"/search?q={character.slug}",
                    )
                    edge_id = f"{person_id}|portrays|{character_id}"
                    edges[edge_id] = KnowledgeEdge(
                        id=edge_id,
                        source=person_id,
                        target=character_id,
                        label="portrays",
                    )
        if credit.company_id:
            company = db.get(Company, credit.company_id)
            if company:
                connect(
                    "company",
                    str(company.id),
                    company.name,
                    "company",
                    f"/companies/{company.slug}",
                )
    person_ids = {credit.person_id for credit in credits}
    if person_ids:
        related_credits = db.scalars(
            select(Credit).where(Credit.person_id.in_(person_ids), Credit.movie_id.is_not(None))
        )
        for related_credit in related_credits:
            if related_credit.movie_id == movie.id:
                continue
            related_movie = db.scalar(
                movie_query().where(
                    Movie.id == related_credit.movie_id,
                    *public_title_conditions(Movie, country=country),
                )
            )
            person = db.get(Person, related_credit.person_id)
            if related_movie and person:
                node_id = f"movie:{related_movie.id}"
                nodes[node_id] = KnowledgeNode(
                    id=node_id,
                    kind="movie",
                    label=related_movie.title,
                    href=f"/movies/{related_movie.slug}",
                    detail=f"Also connected to {person.name}",
                )
                edge_id = f"person:{person.id}|credits|{node_id}"
                edges[edge_id] = KnowledgeEdge(
                    id=edge_id,
                    source=f"person:{person.id}",
                    target=node_id,
                    label=related_credit.role,
                )
    relationships = db.scalars(
        select(TitleRelationship)
        .where(
            or_(
                TitleRelationship.source_movie_id == movie.id,
                TitleRelationship.target_movie_id == movie.id,
            ),
            TitleRelationship.manually_verified.is_(True),
        )
        .order_by(TitleRelationship.kind, TitleRelationship.id)
    )
    for relationship in relationships:
        other_id = (
            relationship.target_movie_id
            if relationship.source_movie_id == movie.id
            else relationship.source_movie_id
        )
        other = db.scalar(
            movie_query().where(
                Movie.id == other_id,
                *public_title_conditions(Movie, country=country),
            )
        )
        if other is None:
            continue
        other_node_id = f"movie:{other.id}"
        nodes[other_node_id] = KnowledgeNode(
            id=other_node_id,
            kind="movie",
            label=other.title,
            href=f"/movies/{other.slug}",
            detail=relationship.description or "Verified editorial relationship",
        )
        source_id = f"movie:{relationship.source_movie_id}"
        target_id = f"movie:{relationship.target_movie_id}"
        edge_id = f"{source_id}|{relationship.kind.value}|{target_id}"
        edges[edge_id] = KnowledgeEdge(
            id=edge_id,
            source=source_id,
            target=target_id,
            label=relationship.kind.value.replace("_", " "),
        )
    return FilmKnowledgeGraph(
        root_id=root_id,
        nodes=sorted(nodes.values(), key=lambda item: (item.kind, item.label.casefold(), item.id)),
        edges=sorted(edges.values(), key=lambda item: (item.label, item.id)),
    )


def credit_destination(
    db: Session, *, kind: str, slug: str, country: str | None = None
) -> CreditDestination | None:
    model = Person if kind == "person" else Company
    record = db.scalar(select(model).where(model.slug == slug))
    if record is None:
        return None
    statement = select(Credit).where(
        Credit.person_id == record.id if kind == "person" else Credit.company_id == record.id
    )
    titles = []
    for credit in db.scalars(statement.order_by(Credit.billing_order.asc().nullslast(), Credit.id)):
        character = db.get(Character, credit.character_id) if credit.character_id else None
        if credit.movie_id:
            movie = db.scalar(
                movie_query().where(
                    Movie.id == credit.movie_id,
                    *public_title_conditions(Movie, country=country),
                )
            )
            if movie:
                titles.append(
                    CreditTitle(
                        id=movie.id,
                        kind="movie",
                        title=movie.title,
                        href=f"/movies/{movie.slug}",
                        role=credit.role,
                        character_name=character.name if character else None,
                    )
                )
        elif credit.series_id:
            series = db.scalar(
                select(Series).where(
                    Series.id == credit.series_id,
                    *public_title_conditions(Series, country=country),
                )
            )
            if series:
                titles.append(
                    CreditTitle(
                        id=series.id,
                        kind="series",
                        title=series.title,
                        href=f"/series/{series.slug}",
                        role=credit.role,
                        character_name=character.name if character else None,
                    )
                )
        elif credit.episode_id:
            result = db.execute(
                select(Episode, Season, Series)
                .join(Season, Episode.season_id == Season.id)
                .join(Series, Season.series_id == Series.id)
                .where(
                    Episode.id == credit.episode_id,
                    Episode.status == CatalogStatus.published,
                    *public_title_conditions(Series, country=country),
                )
            ).one_or_none()
            if result:
                episode, season, series = result
                titles.append(
                    CreditTitle(
                        id=episode.id,
                        kind="episode",
                        title=(
                            f"{series.title} · S{season.number} E{episode.number} · {episode.title}"
                        ),
                        href=f"/series/{series.slug}",
                        role=credit.role,
                        character_name=character.name if character else None,
                    )
                )
    return CreditDestination(
        id=record.id,
        kind=kind,
        name=record.name,
        slug=record.slug,
        biography=record.biography if kind == "person" else None,
        country_code=record.country_code,
        titles=titles,
    )
