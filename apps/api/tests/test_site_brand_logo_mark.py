import string
import uuid
from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import Admin, SiteBrandAsset, SiteBrandConfiguration
from app.routes.site_brand import _published_logo_kind
from app.site_brand_schemas import (
    SiteBrandEditableConfig,
    SiteBrandLogoMark,
    SiteBrandPatchRequest,
)
from app.site_brand_service import (
    admin_response,
    default_config,
    patch_configuration,
    public_response,
    publish_configuration,
    put_logo,
    validate_logo,
)

LOGO_VARIANTS = (
    "iris",
    "marquee",
    "prism",
    "orbit",
    "film-frame",
    "eclipse",
    "stencil",
    "signal",
    "portal",
    "monolith",
    "ribbon",
    "beam",
)


@pytest.fixture
def brand_configuration() -> uuid.UUID:
    with SessionLocal() as db:
        admin = Admin(
            email=f"logo-mark-{uuid.uuid4().hex[:10]}@example.com",
            password_hash=hash_password("LogoMarkOwner123"),
        )
        db.add(admin)
        db.flush()
        db.add(
            SiteBrandConfiguration(
                id=1,
                owner_admin_id=admin.id,
                draft_config={
                    "schema_version": 1,
                    **default_config().model_dump(mode="json"),
                },
                revision=0,
                current_step=1,
                completed_steps=[],
            )
        )
        db.commit()
        admin_id = admin.id
    try:
        yield admin_id
    finally:
        with SessionLocal() as db:
            db.execute(delete(SiteBrandConfiguration))
            db.execute(delete(SiteBrandAsset))
            db.execute(delete(Admin).where(Admin.id == admin_id))
            db.commit()


def _logo_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGBA", (64, 64), "#ff5c35").save(output, format="PNG")
    return output.getvalue()


def _mark(glyph: str = "A", variant: str = "iris") -> dict[str, object]:
    return {"renderer_version": 1, "glyph": glyph, "variant": variant}


def test_logo_mark_is_additive_to_legacy_snapshot_v1() -> None:
    assert default_config().logo_mark is None
    legacy = default_config().model_dump(mode="json", exclude={"logo_mark"})
    parsed = SiteBrandEditableConfig.model_validate(legacy)
    assert parsed.logo_mark is None


@pytest.mark.parametrize("glyph", list(string.ascii_uppercase + string.ascii_lowercase))
def test_logo_mark_accepts_every_ascii_letter_and_preserves_case(glyph: str) -> None:
    recipe = SiteBrandLogoMark.model_validate(_mark(glyph=glyph))
    assert recipe.glyph == glyph


@pytest.mark.parametrize("variant", LOGO_VARIANTS)
def test_logo_mark_accepts_every_renderer_variant(variant: str) -> None:
    recipe = SiteBrandLogoMark.model_validate(_mark(glyph="a", variant=variant))
    assert recipe.variant == variant


@pytest.mark.parametrize("glyph", ["🎬", "<", ">", "AA", "é", "0", "", "\u200b"])
def test_logo_mark_rejects_non_ascii_or_non_letter_glyphs(glyph: str) -> None:
    with pytest.raises(ValidationError):
        SiteBrandLogoMark.model_validate(_mark(glyph=glyph))


