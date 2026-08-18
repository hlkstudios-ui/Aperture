import asyncio
import logging
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager

import boto3
import redis.asyncio as redis
import sentry_sdk
from botocore.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.observability import (
    configure_observability,
    log_event,
    metrics,
    request_id_context,
)
from app.routes import (
    account,
    admin_analytics,
    admin_auth,
    admin_catalog,
    admin_community,
    admin_curation,
    admin_homepage,
    admin_playback,
    admin_processing,
    admin_scenes,
    admin_support,
    admin_uploads,
    analytics,
    billing_webhooks,
    cinephile,
    clubs,
    community,
    curation,
    customer_auth,
    customer_catalog,
    homepage,
    oauth,
    operations,
    passport,
    playback,
    profiles,
    recommendations,
    scene_intelligence,
)

settings = get_settings()
configure_observability(settings)
logger = logging.getLogger("aperture.api")
REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def private_studio_authorized(path: str, supplied: str | None) -> bool:
    if not settings.private_studio_required or not (
        path == "/admin" or path.startswith("/admin/")
    ):
        return True
    expected = settings.studio_edge_secret or ""
    return bool(expected and supplied and secrets.compare_digest(supplied, expected))


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    engine.dispose()


production = settings.app_env == "production"
app = FastAPI(
    title="Aperture API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        str(origin).rstrip("/")
        for origin in (settings.web_origin, settings.admin_web_origin)
        if origin is not None
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Range"],
)


@app.middleware("http")
async def private_studio_boundary(request, call_next):
    if not private_studio_authorized(
        request.url.path, request.headers.get("x-aperture-studio-edge")
    ):
        response = JSONResponse({"detail": "Not found"}, status_code=404)
        apply_security_headers(response)
        return response
    return await call_next(request)


@app.middleware("http")
async def observe_request(request, call_next):
    supplied_id = request.headers.get("x-request-id", "")
    request_id = supplied_id if REQUEST_ID.fullmatch(supplied_id) else uuid.uuid4().hex
    context_token = request_id_context.set(request_id)
    started = time.perf_counter()
    metrics.increment("aperture_api_in_flight")
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as error:
        sentry_sdk.capture_exception(error)
        logger.exception(
            "request.failed",
            extra={
                "structured": {
                    "event": "request.failed",
                    "method": request.method,
                    "path": request.url.path,
                }
            },
        )
        response = JSONResponse(
            {"detail": "Internal server error", "request_id": request_id}, status_code=500
        )
        apply_security_headers(response)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration = time.perf_counter() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        labels = {"method": request.method, "route": route, "status": str(status_code)}
        metrics.increment("aperture_api_in_flight", -1)
        metrics.increment("aperture_api_requests_total", **labels)
        metrics.observe("aperture_api_request_duration_seconds", duration, **labels)
        log_event(
            logger,
            "request.completed",
            method=request.method,
            route=route,
            status=status_code,
            duration_ms=round(duration * 1000, 3),
        )
        request_id_context.reset(context_token)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    apply_security_headers(response)
    return response


def apply_security_headers(response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


app.include_router(customer_auth.router)
app.include_router(oauth.router)
app.include_router(account.router)
app.include_router(billing_webhooks.router)
app.include_router(analytics.router)
app.include_router(profiles.router)
if settings.feature_experimental_recommendations_enabled:
    app.include_router(recommendations.router)
app.include_router(passport.router)
app.include_router(admin_auth.router)
app.include_router(admin_catalog.router)
app.include_router(admin_community.router)
app.include_router(admin_curation.router)
app.include_router(admin_analytics.router)
app.include_router(admin_homepage.router)
app.include_router(admin_uploads.router)
app.include_router(admin_processing.router)
app.include_router(admin_scenes.router)
app.include_router(admin_support.router)
app.include_router(admin_playback.router)
app.include_router(playback.router)
app.include_router(playback.edge_router)
if settings.feature_scene_lens_enabled:
    app.include_router(scene_intelligence.router)
app.include_router(cinephile.router)
if settings.feature_community_enabled:
    app.include_router(clubs.router)
    app.include_router(community.router)
    app.include_router(curation.router)
app.include_router(customer_catalog.router)
app.include_router(homepage.router)
app.include_router(operations.router)
app.include_router(operations.admin_router)


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


def check_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def check_object_storage() -> None:
    client = boto3.client(
        "s3",
        endpoint_url=str(settings.s3_endpoint),
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(s3={"addressing_style": "path"}),
    )
    client.head_bucket(Bucket=settings.s3_bucket)


@app.get("/ready", tags=["operations"])
async def readiness() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        await asyncio.wait_for(asyncio.to_thread(check_database), timeout=3)
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    redis_client = redis.from_url(settings.redis_url, socket_timeout=3)
    try:
        try:
            await asyncio.wait_for(redis_client.ping(), timeout=3)
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "error"
    finally:
        await redis_client.aclose()
    try:
        await asyncio.wait_for(asyncio.to_thread(check_object_storage), timeout=3)
        checks["object_storage"] = "ok"
    except Exception:
        checks["object_storage"] = "error"
    ready = all(value == "ok" for value in checks.values())
    if not ready:
        sentry_sdk.capture_message("readiness check failed", level="error")
        log_event(logger, "readiness.failed", checks=checks)
    return JSONResponse(
        {"status": "ready" if ready else "unavailable", "checks": checks},
        status_code=200 if ready else 503,
    )
