import asyncio
import json
import logging
import uuid

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.auth import hash_password
from app.brand_copy_assistant import (
    MAX_PROVIDER_RESPONSE_BYTES,
    BrandAiProviderError,
    _bounded_body,
    _request_payload,
    generate_brand_copy,
    owner_safety_identifier,
)
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Admin, AuditLog, SiteBrandConfiguration
from app.observability import configure_observability
from app.routes import site_brand as site_brand_route
from app.site_brand_schemas import (
    BrandCopyAssistRequest,
    BrandCopyAssistResponse,
    BrandCopySuggestion,
)


def _brief() -> BrandCopyAssistRequest:
    return BrandCopyAssistRequest(
        business_name="Northstar Pictures",
        short_name="Northstar",
        audience="People who love ambitious international cinema",
        themes=["discovery", "craft"],
        tone="refined",
        additional_direction="Confident, but never grandiose",
    )


def _suggestions() -> list[BrandCopySuggestion]:
    return [
        BrandCopySuggestion(
            tagline="Find the frame that stays.",
            description=(
                "A considered home for films and series that reward curiosity, attention, "
                "and another look."
            ),
            short_name="Northstar",
            tone_direction="Poetic and assured, with an invitation to discover.",
        ),
        BrandCopySuggestion(
            tagline="Cinema, charted differently.",
            description=(
                "Thoughtful stories, bold perspectives, and memorable discoveries gathered "
                "for people who watch with intention."
            ),
            short_name="Northstar",
            tone_direction="Modern and editorial, led by clarity instead of hype.",
        ),
        BrandCopySuggestion(
            tagline="Stay for what moves you.",
            description=(
                "An inviting destination for distinctive films and series, shaped around the "
                "pleasure of finding your next favorite."
            ),
            short_name="Northstar",
            tone_direction="Warmly cinematic, personal, and quietly memorable.",
        ),
    ]


def test_provider_payload_is_private_bounded_and_structured() -> None:
    identifier = owner_safety_identifier(uuid.uuid4(), "test-secret-that-is-not-the-owner-id")
    payload = _request_payload(_brief(), model="gpt-5-mini", safety_identifier=identifier)

    assert payload["store"] is False
    assert payload["background"] is False
    assert payload["max_output_tokens"] == 900
    assert payload["safety_identifier"] == identifier
    assert "tools" not in payload
    response_format = payload["text"]["format"]
    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    assert response_format["schema"]["additionalProperties"] is False
    assert response_format["schema"]["properties"]["suggestions"]["minItems"] == 3
    assert response_format["schema"]["properties"]["suggestions"]["maxItems"] == 3
    assert "Northstar Pictures" in payload["input"][0]["content"][0]["text"]

    with pytest.raises(ValidationError, match="fine-tuned"):
        Settings(
            _env_file=None,
            brand_ai_provider="openai",
            brand_ai_model="ft:gpt-5-mini:example:brand",
            openai_api_key="test-project-key",
        )


def test_observability_never_captures_request_bodies_or_stack_locals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.observability.sentry_sdk.init",
        lambda **kwargs: captured.update(kwargs),
    )
    settings = Settings(
        _env_file=None,
        app_env="development",
        error_tracking_dsn="https://public@example.test/1",
        brand_ai_provider="openai",
        openai_api_key="server-side-project-key",
    )
    root_logger = logging.getLogger()
    previous_handlers = root_logger.handlers
    previous_level = root_logger.level
    try:
        configure_observability(settings)
    finally:
        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)

    assert captured["send_default_pii"] is False
    assert captured["include_local_variables"] is False
    assert captured["max_request_body_size"] == "never"
    assert "server-side-project-key" not in repr(settings)


