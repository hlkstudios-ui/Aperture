from functools import lru_cache

from pydantic import AnyHttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    app_env: str = "development"
    api_origin: AnyHttpUrl = "http://localhost:8000"
    web_origin: AnyHttpUrl = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://anime_streaming_dev:replace_for_local_development@localhost:5432/anime_streaming_dev"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: AnyHttpUrl = "http://localhost:9000"
    s3_public_endpoint: AnyHttpUrl | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "anime-streaming-development"
    s3_access_key: str = "replace_for_local_development"
    s3_secret_key: str = "replace_for_local_development"
    upload_max_bytes: int = 5 * 1024 * 1024 * 1024
    upload_url_ttl_seconds: int = 900
    customer_session_cookie: str = "aperture_session"
    admin_session_cookie: str = "aperture_admin_session"
    session_cookie_domain: str | None = None
    admin_session_cookie_domain: str | None = None
    admin_web_origin: AnyHttpUrl | None = None
    private_studio_required: bool = False
    studio_edge_secret: str | None = None
    customer_session_days: int = 30
    admin_session_hours: int = 12
    registration_rate_limit_per_hour: int = 10
    session_secret: str = "replace_with_a_long_random_local_secret"
    oauth_google_client_id: str | None = None
    oauth_google_client_secret: str | None = None
    oauth_microsoft_client_id: str | None = None
    oauth_microsoft_client_secret: str | None = None
    oauth_github_client_id: str | None = None
    oauth_github_client_secret: str | None = None
    oauth_apple_client_id: str | None = None
    oauth_apple_client_secret: str | None = None
    turnstile_secret_key: str | None = None
    tmdb_api_read_access_token: str | None = None
    tmdb_api_key: str | None = None
    tmdb_language: str = "en-CA"
    tmdb_region: str = "CA"
    captcha_required: bool = False
    captcha_test_mode: bool = True
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_starttls: bool = True
    billing_provider: str = "development_stub"
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    analytics_retention_days: int = 90
    analytics_max_batch_size: int = 25
    error_tracking_dsn: str | None = None
    metrics_bearer_token: str = "development-observability-token"
    queue_backlog_alert_threshold: int = 25
    queued_job_age_alert_seconds: int = 300
    processing_failure_alert_threshold: int = 3
    media_job_lease_seconds: int = 300
    media_job_max_attempts: int = 3
    scene_job_lease_seconds: int = 300
    scene_job_max_attempts: int = 3
    media_delivery_mode: str = "api_proxy"
    cdn_public_origin: AnyHttpUrl | None = None
    cdn_signing_secret: str | None = None
    cdn_origin_secret: str | None = None
    cdn_token_ttl_seconds: int = 300
    feature_scene_lens_enabled: bool = True
    feature_ask_movie_enabled: bool = True
    feature_community_enabled: bool = True
    feature_watch_parties_enabled: bool = True
    feature_experimental_recommendations_enabled: bool = True
    malware_scanner_mode: str = "eicar"
    malware_scanner_host: str | None = None
    malware_scanner_port: int = 3310
    malware_scanner_timeout_seconds: int = 30
    playback_lease_seconds: int = 300
    geo_assertion_secret: str = "replace_with_a_long_random_local_geo_secret"
    geo_assertion_max_age_seconds: int = 120

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        placeholders = ("replace_", "change_me", "changeme")
        if self.app_env in {"staging", "production"} and (
            self.session_secret.lower().startswith(placeholders) or len(self.session_secret) < 32
        ):
            raise ValueError("SESSION_SECRET must be a strong environment-specific secret")
        if (
            self.app_env in {"staging", "production"}
            and self.captcha_required
            and self.captcha_test_mode
        ):
            raise ValueError("CAPTCHA_TEST_MODE must be disabled outside development")
        if (
            self.app_env in {"staging", "production"}
            and self.captcha_required
            and not self.turnstile_secret_key
        ):
            raise ValueError("TURNSTILE_SECRET_KEY is required when CAPTCHA is enabled")
        if self.app_env in {"staging", "production"} and (
            any(value in self.database_url.lower() for value in placeholders)
            or self.s3_access_key.lower().startswith(placeholders)
            or self.s3_secret_key.lower().startswith(placeholders)
        ):
            raise ValueError("Database and object-storage credentials must be environment-specific")
        if self.app_env in {"staging", "production"} and not all(
            (self.smtp_host, self.smtp_username, self.smtp_password, self.smtp_from_email)
        ):
            raise ValueError("SMTP settings are required for staging and production")
        if (
            self.app_env in {"staging", "production"}
            and self.billing_provider == "development_stub"
        ):
            raise ValueError(
                "BILLING_PROVIDER must not use the development stub in staging/production"
            )
        if self.billing_provider == "stripe" and not all(
            (self.stripe_secret_key, self.stripe_webhook_secret)
        ):
            raise ValueError(
                "STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET are required for Stripe billing"
            )
        if (
            self.app_env == "production"
            and self.billing_provider == "stripe"
            and not (self.stripe_secret_key or "").startswith("sk_live_")
        ):
            raise ValueError("Production Stripe billing requires a live secret key")
        if self.app_env == "production" and (
            str(self.api_origin).startswith("http://") or str(self.web_origin).startswith("http://")
        ):
            raise ValueError("Production public origins must use HTTPS")
        if (
            self.app_env == "production"
            and self.s3_public_endpoint is not None
            and str(self.s3_public_endpoint).startswith("http://")
        ):
            raise ValueError("Production public object-storage origin must use HTTPS")
        if self.app_env in {"staging", "production"} and (
            self.metrics_bearer_token.lower().startswith((*placeholders, "development"))
            or len(self.metrics_bearer_token) < 32
        ):
            raise ValueError("METRICS_BEARER_TOKEN must be a strong environment-specific secret")
        if self.app_env == "production" and not self.error_tracking_dsn:
            raise ValueError("ERROR_TRACKING_DSN is required in production")
        if self.upload_max_bytes <= 0 or self.upload_max_bytes > 5 * 1024 * 1024 * 1024:
            raise ValueError("UPLOAD_MAX_BYTES must be between 1 byte and 5 GiB")
        if not 60 <= self.upload_url_ttl_seconds <= 3600:
            raise ValueError("UPLOAD_URL_TTL_SECONDS must be between 60 and 3600")
        if not 30 <= self.analytics_retention_days <= 730:
            raise ValueError("ANALYTICS_RETENTION_DAYS must be between 30 and 730")
        if not 1 <= self.analytics_max_batch_size <= 50:
            raise ValueError("ANALYTICS_MAX_BATCH_SIZE must be between 1 and 50")
        if self.queue_backlog_alert_threshold < 1:
            raise ValueError("QUEUE_BACKLOG_ALERT_THRESHOLD must be positive")
        if self.queued_job_age_alert_seconds < 30:
            raise ValueError("QUEUED_JOB_AGE_ALERT_SECONDS must be at least 30")
        if self.processing_failure_alert_threshold < 1:
            raise ValueError("PROCESSING_FAILURE_ALERT_THRESHOLD must be positive")
        if self.media_job_lease_seconds < 60:
            raise ValueError("MEDIA_JOB_LEASE_SECONDS must be at least 60")
        if not 1 <= self.media_job_max_attempts <= 10:
            raise ValueError("MEDIA_JOB_MAX_ATTEMPTS must be between 1 and 10")
        if self.scene_job_lease_seconds < 60:
            raise ValueError("SCENE_JOB_LEASE_SECONDS must be at least 60")
        if not 1 <= self.scene_job_max_attempts <= 10:
            raise ValueError("SCENE_JOB_MAX_ATTEMPTS must be between 1 and 10")
        if self.media_delivery_mode not in {"api_proxy", "cdn"}:
            raise ValueError("MEDIA_DELIVERY_MODE must be api_proxy or cdn")
        if self.media_delivery_mode == "cdn" and not all(
            (self.cdn_public_origin, self.cdn_signing_secret, self.cdn_origin_secret)
        ):
            raise ValueError("CDN delivery requires public origin and both edge secrets")
        if self.app_env == "production" and self.media_delivery_mode != "cdn":
            raise ValueError("Production requires protected CDN media delivery")
        if self.media_delivery_mode == "cdn" and (
            len(self.cdn_signing_secret or "") < 32 or len(self.cdn_origin_secret or "") < 32
        ):
            raise ValueError("CDN secrets must each contain at least 32 characters")
        if self.media_delivery_mode == "cdn" and not str(self.cdn_public_origin).startswith(
            "https://"
        ):
            raise ValueError("CDN_PUBLIC_ORIGIN must use HTTPS")
        if self.app_env == "production" and any(
            value.lower().startswith((*placeholders, "dummy"))
            for value in (self.cdn_signing_secret or "", self.cdn_origin_secret or "")
        ):
            raise ValueError("Production CDN secrets must not be placeholders")
        if not 60 <= self.cdn_token_ttl_seconds <= 900:
            raise ValueError("CDN_TOKEN_TTL_SECONDS must be between 60 and 900")
        if self.registration_rate_limit_per_hour < 1:
            raise ValueError("REGISTRATION_RATE_LIMIT_PER_HOUR must be positive")
        if self.malware_scanner_mode not in {"disabled", "eicar", "clamav_tcp"}:
            raise ValueError("MALWARE_SCANNER_MODE must be disabled, eicar, or clamav_tcp")
        if self.app_env in {"staging", "production"} and self.malware_scanner_mode == "disabled":
            raise ValueError("Malware scanning must not be disabled in staging/production")
        if self.app_env == "production" and self.malware_scanner_mode != "clamav_tcp":
            raise ValueError("Production requires the ClamAV TCP malware scanner")
        if self.malware_scanner_mode == "clamav_tcp" and not self.malware_scanner_host:
            raise ValueError("ClamAV TCP scanning requires MALWARE_SCANNER_HOST")
        if not 1 <= self.malware_scanner_port <= 65535:
            raise ValueError("MALWARE_SCANNER_PORT is invalid")
        if not 1 <= self.malware_scanner_timeout_seconds <= 300:
            raise ValueError("MALWARE_SCANNER_TIMEOUT_SECONDS must be between 1 and 300")
        if not 30 <= self.playback_lease_seconds <= 600:
            raise ValueError("PLAYBACK_LEASE_SECONDS must be between 30 and 600")
        if not 30 <= self.geo_assertion_max_age_seconds <= 300:
            raise ValueError("GEO_ASSERTION_MAX_AGE_SECONDS must be between 30 and 300")
        if self.app_env in {"staging", "production"} and (
            self.geo_assertion_secret.lower().startswith((*placeholders, "dummy"))
            or len(self.geo_assertion_secret) < 32
        ):
            raise ValueError("GEO_ASSERTION_SECRET must be a strong environment-specific secret")
        if (
            self.media_delivery_mode == "cdn"
            and self.playback_lease_seconds < self.cdn_token_ttl_seconds
        ):
            raise ValueError("PLAYBACK_LEASE_SECONDS must cover CDN_TOKEN_TTL_SECONDS")
        if self.app_env == "production" and not self.private_studio_required:
            raise ValueError("PRIVATE_STUDIO_REQUIRED must be enabled in production")
        if self.private_studio_required and (
            len(self.studio_edge_secret or "") < 32
            or (self.studio_edge_secret or "").lower().startswith(("dummy", "replace_"))
        ):
            raise ValueError(
                "STUDIO_EDGE_SECRET must be a non-placeholder secret of at least 32 characters"
            )
        if self.private_studio_required and self.admin_web_origin is None:
            raise ValueError("ADMIN_WEB_ORIGIN is required for private Studio")
        if self.private_studio_required and not str(self.admin_web_origin).startswith("https://"):
            raise ValueError("ADMIN_WEB_ORIGIN must use HTTPS")
        if self.private_studio_required and self.admin_session_cookie_domain is not None:
            raise ValueError("Private Studio administrator cookies must remain host-only")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
