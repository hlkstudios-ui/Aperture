import uuid

import pytest
from pydantic import ValidationError

from app.playback_schemas import PlaybackSourceCreate


def test_external_source_requires_https_duration_and_rights_evidence() -> None:
    movie_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        PlaybackSourceCreate(
            movie_id=movie_id,
            external_manifest_url="http://cdn.example.test/movie/master.m3u8",
            duration_seconds=5400,
            rights_basis="Licensed streaming distribution agreement",
            rights_reference="LIC-2026-41",
        )
    with pytest.raises(ValidationError):
        PlaybackSourceCreate(
            movie_id=movie_id,
            external_manifest_url="https://cdn.example.test/movie/master.m3u8",
            duration_seconds=5400,
        )


def test_external_source_normalizes_format_and_territories() -> None:
    source = PlaybackSourceCreate(
        movie_id=uuid.uuid4(),
        external_manifest_url="https://cdn.example.test/movie/master.m3u8",
        duration_seconds=5400,
        rights_basis="Licensed streaming distribution agreement",
        rights_reference="LIC-2026-41",
        allowed_territories=["ca", " US ", "ca"],
    )
    assert source.external_format == "hls"
    assert source.allowed_territories == ["CA", "US"]


def test_source_rejects_ambiguous_origin_and_parent() -> None:
    with pytest.raises(ValidationError):
        PlaybackSourceCreate(
            processing_job_id=uuid.uuid4(),
            external_manifest_url="https://cdn.example.test/movie/master.m3u8",
            movie_id=uuid.uuid4(),
            duration_seconds=5400,
            rights_basis="Licensed streaming distribution agreement",
            rights_reference="LIC-2026-41",
        )
    with pytest.raises(ValidationError):
        PlaybackSourceCreate(
            processing_job_id=uuid.uuid4(),
            movie_id=uuid.uuid4(),
            episode_id=uuid.uuid4(),
        )
