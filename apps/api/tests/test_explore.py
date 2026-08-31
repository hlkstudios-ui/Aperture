import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Episode, Genre, Movie, Season, Series
from app.config import get_settings
from app.db import SessionLocal
from app.explore_models import ExploreEntry, ExploreEntryCard
from app.geo import sign_geo_assertion
from app.main import app
from app.models import Admin, AuditLog

PASSWORD = "ExploreAdministrator123"


def _payload(
    label: str,
    position: int,
    *,
    enabled: bool = True,
    description: str = "A Studio-programmed catalog view.",
) -> dict:
    return {
        "label": label,
        "description": description,
        "icon": "\u2197",
        "position": position,
        "enabled": enabled,
        "criteria": {
            "content_type": "series",
            "query": None,
            "genre": "Animation",
            "studio": None,
            "country_code": "JP",
            "original_language_code": "ja",
            "maturity_rating": None,
            "release_period": "2020s",
            "duration": "standard",
            "airing": "ongoing",
        },
    }


def _seed_admin(suffix: str) -> tuple[uuid.UUID, str]:
    email = f"explore-{suffix}@example.com"
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(PASSWORD))
        db.add(admin)
        db.commit()
        return admin.id, email


def _existing_positions() -> tuple[dict[uuid.UUID, int], int]:
    with SessionLocal() as db:
        entries = list(db.scalars(select(ExploreEntry).order_by(ExploreEntry.position)))
        positions = {entry.id: entry.position for entry in entries}
        next_position = max(positions.values(), default=-1) + 1
        return positions, next_position


def _cleanup(
    *,
    admin_id: uuid.UUID,
    created_ids: list[uuid.UUID],
    original_positions: dict[uuid.UUID, int],
) -> None:
    with SessionLocal() as db:
        if created_ids:
            db.execute(delete(ExploreEntry).where(ExploreEntry.id.in_(created_ids)))
            db.flush()
        originals = list(
            db.scalars(select(ExploreEntry).where(ExploreEntry.id.in_(original_positions)))
        )
        for index, entry in enumerate(originals):
            entry.position = 20_000 + index
        db.flush()
        for entry in originals:
            entry.position = original_positions[entry.id]
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()


def test_explore_admin_crud_public_visibility_reorder_and_audit() -> None:
    suffix = uuid.uuid4().hex[:10]
    admin_id, email = _seed_admin(suffix)
    original_positions, next_position = _existing_positions()
    created_ids: list[uuid.UUID] = []

    try:
        with TestClient(app) as client:
            assert client.get("/admin/explore").status_code == 401
            assert client.get("/catalog/explore").status_code == 200
            assert (
                client.post(
                    "/admin/auth/login",
                    json={"email": email, "password": PASSWORD},
                ).status_code
                == 200
            )

            rejected = client.post(
                "/admin/explore",
                json=_payload(f"Untrusted {suffix}", next_position),
                headers={"Origin": "https://attacker.example"},
            )
            assert rejected.status_code == 403

            first = client.post(
                "/admin/explore",
                json=_payload(f"Anime premieres {suffix}", next_position),
            )
            assert first.status_code == 201, first.text
            first_id = uuid.UUID(first.json()["id"])
            created_ids.append(first_id)

            second = client.post(
                "/admin/explore",
                json=_payload(
                    f"Festival discoveries {suffix}",
                    next_position + 1,
                    enabled=False,
                ),
            )
            assert second.status_code == 201, second.text
            second_id = uuid.UUID(second.json()["id"])
            created_ids.append(second_id)

            position_conflict = client.post(
                "/admin/explore",
                json=_payload(f"Position conflict {suffix}", next_position),
            )
            assert position_conflict.status_code == 409

            public_before = client.get("/catalog/explore")
            assert public_before.status_code == 200
            public_by_id = {uuid.UUID(entry["id"]): entry for entry in public_before.json()}
            assert first_id in public_by_id
            assert second_id not in public_by_id
            assert "enabled" not in public_by_id[first_id]
            assert "created_at" not in public_by_id[first_id]

            updated_payload = _payload(
                f"Festival discoveries updated {suffix}",
                next_position + 1,
                description="A visible, updated Explore filter.",
            )
            updated = client.put(f"/admin/explore/{second_id}", json=updated_payload)
            assert updated.status_code == 200, updated.text
            assert updated.json()["enabled"] is True
            assert updated.json()["description"] == "A visible, updated Explore filter."

            all_entries = client.get("/admin/explore").json()
            all_ids = [uuid.UUID(entry["id"]) for entry in all_entries]
            incomplete_order = client.put("/admin/explore/order", json={"ids": [str(first_id)]})
            assert incomplete_order.status_code == 422
            duplicate_order = client.put(
                "/admin/explore/order",
                json={"ids": [str(first_id), str(first_id)]},
            )
            assert duplicate_order.status_code == 422

            desired_order = [second_id, first_id] + [
                entry_id for entry_id in all_ids if entry_id not in {first_id, second_id}
            ]
            reordered = client.put(
                "/admin/explore/order",
                json={"ids": [str(entry_id) for entry_id in desired_order]},
            )
            assert reordered.status_code == 200, reordered.text
            assert [uuid.UUID(entry["id"]) for entry in reordered.json()] == desired_order
            assert [entry["position"] for entry in reordered.json()] == list(
                range(len(desired_order))
            )

            public_after = client.get("/catalog/explore").json()
            public_ids = [uuid.UUID(entry["id"]) for entry in public_after]
            assert public_ids.index(second_id) < public_ids.index(first_id)

            assert client.delete(f"/admin/explore/{first_id}").status_code == 204
            assert client.delete(f"/admin/explore/{first_id}").status_code == 404
            assert first_id not in {
                uuid.UUID(entry["id"]) for entry in client.get("/catalog/explore").json()
            }

        with SessionLocal() as db:
            explore_audits = list(
                db.scalars(
                    select(AuditLog)
                    .where(
                        AuditLog.actor_id == admin_id,
                        AuditLog.action.like("explore.%"),
                    )
                    .order_by(AuditLog.created_at)
                )
            )
            create_audits = [
                audit for audit in explore_audits if audit.action == "explore.entry.created"
            ]
            assert {audit.detail["entry_id"] for audit in create_audits} == {
                str(first_id),
                str(second_id),
            }
            assert all(audit.detail["entry_id"] != "None" for audit in create_audits)
            assert {audit.action for audit in explore_audits} >= {
                "explore.entry.created",
                "explore.entry.updated",
                "explore.entries.reordered",
                "explore.entry.deleted",
            }
    finally:
        _cleanup(
            admin_id=admin_id,
            created_ids=created_ids,
            original_positions=original_positions,
        )


