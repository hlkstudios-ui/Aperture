from sqlalchemy.dialects.postgresql import JSONB

from app.catalog_models import Character, Company, Movie, Person, Series
from app.models import PlaybackSource


def test_trigram_migration_indexes_are_present_in_model_metadata() -> None:
    expected = {
        Company: {"ix_companies_name_trgm": "name"},
        Person: {"ix_people_name_trgm": "name"},
        Character: {"ix_characters_name_trgm": "name"},
        Movie: {
            "ix_movies_title_trgm": "title",
            "ix_movies_original_title_trgm": "original_title",
        },
        Series: {
            "ix_series_title_trgm": "title",
            "ix_series_original_title_trgm": "original_title",
        },
    }

    for model, model_indexes in expected.items():
        indexes = {index.name: index for index in model.__table__.indexes}
        for index_name, column_name in model_indexes.items():
            index = indexes[index_name]
            assert [column.name for column in index.columns] == [column_name]
            assert index.dialect_options["postgresql"]["using"] == "gin"
            assert index.dialect_options["postgresql"]["ops"] == {
                column_name: "gin_trgm_ops"
            }


def test_playback_source_territories_match_migrated_jsonb_type() -> None:
    column_type = PlaybackSource.__table__.c.allowed_territories.type
    assert isinstance(column_type, JSONB)
