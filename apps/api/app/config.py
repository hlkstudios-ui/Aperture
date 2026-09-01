import re
from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, EmailStr, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def repository_env() -> Path:
    for directory in Path(__file__).resolve().parents:
        if (directory / ".env.example").is_file() and (directory / "package.json").is_file():
            return directory / ".env"
    return Path.cwd() / ".env"


ROOT_ENV = repository_env()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_ENV,
        env_ignore_empty=True,
        extra="ignore",
    )

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
    platform_session_cookie: str = "aperture_platform_session"
    platform_control_plane_enabled: bool = False
    session_cookie_domain: str | None = None
    admin_session_cookie_domain: str | None = None
    admin_web_origin: AnyHttpUrl | None = None
    private_studio_required: bool = False
    studio_edge_secret: str | None = None
    studio_dev_auto_login: bool = False
    studio_dev_admin_email: EmailStr | None = None
    customer_session_days: int = 30
    admin_session_hours: int = 12
    platform_session_days: int = 30
    platform_tenant_base_domain: str = "apertures.online"
    platform_email_verification_minutes: int = 30
    platform_email_delivery_lease_seconds: int = 120
    platform_unverified_account_hours: int = 24
    platform_rental_intent_hours: int = 24
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
    turnstile_site_key: str | None = None
    cloudflare_turnstile_api_token: SecretStr | None = None
    turnstile_hostname_limit: int = 10
    brand_ai_provider: str = "disabled"
    brand_ai_model: str = "gpt-5-mini"
    brand_ai_timeout_seconds: float = 12.0
    brand_ai_rate_limit_per_hour: int = 30
    openai_api_key: SecretStr | None = None
    custom_domains_enabled: bool = False
    custom_domain_infrastructure_ready: bool = False
    custom_domain_provider: str = "disabled"
    custom_domain_cname_target: str | None = None
    custom_domain_max_per_site: int = 20
    custom_domain_edge_secret: SecretStr | None = None
    cloudflare_api_token: SecretStr | None = None
    cloudflare_custom_hostnames_api_token: SecretStr | None = None
    cloudflare_zone_id: str | None = None
    cloudflare_account_id: str | None = None
    cloudflare_site_domains_kv_namespace_id: str | None = None
    cloudflare_api_timeout_seconds: float = 8.0
    tmdb_api_read_access_token: str | None = None
    tmdb_api_key: str | None = None
    tmdb_language: str = "en-CA"
    tmdb_region: str = "CA"
    movie_metadata_mode: str = "legacy"
    aperture_movie_api_origin: AnyHttpUrl | None = None
    aperture_movie_api_key: str | None = None
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
    stripe_payouts_enabled: bool = False
    stripe_connect_enabled: bool = False
    stripe_connect_platform_secret_key: SecretStr | None = None
    stripe_connect_webhook_secret: SecretStr | None = None
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
    media_source_origins: str = ""
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
        self.billing_provider = self.billing_provider.strip().lower()
        if self.billing_provider not in {"disabled", "development_stub", "stripe"}:
            raise ValueError("BILLING_PROVIDER must be disabled, development_stub, or stripe")
        self.brand_ai_provider = self.brand_ai_provider.strip().lower()
        if self.brand_ai_provider not in {"disabled", "openai"}:
            raise ValueError("BRAND_AI_PROVIDER must be disabled or openai")
        self.custom_domain_provider = self.custom_domain_provider.strip().lower()
        if self.custom_domain_provider not in {"disabled", "cloudflare"}:
            raise ValueError("CUSTOM_DOMAIN_PROVIDER must be disabled or cloudflare")
        if not 1 <= self.custom_domain_max_per_site <= 100:
            raise ValueError("CUSTOM_DOMAIN_MAX_PER_SITE must be between 1 and 100")
        if not 2 <= self.cloudflare_api_timeout_seconds <= 15:
            raise ValueError("CLOUDFLARE_API_TIMEOUT_SECONDS must be between 2 and 15")
        if self.custom_domains_enabled and self.session_cookie_domain is not None:
            raise ValueError("Custom-domain customer cookies must remain host-only")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", self.brand_ai_model):
            raise ValueError("BRAND_AI_MODEL contains unsupported characters")
        if self.brand_ai_model.startswith("ft:"):
            raise ValueError("BRAND_AI_MODEL must not use a fine-tuned model")
        if not 3 <= self.brand_ai_timeout_seconds <= 30:
            raise ValueError("BRAND_AI_TIMEOUT_SECONDS must be between 3 and 30")
        if not 1 <= self.brand_ai_rate_limit_per_hour <= 120:
            raise ValueError("BRAND_AI_RATE_LIMIT_PER_HOUR must be between 1 and 120")
        openai_api_key = (
            self.openai_api_key.get_secret_value() if self.openai_api_key is not None else ""
        )
        if self.brand_ai_provider == "openai" and not openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when BRAND_AI_PROVIDER=openai")
        if (
            self.app_env in {"staging", "production"}
            and self.brand_ai_provider == "openai"
            and openai_api_key.lower().startswith((*placeholders, "dummy"))
        ):
            raise ValueError("OPENAI_API_KEY must not be a placeholder")
        if self.studio_dev_auto_login and self.app_env != "development":
            raise ValueError("STUDIO_DEV_AUTO_LOGIN is allowed only in development")
        if self.studio_dev_auto_login and self.studio_dev_admin_email is None:
            raise ValueError(
                "STUDIO_DEV_ADMIN_EMAIL is required when STUDIO_DEV_AUTO_LOGIN is enabled"
            )
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
        if not 1 <= self.turnstile_hostname_limit <= 200:
            raise ValueError("TURNSTILE_HOSTNAME_LIMIT must be between 1 and 200")
        if (
            self.custom_domains_enabled
            and self.captcha_required
            and (
                self.turnstile_hostname_limit < 2
                or self.custom_domain_max_per_site > self.turnstile_hostname_limit - 1
            )
        ):
            raise ValueError(
                "CUSTOM_DOMAIN_MAX_PER_SITE must reserve one Turnstile hostname slot "
                "for WEB_HOSTNAME"
            )
        if self.app_env in {"staging", "production"} and (
            any(value in self.database_url.lower() for value in placeholders)
            or self.s3_access_key.lower().startswith(placeholders)
            or self.s3_secret_key.lower().startswith(placeholders)
        ):
            raise ValueError("Database and object-storage credentials must be environment-specific")
        if self.movie_metadata_mode not in {"legacy", "gateway"}:
            raise ValueError("MOVIE_METADATA_MODE must be legacy or gateway")
        if self.movie_metadata_mode == "gateway" and not all(
            (self.aperture_movie_api_origin, self.aperture_movie_api_key)
        ):
            raise ValueError(
                "Gateway metadata requires APERTURE_MOVIE_API_ORIGIN and APERTURE_MOVIE_API_KEY"
            )
        if self.app_env in {"staging", "production"} and not all(
            (self.smtp_host, self.smtp_username, self.smtp_password, self.smtp_from_email)
        ):
            raise ValueError("SMTP settings are required for staging and production")
        if self.app_env == "production" and not self.smtp_starttls:
            raise ValueError("SMTP_STARTTLS must be enabled in production")
        if (
            self.app_env in {"staging", "production"}
            and self.billing_provider == "development_stub"
        ):
            raise ValueError(
                "BILLING_PROVIDER must not use the development stub in staging/production"
            )
        if self.stripe_connect_enabled and self.billing_provider != "disabled":
            raise ValueError("STRIPE_CONNECT_ENABLED requires BILLING_PROVIDER=disabled")
        if self.billing_provider == "stripe" and not all(
            (self.stripe_secret_key, self.stripe_webhook_secret)
        ):
            raise ValueError(
                "STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET are required for Stripe billing"
            )
        if self.stripe_payouts_enabled and self.billing_provider != "stripe":
            raise ValueError("STRIPE_PAYOUTS_ENABLED requires BILLING_PROVIDER=stripe")
        stripe_connect_key = (
            self.stripe_connect_platform_secret_key.get_secret_value()
            if self.stripe_connect_platform_secret_key is not None
            else ""
        )
        stripe_connect_webhook = (
            self.stripe_connect_webhook_secret.get_secret_value()
            if self.stripe_connect_webhook_secret is not None
            else ""
        )
        if self.stripe_connect_enabled and not (stripe_connect_key and stripe_connect_webhook):
            raise ValueError(
                "STRIPE_CONNECT_PLATFORM_SECRET_KEY and STRIPE_CONNECT_WEBHOOK_SECRET "
                "are required when Stripe Connect is enabled"
            )
        if self.stripe_connect_enabled and not stripe_connect_key.startswith(
            ("sk_test_", "sk_live_")
        ):
            raise ValueError("Stripe Connect requires a Stripe platform secret key")
        if self.stripe_connect_enabled and not stripe_connect_webhook.startswith("whsec_"):
            raise ValueError("Stripe Connect requires a webhook signing secret")
        if self.stripe_connect_enabled and any(
            value.lower().startswith((*placeholders, "dummy"))
            for value in (stripe_connect_key, stripe_connect_webhook)
        ):
            raise ValueError("Stripe Connect credentials must not be placeholders")
        if (
            self.app_env == "production"
            and self.stripe_connect_enabled
            and not stripe_connect_key.startswith("sk_live_")
        ):
            raise ValueError("Production Stripe Connect requires a live platform secret key")
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
        cookie_names = {
            self.customer_session_cookie,
            self.admin_session_cookie,
            self.platform_session_cookie,
        }
        if len(cookie_names) != 3 or any(
            not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name) for name in cookie_names
        ):
            raise ValueError("Customer, administrator, and platform cookies must be distinct")
        if (
            self.app_env in {"staging", "production"}
            and self.platform_control_plane_enabled
            and not self.platform_session_cookie.startswith("__Host-")
        ):
            raise ValueError(
                "PLATFORM_SESSION_COOKIE must use the __Host- prefix when the platform "
                "control plane is enabled outside development"
            )
        if (
            self.app_env in {"staging", "production"}
            and self.platform_control_plane_enabled
            and not self.captcha_required
        ):
            raise ValueError(
                "CAPTCHA_REQUIRED must be true when the platform control plane is enabled "
                "outside development"
            )
        if not 1 <= self.platform_session_days <= 90:
            raise ValueError("PLATFORM_SESSION_DAYS must be between 1 and 90")
        if not 10 <= self.platform_email_verification_minutes <= 1440:
            raise ValueError("PLATFORM_EMAIL_VERIFICATION_MINUTES must be between 10 and 1440")
        if not 30 <= self.platform_email_delivery_lease_seconds <= 300:
            raise ValueError("PLATFORM_EMAIL_DELIVERY_LEASE_SECONDS must be between 30 and 300")
        if (
            self.platform_email_delivery_lease_seconds
            >= self.platform_email_verification_minutes * 60
        ):
            raise ValueError(
                "PLATFORM_EMAIL_DELIVERY_LEASE_SECONDS must be strictly less than the "
                "verification token lifetime"
            )
        if not 1 <= self.platform_unverified_account_hours <= 168:
            raise ValueError("PLATFORM_UNVERIFIED_ACCOUNT_HOURS must be between 1 and 168")
        if self.platform_email_verification_minutes > self.platform_unverified_account_hours * 60:
            raise ValueError(
                "PLATFORM_EMAIL_VERIFICATION_MINUTES must not outlive the unverified account"
            )
        if not 1 <= self.platform_rental_intent_hours <= 168:
            raise ValueError("PLATFORM_RENTAL_INTENT_HOURS must be between 1 and 168")
        self.platform_tenant_base_domain = (
            self.platform_tenant_base_domain.strip().lower().rstrip(".")
        )
        if not (
            len(self.platform_tenant_base_domain) <= 189
            and "." in self.platform_tenant_base_domain
            and all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in self.platform_tenant_base_domain.split(".")
            )
        ):
            raise ValueError(
                "PLATFORM_TENANT_BASE_DOMAIN must be a lower-case DNS hostname of at most "
                "189 characters"
            )
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

    @property
    def custom_domains_available(self) -> bool:
        """Return the effective feature gate without exposing provider credentials."""
        cloudflare_identifier = re.compile(r"^[0-9a-fA-F]{32}$")
        api_token = (
            self.cloudflare_custom_hostnames_api_token.get_secret_value()
            if self.cloudflare_custom_hostnames_api_token is not None
            else ""
        )
        edge_secret = (
            self.custom_domain_edge_secret.get_secret_value()
            if self.custom_domain_edge_secret is not None
            else ""
        )
        turnstile_api_token = (
            self.cloudflare_turnstile_api_token.get_secret_value()
            if self.cloudflare_turnstile_api_token is not None
            else ""
        )
        try:
            cname_target = (
                (self.custom_domain_cname_target or "")
                .strip()
                .rstrip(".")
                .encode("idna")
                .decode("ascii")
                .lower()
            )
        except UnicodeError:
            cname_target = ""
        valid_cname_target = bool(
            len(cname_target) <= 253
            and "." in cname_target
            and all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in cname_target.split(".")
            )
        )
        non_placeholder_secrets = not api_token.lower().startswith(
            ("dummy", "replace_", "change_me", "changeme")
        ) and not edge_secret.lower().startswith(("dummy", "replace_", "change_me", "changeme"))
        turnstile_ready = bool(
            not self.captcha_required
            or (
                len(turnstile_api_token) >= 20
                and not turnstile_api_token.lower().startswith(
                    ("dummy", "replace_", "change_me", "changeme")
                )
                and re.fullmatch(r"[A-Za-z0-9_-]{10,32}", self.turnstile_site_key or "")
            )
        )
        return bool(
            self.custom_domains_enabled
            and self.custom_domain_infrastructure_ready
            and self.custom_domain_provider == "cloudflare"
            and len(api_token) >= 20
            and len(edge_secret) >= 32
            and non_placeholder_secrets
            and turnstile_ready
            and valid_cname_target
            and cloudflare_identifier.fullmatch(self.cloudflare_zone_id or "")
            and cloudflare_identifier.fullmatch(self.cloudflare_account_id or "")
            and cloudflare_identifier.fullmatch(self.cloudflare_site_domains_kv_namespace_id or "")
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