def test_explore_rejects_reserved_invalid_and_case_duplicate_entries() -> None:
    suffix = uuid.uuid4().hex[:10]
    admin_id, email = _seed_admin(suffix)
    original_positions, next_position = _existing_positions()
    created_ids: list[uuid.UUID] = []

    try:
        with TestClient(app) as client:
            assert (
                client.post(
                    "/admin/auth/login",
                    json={"email": email, "password": PASSWORD},
                ).status_code
                == 200
            )

            reserved = client.post(
                "/admin/explore",
                json=_payload("  TrEnDiNg  ", next_position),
            )
            assert reserved.status_code == 409
            assert "reserved" in reserved.json()["detail"].lower()

            whitespace = client.post(
                "/admin/explore",
                json=_payload("   ", next_position),
            )
            assert whitespace.status_code == 422

            unknown_field = _payload(f"Unknown field {suffix}", next_position)
            unknown_field["unexpected"] = True
            assert client.post("/admin/explore", json=unknown_field).status_code == 422

            unknown_criteria = _payload(f"Unknown criteria {suffix}", next_position)
            unknown_criteria["criteria"]["unexpected"] = True
            assert client.post("/admin/explore", json=unknown_criteria).status_code == 422

            control_icon = _payload(f"Control icon {suffix}", next_position)
            control_icon["icon"] = "bad\nicon"
            assert client.post("/admin/explore", json=control_icon).status_code == 422

            label = f"Unique Explore View {suffix}"
            created = client.post(
                "/admin/explore",
                json=_payload(label, next_position, enabled=False),
            )
            assert created.status_code == 201, created.text
            created_id = uuid.UUID(created.json()["id"])
            created_ids.append(created_id)

            duplicate = client.post(
                "/admin/explore",
                json=_payload(label.swapcase(), next_position + 1),
            )
            assert duplicate.status_code == 409
            assert "unique" in duplicate.json()["detail"].lower()
            assert created_id not in {
                uuid.UUID(entry["id"]) for entry in client.get("/catalog/explore").json()
            }

        with SessionLocal() as db:
            db.add(
                ExploreEntry(
                    label=label.swapcase(),
                    description="A direct write must still respect the database invariant.",
                    icon="\u2197",
                    position=next_position + 2,
                    enabled=False,
                    criteria={},
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
            assert (
                db.scalar(
                    select(func.count(ExploreEntry.id)).where(
                        func.lower(ExploreEntry.label) == label.lower()
                    )
                )
                == 1
            )

            create_audits = list(
                db.scalars(
                    select(AuditLog).where(
                        AuditLog.actor_id == admin_id,
                        AuditLog.action == "explore.entry.created",
                    )
                )
            )
            assert len(create_audits) == 1
            assert create_audits[0].detail["entry_id"] == str(created_id)
    finally:
        _cleanup(
            admin_id=admin_id,
            created_ids=created_ids,
            original_positions=original_positions,
        )


def test_explore_cards_are_owned_ordered_hydrated_and_publicly_filtered() -> None:
    suffix = uuid.uuid4().hex[:10]
    admin_id, email = _seed_admin(suffix)
    original_positions, next_position = _existing_positions()
    created_entry_ids: list[uuid.UUID] = []
    now = datetime.now(UTC)

    with SessionLocal() as db:
        genre = Genre(name=f"Explore Animation {suffix}", slug=f"explore-animation-{suffix}")
        public_movie = Movie(
            title=f"Catalog Classic {suffix}",
            slug=f"catalog-classic-{suffix}",
            original_title=f"Original Classic {suffix}",
            short_description="An older title pinned directly by Studio.",
            synopsis="A public movie used to validate Explore card hydration.",
            release_date=date(1971, 2, 3),
            runtime_minutes=101,
            maturity_rating="PG",
            status=CatalogStatus.published,
            poster_url="https://images.example/classic.jpg",
            content_format="movie",
            studios=["Aperture Archive"],
            genres=[genre],
        )
        public_series = Series(
            title=f"Public Series {suffix}",
            slug=f"public-series-{suffix}",
            short_description="A public series with one draft episode.",
            synopsis="Only published episodes may contribute to the public card.",
            release_date=date(2025, 4, 5),
            maturity_rating="TV-14",
            status=CatalogStatus.published,
            poster_url="https://images.example/series.jpg",
            is_ongoing=True,
            content_format="tv",
            studios=["Aperture Television"],
            genres=[genre],
            seasons=[
                Season(
                    number=1,
                    title="Season One",
                    episodes=[
                        Episode(
                            number=1,
                            title="Published Episode",
                            synopsis="Visible episode metadata.",
                            runtime_minutes=24,
                            status=CatalogStatus.published,
                        ),
                        Episode(
                            number=2,
                            title="Draft Episode",
                            synopsis="Private episode metadata.",
                            runtime_minutes=48,
                            status=CatalogStatus.draft,
                        ),
                    ],
                )
            ],
        )
        draft_movie = Movie(
            title=f"Draft Movie {suffix}",
            slug=f"draft-movie-{suffix}",
            short_description="A draft title.",
            synopsis="This metadata must remain private.",
            runtime_minutes=90,
            status=CatalogStatus.draft,
        )
        future_movie = Movie(
            title=f"Future Movie {suffix}",
            slug=f"future-movie-{suffix}",
            short_description="A future scheduled title.",
            synopsis="This title is not due yet.",
            runtime_minutes=91,
            status=CatalogStatus.ready,
            publish_at=now + timedelta(days=1),
        )
        due_movie = Movie(
            title=f"Due Movie {suffix}",
            slug=f"due-movie-{suffix}",
            short_description="A title whose publication schedule is due.",
            synopsis="The public Explore read should materialize this schedule.",
            runtime_minutes=92,
            status=CatalogStatus.ready,
            publish_at=now - timedelta(minutes=1),
        )
        expired_movie = Movie(
            title=f"Expired Movie {suffix}",
            slug=f"expired-explore-{suffix}",
            short_description="An expired rights title.",
            synopsis="Rights filtering must omit this card.",
            runtime_minutes=93,
            status=CatalogStatus.published,
            rights_end_at=now - timedelta(minutes=1),
        )
        canada_movie = Movie(
            title=f"Canada Movie {suffix}",
            slug=f"canada-movie-{suffix}",
            short_description="A Canada-only title.",
            synopsis="Territory filtering controls this card.",
            runtime_minutes=94,
            status=CatalogStatus.published,
            allowed_territories=["CA"],
        )
        db.add_all(
            (
                public_movie,
                public_series,
                draft_movie,
                future_movie,
                due_movie,
                expired_movie,
                canada_movie,
            )
        )
        db.commit()
        genre_id = genre.id
        movie_ids = [
            public_movie.id,
            draft_movie.id,
            future_movie.id,
            due_movie.id,
            expired_movie.id,
            canada_movie.id,
        ]
        series_id = public_series.id

    try:
        with TestClient(app) as client:
            assert (
                client.post(
                    "/admin/auth/login",
                    json={"email": email, "password": PASSWORD},
                ).status_code
                == 200
            )
            entry = client.post(
                "/admin/explore",
                json=_payload(f"Pinned discoveries {suffix}", next_position),
            )
            assert entry.status_code == 201, entry.text
            entry_id = uuid.UUID(entry.json()["id"])
            created_entry_ids.append(entry_id)
            other_entry = client.post(
                "/admin/explore",
                json=_payload(
                    f"Other pinned discoveries {suffix}",
                    next_position + 1,
                    enabled=False,
                ),
            )
            assert other_entry.status_code == 201, other_entry.text
            other_entry_id = uuid.UUID(other_entry.json()["id"])
            created_entry_ids.append(other_entry_id)

            rejected = client.post(
                f"/admin/explore/{entry_id}/cards",
                json={"movie_id": str(public_movie.id), "position": 0},
                headers={"Origin": "https://attacker.example"},
            )
            assert rejected.status_code == 403
            assert (
                client.post(
                    f"/admin/explore/{entry_id}/cards",
                    json={"position": 0},
                ).status_code
                == 422
            )
            assert (
                client.post(
                    f"/admin/explore/{entry_id}/cards",
                    json={
                        "movie_id": str(public_movie.id),
                        "series_id": str(series_id),
                        "position": 0,
                    },
                ).status_code
                == 422
            )
            assert (
                client.post(
                    f"/admin/explore/{uuid.uuid4()}/cards",
                    json={"movie_id": str(public_movie.id), "position": 0},
                ).status_code
                == 404
            )
            assert (
                client.post(
                    f"/admin/explore/{entry_id}/cards",
                    json={"movie_id": str(uuid.uuid4()), "position": 0},
                ).status_code
                == 404
            )

            refs = [
                ("movie_id", public_movie.id),
                ("series_id", series_id),
                ("movie_id", draft_movie.id),
                ("movie_id", future_movie.id),
                ("movie_id", due_movie.id),
                ("movie_id", expired_movie.id),
                ("movie_id", canada_movie.id),
            ]
            card_ids: list[uuid.UUID] = []
            for position, (field, title_id) in enumerate(refs):
                response = client.post(
                    f"/admin/explore/{entry_id}/cards",
                    json={field: str(title_id), "position": position},
                )
                assert response.status_code == 201, response.text
                card_ids.append(uuid.UUID(response.json()["id"]))
                assert response.json()["title"]["id"] == str(title_id)

            assert (
                client.post(
                    f"/admin/explore/{entry_id}/cards",
                    json={"movie_id": str(public_movie.id), "position": len(refs)},
                ).status_code
                == 409
            )
            assert (
                client.post(
                    f"/admin/explore/{entry_id}/cards",
                    json={"movie_id": str(uuid.uuid4()), "position": 0},
                ).status_code
                == 404
            )
            same_title_other_entry = client.post(
                f"/admin/explore/{other_entry_id}/cards",
                json={"movie_id": str(public_movie.id), "position": 0},
            )
            assert same_title_other_entry.status_code == 201, same_title_other_entry.text
            other_card_id = uuid.UUID(same_title_other_entry.json()["id"])

            admin_entries = client.get("/admin/explore").json()
            admin_payload = next(item for item in admin_entries if item["id"] == str(entry_id))
            assert [uuid.UUID(card["id"]) for card in admin_payload["cards"]] == card_ids
            assert len(admin_payload["cards"]) == len(refs)
            admin_series = next(
                card for card in admin_payload["cards"] if card["series_id"] == str(series_id)
            )
            assert admin_series["title"]["episode_count"] == 2
            assert admin_series["title"]["duration_minutes"] == 36

            public_payload = next(
                item
                for item in client.get("/catalog/explore").json()
                if item["id"] == str(entry_id)
            )
            assert public_payload["criteria"] == entry.json()["criteria"]
            public_title_ids = [card["title"]["id"] for card in public_payload["cards"]]
            assert public_title_ids == [str(public_movie.id), str(series_id), str(due_movie.id)]
            public_series_card = next(
                card for card in public_payload["cards"] if card["series_id"] == str(series_id)
            )
            assert public_series_card["title"]["episode_count"] == 1
            assert public_series_card["title"]["duration_minutes"] == 24
            assert public_series_card["title"]["poster_url"] == "https://images.example/series.jpg"
            assert public_series_card["title"]["genres"] == [f"Explore Animation {suffix}"]
            assert public_series_card["title"]["studios"] == ["Aperture Television"]
            assert public_series_card["title"]["is_ongoing"] is True
            assert {
                "id",
                "kind",
                "title",
                "original_title",
                "slug",
                "short_description",
                "release_date",
                "maturity_rating",
                "poster_url",
                "content_format",
                "country_code",
                "original_language_code",
                "studios",
                "genres",
                "duration_minutes",
                "is_ongoing",
                "season_count",
                "episode_count",
                "href",
                "source",
                "availability",
            } <= public_series_card["title"].keys()
            assert public_series_card["title"]["href"] == f"/series/public-series-{suffix}"
            assert public_series_card["title"]["source"] == "local"
            assert "rights_end_at" not in public_series_card["title"]
            assert "status" not in public_series_card["title"]

            issued_at = int(datetime.now(UTC).timestamp())
            geo_headers = {
                "X-Aperture-Country": "CA",
                "X-Aperture-Geo-Timestamp": str(issued_at),
                "X-Aperture-Geo-Signature": sign_geo_assertion(
                    "CA", issued_at, get_settings().geo_assertion_secret
                ),
            }
            canada_payload = next(
                item
                for item in client.get("/catalog/explore", headers=geo_headers).json()
                if item["id"] == str(entry_id)
            )
            canada_title_ids = [card["title"]["id"] for card in canada_payload["cards"]]
            assert str(canada_movie.id) in canada_title_ids
            assert str(draft_movie.id) not in canada_title_ids
            assert str(future_movie.id) not in canada_title_ids
            assert str(expired_movie.id) not in canada_title_ids

            invalid_order = client.put(
                f"/admin/explore/{entry_id}/cards/order",
                json={"ids": [str(card_id) for card_id in card_ids[:-1]]},
            )
            assert invalid_order.status_code == 422
            foreign_order = client.put(
                f"/admin/explore/{entry_id}/cards/order",
                json={"ids": [str(other_card_id), *[str(card_id) for card_id in card_ids[1:]]]},
            )
            assert foreign_order.status_code == 422
            reversed_ids = list(reversed(card_ids))
            reordered = client.put(
                f"/admin/explore/{entry_id}/cards/order",
                json={"ids": [str(card_id) for card_id in reversed_ids]},
            )
            assert reordered.status_code == 200, reordered.text
            assert [uuid.UUID(card["id"]) for card in reordered.json()] == reversed_ids
            assert [card["position"] for card in reordered.json()] == list(range(len(refs)))

            public_reordered = next(
                item
                for item in client.get("/catalog/explore").json()
                if item["id"] == str(entry_id)
            )
            assert [card["title"]["id"] for card in public_reordered["cards"]] == [
                str(due_movie.id),
                str(series_id),
                str(public_movie.id),
            ]

            removed_id = reversed_ids[0]
            assert client.delete(f"/admin/explore/cards/{removed_id}").status_code == 204
            assert client.delete(f"/admin/explore/cards/{removed_id}").status_code == 404
            assert client.delete(f"/admin/explore/{other_entry_id}").status_code == 204
            with SessionLocal() as db:
                assert db.get(ExploreEntryCard, other_card_id) is None

        with SessionLocal() as db:
            card_audits = list(
                db.scalars(
                    select(AuditLog).where(
                        AuditLog.actor_id == admin_id,
                        AuditLog.action.in_(
                            (
                                "explore.card.added",
                                "explore.card.removed",
                                "explore.cards.reordered",
                            )
                        ),
                    )
                )
            )
            added_ids = {
                audit.detail["card_id"]
                for audit in card_audits
                if audit.action == "explore.card.added"
            }
            assert {str(card_id) for card_id in card_ids} <= added_ids
            assert str(other_card_id) in added_ids
            assert any(
                audit.action == "explore.card.removed"
                and audit.detail["card_id"] == str(removed_id)
                for audit in card_audits
            )
            assert any(audit.action == "explore.cards.reordered" for audit in card_audits)

            due_card_id = card_ids[4]
            db.execute(delete(Movie).where(Movie.id == due_movie.id))
            db.commit()
            assert db.get(ExploreEntryCard, due_card_id) is None
    finally:
        _cleanup(
            admin_id=admin_id,
            created_ids=created_entry_ids,
            original_positions=original_positions,
        )
        with SessionLocal() as db:
            db.execute(delete(Movie).where(Movie.id.in_(movie_ids)))
            db.execute(delete(Series).where(Series.id == series_id))
            db.execute(delete(Genre).where(Genre.id == genre_id))
            db.commit()