def test_observability_never_sends_isolated_test_failures_to_sentry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def unexpected_init(**_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("app.observability.sentry_sdk.init", unexpected_init)
    configure_observability(
        Settings(
            _env_file=None,
            app_env="test",
            error_tracking_dsn="https://public@production.example.test/1",
        )
    )
    assert called is False


def test_assistant_input_normalizes_unicode_and_rejects_invisible_controls() -> None:
    normalized = BrandCopyAssistRequest(business_name="Cafe\u0301 Cinema")
    assert normalized.business_name == "Café Cinema"
    with pytest.raises(ValidationError):
        BrandCopyAssistRequest(business_name="North\u200bstar")
    with pytest.raises(ValidationError):
        BrandCopyAssistRequest(business_name="Northstar", additional_direction="first\nsecond")


def test_provider_response_body_has_a_decoded_size_ceiling() -> None:
    async def oversized_body():
        yield b"x" * (MAX_PROVIDER_RESPONSE_BYTES + 1)

    with pytest.raises(BrandAiProviderError):
        asyncio.run(_bounded_body(oversized_body()))


def test_provider_output_is_validated_after_structured_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def valid_provider(*_args, **_kwargs):
        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "suggestions": [
                                        suggestion.model_dump() for suggestion in _suggestions()
                                    ]
                                }
                            ),
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr("app.brand_copy_assistant._request_openai", valid_provider)
    settings = Settings(
        _env_file=None,
        brand_ai_provider="openai",
        openai_api_key="test-project-key",
    )
    response = asyncio.run(
        generate_brand_copy(
            _brief(),
            safety_identifier="a" * 64,
            settings=settings,
        )
    )
    assert response.generated_by == "ai"
    assert len(response.suggestions) == 3

    async def invalid_provider(*_args, **_kwargs):
        payload = {"suggestions": [suggestion.model_dump() for suggestion in _suggestions()]}
        payload["suggestions"][0]["tagline"] = "x" * 121
        return {"status": "completed", "output_text": json.dumps(payload)}

    monkeypatch.setattr("app.brand_copy_assistant._request_openai", invalid_provider)
    with pytest.raises(BrandAiProviderError):
        asyncio.run(
            generate_brand_copy(
                _brief(),
                safety_identifier="a" * 64,
                settings=settings,
            )
        )

    async def incomplete_provider(*_args, **_kwargs):
        return {"output_text": json.dumps({"suggestions": []})}

    monkeypatch.setattr("app.brand_copy_assistant._request_openai", incomplete_provider)
    with pytest.raises(BrandAiProviderError):
        asyncio.run(
            generate_brand_copy(
                _brief(),
                safety_identifier="a" * 64,
                settings=settings,
            )
        )