@pytest.mark.parametrize(
    "recipe",
    [
        _mark(variant="unknown"),
        {**_mark(), "svg": "<svg><script>alert(1)</script></svg>"},
        {**_mark(), "glyph": "<svg>"},
        {"renderer_version": 2, "glyph": "A", "variant": "iris"},
        {"renderer_version": True, "glyph": "A", "variant": "iris"},
        {"renderer_version": 1.0, "glyph": "A", "variant": "iris"},
    ],
)
def test_logo_mark_rejects_unknown_versions_variants_and_fields(
    recipe: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SiteBrandLogoMark.model_validate(recipe)


def test_logo_mark_draft_and_publish_revisions_are_isolated(
    brand_configuration: uuid.UUID,
) -> None:
    with SessionLocal() as db:
        configuration = db.get_one(SiteBrandConfiguration, 1)
        configuration, changed = patch_configuration(
            db,
            configuration,
            SiteBrandPatchRequest(
                revision=0,
                current_step=5,
                completed_steps=[1, 2, 3, 4, 5],
                config={"logo_mark": _mark("A", "iris")},
            ),
        )
        db.commit()
        assert configuration.revision == 1
        assert changed == ["completed_steps", "current_step", "logo_mark"]
        assert admin_response(db, configuration).config.logo_mark == SiteBrandLogoMark(
            **_mark("A", "iris")
        )
        assert public_response(db).logo_mark is None

        configuration = publish_configuration(db, configuration, 1)
        db.commit()
        assert configuration.revision == 2
        assert _published_logo_kind(configuration) == "generated"
        assert public_response(db).logo_mark == SiteBrandLogoMark(**_mark("A", "iris"))

        configuration, _changed = patch_configuration(
            db,
            configuration,
            SiteBrandPatchRequest(
                revision=2,
                config={"logo_mark": _mark("z", "beam")},
            ),
        )
        db.commit()
        assert configuration.revision == 3
        assert admin_response(db, configuration).config.logo_mark == SiteBrandLogoMark(
            **_mark("z", "beam")
        )
        live = public_response(db)
        assert live.revision == 2
        assert live.logo_mark == SiteBrandLogoMark(**_mark("A", "iris"))

        with pytest.raises(HTTPException) as stale:
            patch_configuration(
                db,
                configuration,
                SiteBrandPatchRequest(
                    revision=2,
                    config={"logo_mark": _mark("B", "orbit")},
                ),
            )
        assert stale.value.status_code == 409


def test_generated_mark_atomically_retires_draft_upload_and_preserves_live_asset(
    brand_configuration: uuid.UUID,
) -> None:
    image = validate_logo(_logo_bytes(), "image/png")
    with SessionLocal() as db:
        configuration = db.get_one(SiteBrandConfiguration, 1)
        configuration, changed = put_logo(db, configuration, 0, image)
        assert changed is True
        configuration, _changed = patch_configuration(
            db,
            configuration,
            SiteBrandPatchRequest(
                revision=1,
                current_step=5,
                completed_steps=[1, 2, 3, 4, 5],
            ),
        )
        configuration = publish_configuration(db, configuration, 2)
        db.commit()
        live_asset_id = configuration.published_logo_asset_id
        assert live_asset_id is not None

        configuration, changed_fields = patch_configuration(
            db,
            configuration,
            SiteBrandPatchRequest(
                revision=3,
                config={"logo_mark": _mark("q", "portal")},
            ),
        )
        db.commit()
        assert changed_fields == ["logo_mark"]
        assert configuration.draft_logo_asset_id is None
        assert configuration.published_logo_asset_id == live_asset_id
        assert db.get(SiteBrandAsset, live_asset_id) is not None
        assert admin_response(db, configuration).config.logo_url is None
        assert public_response(db).logo_url is not None
        assert public_response(db).logo_mark is None

        configuration = publish_configuration(db, configuration, 4)
        db.commit()
        assert configuration.published_logo_asset_id is None
        assert db.get(SiteBrandAsset, live_asset_id) is None
        live = public_response(db)
        assert live.logo_url is None
        assert live.logo_mark == SiteBrandLogoMark(**_mark("q", "portal"))


def test_generated_mark_deletes_only_an_unreferenced_draft_asset(
    brand_configuration: uuid.UUID,
) -> None:
    image = validate_logo(_logo_bytes(), "image/png")
    with SessionLocal() as db:
        configuration = db.get_one(SiteBrandConfiguration, 1)
        configuration, _changed = put_logo(db, configuration, 0, image)
        old_asset_id = configuration.draft_logo_asset_id
        assert old_asset_id is not None

        configuration, _changed_fields = patch_configuration(
            db,
            configuration,
            SiteBrandPatchRequest(
                revision=1,
                config={"logo_mark": _mark("m", "monolith")},
            ),
        )
        db.commit()
        assert configuration.draft_logo_asset_id is None
        assert db.get(SiteBrandAsset, old_asset_id) is None
        assert db.scalar(select(func.count(SiteBrandAsset.id))) == 0


def test_custom_upload_atomically_clears_generated_mark(
    brand_configuration: uuid.UUID,
) -> None:
    image = validate_logo(_logo_bytes(), "image/png")
    with SessionLocal() as db:
        configuration = db.get_one(SiteBrandConfiguration, 1)
        configuration, _changed = patch_configuration(
            db,
            configuration,
            SiteBrandPatchRequest(
                revision=0,
                config={"logo_mark": _mark("r", "ribbon")},
            ),
        )
        configuration, changed = put_logo(db, configuration, 1, image)
        db.commit()
        assert changed is True
        assert configuration.revision == 2
        response = admin_response(db, configuration)
        assert response.config.logo_mark is None
        assert response.config.logo_url is not None
        assert configuration.draft_config["logo_mark"] is None