def test_owner_copy_assistant_route_is_ephemeral_private_and_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    owner_email = f"copy-owner-{suffix}@example.com"
    other_email = f"copy-other-{suffix}@example.com"
    password = "CopyAssistantOwner123"
    with SessionLocal() as db:
        owner = Admin(email=owner_email, password_hash=hash_password(password))
        db.add(owner)
        db.commit()
        owner_id = owner.id
    other_id = None
    calls: dict[str, object] = {}

    async def allow_rate_limit(key: str, **_kwargs) -> None:
        calls["rate_key"] = key

    async def generated(brief, *, safety_identifier, settings):
        calls["brief"] = brief
        calls["safety_identifier"] = safety_identifier
        calls["settings"] = settings
        return BrandCopyAssistResponse(suggestions=_suggestions())

    monkeypatch.setattr(site_brand_route, "enforce_rate_limit", allow_rate_limit)
    monkeypatch.setattr(site_brand_route, "generate_brand_copy", generated)
    origin = str(get_settings().web_origin).rstrip("/")

    try:
        with TestClient(app) as client:
            anonymous_response = client.post(
                "/admin/site/brand/assist-copy",
                json=_brief().model_dump(mode="json"),
                headers={"Origin": origin},
            )
            assert anonymous_response.status_code == 401
            assert anonymous_response.headers["cache-control"].startswith("private, no-store")
            assert client.post(
                "/admin/auth/login",
                json={"email": owner_email, "password": password},
            ).status_code == 200
            untrusted_response = client.post(
                "/admin/site/brand/assist-copy",
                json=_brief().model_dump(mode="json"),
                headers={"Origin": "https://untrusted.example"},
            )
            assert untrusted_response.status_code == 403
            assert untrusted_response.headers["cache-control"].startswith("private, no-store")
            invalid_response = client.post(
                "/admin/site/brand/assist-copy",
                json={"business_name": "X"},
                headers={"Origin": origin},
            )
            assert invalid_response.status_code == 422
            assert invalid_response.headers["cache-control"].startswith("private, no-store")

            success = client.post(
                "/admin/site/brand/assist-copy",
                json=_brief().model_dump(mode="json"),
                headers={"Origin": origin},
            )
            assert success.status_code == 200, success.text
            assert success.json()["generated_by"] == "ai"
            assert len(success.json()["suggestions"]) == 3
            assert success.headers["cache-control"].startswith("private, no-store")
            assert "Cookie" in success.headers["vary"]
            assert str(owner_id) not in str(calls["rate_key"])
            assert calls["safety_identifier"] in str(calls["rate_key"])

            async def unavailable(*_args, **_kwargs):
                from app.brand_copy_assistant import BrandAiUnavailableError

                raise BrandAiUnavailableError

            monkeypatch.setattr(site_brand_route, "generate_brand_copy", unavailable)
            unavailable_response = client.post(
                "/admin/site/brand/assist-copy",
                json=_brief().model_dump(mode="json"),
                headers={"Origin": origin},
            )
            assert unavailable_response.status_code == 503
            assert unavailable_response.json() == {
                "detail": "The private copy assistant is not configured yet.",
                "code": "brand_ai_unavailable",
            }
            assert unavailable_response.headers["cache-control"].startswith(
                "private, no-store"
            )

            async def provider_failed(*_args, **_kwargs):
                raise BrandAiProviderError("raw provider body must not escape")

            monkeypatch.setattr(site_brand_route, "generate_brand_copy", provider_failed)
            failed_response = client.post(
                "/admin/site/brand/assist-copy",
                json=_brief().model_dump(mode="json"),
                headers={"Origin": origin},
            )
            assert failed_response.status_code == 502
            assert failed_response.json()["code"] == "brand_ai_failed"
            assert "raw provider" not in failed_response.text
            assert failed_response.headers["cache-control"].startswith("private, no-store")

            async def denied_rate_limit(*_args, **_kwargs) -> None:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "provider budget reached")

            monkeypatch.setattr(site_brand_route, "enforce_rate_limit", denied_rate_limit)
            limited_response = client.post(
                "/admin/site/brand/assist-copy",
                json=_brief().model_dump(mode="json"),
                headers={"Origin": origin},
            )
            assert limited_response.status_code == 429
            assert limited_response.json()["code"] == "brand_ai_rate_limited"
            assert "provider budget" not in limited_response.text
            assert limited_response.headers["cache-control"].startswith("private, no-store")

            async def unavailable_rate_limit(*_args, **_kwargs) -> None:
                raise ConnectionError("redis connection details must not escape")

            monkeypatch.setattr(site_brand_route, "enforce_rate_limit", unavailable_rate_limit)
            limiter_failure = client.post(
                "/admin/site/brand/assist-copy",
                json=_brief().model_dump(mode="json"),
                headers={"Origin": origin},
            )
            assert limiter_failure.status_code == 503
            assert limiter_failure.json()["code"] == "brand_ai_unavailable"
            assert "redis connection" not in limiter_failure.text
            assert limiter_failure.headers["cache-control"].startswith("private, no-store")

            async def unexpected_failure(*_args, **_kwargs):
                raise RuntimeError("unexpected model adapter failure")

            monkeypatch.setattr(site_brand_route, "enforce_rate_limit", allow_rate_limit)
            monkeypatch.setattr(site_brand_route, "generate_brand_copy", unexpected_failure)
            unexpected_response = client.post(
                "/admin/site/brand/assist-copy",
                json=_brief().model_dump(mode="json"),
                headers={"Origin": origin},
            )
            assert unexpected_response.status_code == 500
            assert unexpected_response.json()["detail"] == "Internal server error"
            assert unexpected_response.headers["cache-control"].startswith("private, no-store")

        with SessionLocal() as db:
            configuration = db.get_one(SiteBrandConfiguration, 1)
            assert configuration.revision == 0
            assert configuration.draft_config["business_name"] == "Aperture"
            assistant_audits = list(
                db.scalars(
                    select(AuditLog).where(
                        AuditLog.actor_id == owner_id,
                        AuditLog.action == "site_brand.copy_assistance",
                    )
                )
            )
            assert len(assistant_audits) == 4
            assert {audit.outcome for audit in assistant_audits} == {"succeeded", "failed"}
            serialized_audit = json.dumps([audit.detail for audit in assistant_audits])
            assert "Northstar" not in serialized_audit
            assert "Find the frame" not in serialized_audit

            other = Admin(email=other_email, password_hash=hash_password(password))
            db.add(other)
            db.commit()
            other_id = other.id

        monkeypatch.setattr(site_brand_route, "enforce_rate_limit", allow_rate_limit)
        with TestClient(app) as other_client:
            assert other_client.post(
                "/admin/auth/login",
                json={"email": other_email, "password": password},
            ).status_code == 200
            forbidden = other_client.post(
                "/admin/site/brand/assist-copy",
                json=_brief().model_dump(mode="json"),
                headers={"Origin": origin},
            )
            assert forbidden.status_code == 403
    finally:
        with SessionLocal() as db:
            db.execute(delete(SiteBrandConfiguration))
            ids = [owner_id, *([other_id] if other_id is not None else [])]
            db.execute(delete(AuditLog).where(AuditLog.actor_id.in_(ids)))
            db.execute(delete(Admin).where(Admin.id.in_(ids)))
            db.commit()
