from types import SimpleNamespace

import pytest
import stripe

from app.billing import (
    BillingUnavailable,
    DisabledBillingProvider,
    StripeBillingProvider,
    get_billing_provider,
)
from app.config import Settings


def test_disabled_provider_is_explicit_and_never_calls_stripe(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.billing.get_settings",
        lambda: SimpleNamespace(
            billing_provider="disabled",
            stripe_secret_key="sk_live_unused_must_not_be_called",
        ),
    )
    monkeypatch.setattr(
        "app.billing.stripe.checkout.Session.create",
        lambda **_: pytest.fail("disabled billing must not call Stripe Checkout"),
    )
    monkeypatch.setattr(
        "app.billing.stripe.billing_portal.Session.create",
        lambda **_: pytest.fail("disabled billing must not call Stripe Portal"),
    )

    provider = get_billing_provider()
    assert isinstance(provider, DisabledBillingProvider)
    assert provider.name == "disabled"
    assert provider.production_ready is False
    with pytest.raises(BillingUnavailable, match="intentionally disabled"):
        provider.create_checkout(SimpleNamespace(), SimpleNamespace())
    with pytest.raises(BillingUnavailable, match="intentionally disabled"):
        provider.create_portal("cus_unused")


def test_unknown_billing_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be disabled"):
        Settings(_env_file=None, billing_provider="striep")


def test_stripe_checkout_uses_subscription_mode_and_plan_metadata(monkeypatch) -> None:
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_test_fake", url="https://checkout.stripe.test/fake")

    monkeypatch.setattr("app.billing.stripe.checkout.Session.create", create)
    monkeypatch.setattr(
        "app.billing.get_settings",
        lambda: SimpleNamespace(web_origin="https://watch.example.com"),
    )
    user = SimpleNamespace(id="11111111-1111-1111-1111-111111111111", email="viewer@example.com")
    plan = SimpleNamespace(
        id="22222222-2222-2222-2222-222222222222",
        code="essential-monthly",
        name="Essential",
        description="Essential plan",
        currency="CAD",
        interval=SimpleNamespace(value="month"),
        price_cents=1299,
    )

    result = StripeBillingProvider("sk_test_fake_only").create_checkout(
        user, plan, return_origin="https://watch.customer.example"
    )

    assert result.provider == "stripe"
    assert result.checkout_url == "https://checkout.stripe.test/fake"
    assert captured["api_key"] == "sk_test_fake_only"
    assert captured["idempotency_key"] == (
        "checkout:11111111-1111-1111-1111-111111111111:22222222-2222-2222-2222-222222222222"
    )
    assert captured["mode"] == "subscription"
    assert captured["line_items"][0]["price_data"]["unit_amount"] == 1299
    assert captured["metadata"] == {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "plan_code": "essential-monthly",
    }
    assert captured["success_url"] == (
        "https://watch.customer.example/account?checkout=success"
    )
    assert captured["cancel_url"] == (
        "https://watch.customer.example/account?checkout=canceled"
    )


def test_stripe_checkout_fails_closed_without_redirect(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.billing.stripe.checkout.Session.create",
        lambda **_: SimpleNamespace(id="cs_test_fake", url=None),
    )
    monkeypatch.setattr(
        "app.billing.get_settings",
        lambda: SimpleNamespace(web_origin="https://watch.example.com"),
    )
    user = SimpleNamespace(id="user", email="viewer@example.com")
    plan = SimpleNamespace(
        id="plan-id",
        code="plan",
        name="Plan",
        description="Plan",
        currency="CAD",
        interval=SimpleNamespace(value="month"),
        price_cents=100,
    )
    with pytest.raises(BillingUnavailable):
        StripeBillingProvider("sk_test_fake_only").create_checkout(user, plan)


def test_stripe_rejects_a_non_origin_return_address(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.billing.stripe.checkout.Session.create",
        lambda **_: pytest.fail("an invalid return address must fail before Stripe"),
    )
    user = SimpleNamespace(id="user", email="viewer@example.com")
    plan = SimpleNamespace(id="plan")
    with pytest.raises(BillingUnavailable, match="return address"):
        StripeBillingProvider("sk_test_fake_only").create_checkout(
            user,
            plan,
            return_origin="https://attacker.example/redirect",
        )


def test_stripe_portal_uses_provider_customer_and_safe_return(monkeypatch) -> None:
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url="https://billing.stripe.test/fake")

    monkeypatch.setattr("app.billing.stripe.billing_portal.Session.create", create)
    monkeypatch.setattr(
        "app.billing.get_settings",
        lambda: SimpleNamespace(web_origin="https://watch.example.com"),
    )
    result = StripeBillingProvider("sk_test_fake_only").create_portal(
        "cus_test_fake", return_origin="https://watch.customer.example"
    )
    assert result.portal_url == "https://billing.stripe.test/fake"
    assert captured == {
        "api_key": "sk_test_fake_only",
        "customer": "cus_test_fake",
        "return_url": "https://watch.customer.example/account",
    }


def test_stripe_checkout_redacts_provider_error(monkeypatch) -> None:
    def fail(**_):
        raise stripe.APIConnectionError("contains upstream detail")

    monkeypatch.setattr("app.billing.stripe.checkout.Session.create", fail)
    monkeypatch.setattr(
        "app.billing.get_settings",
        lambda: SimpleNamespace(web_origin="https://watch.example.com"),
    )
    user = SimpleNamespace(id="user", email="viewer@example.com")
    plan = SimpleNamespace(
        id="plan-id",
        code="plan",
        name="Plan",
        description="Plan",
        currency="CAD",
        interval=SimpleNamespace(value="month"),
        price_cents=100,
    )
    with pytest.raises(BillingUnavailable, match="temporarily unavailable"):
        StripeBillingProvider("sk_test_fake_only").create_checkout(user, plan)


def test_stripe_fake_credentials_are_allowed_only_outside_production() -> None:
    staging = Settings(
        _env_file=None,
        app_env="staging",
        billing_provider="stripe",
        stripe_secret_key="sk_test_fake_only",
        stripe_webhook_secret="whsec_fake_only",
        platform_control_plane_enabled=False,
        captcha_required=False,
        captcha_test_mode=False,
        session_secret="s" * 40,
        database_url="postgresql+psycopg://staging:fake@db/staging",
        s3_access_key="fake-access",
        s3_secret_key="fake-secret",
        smtp_host="smtp.example.com",
        smtp_username="fake-user",
        smtp_password="fake-password",
        smtp_from_email="billing@example.com",
        metrics_bearer_token="m" * 40,
        geo_assertion_secret="g" * 40,
    )
    assert staging.billing_provider == "stripe"

    with pytest.raises(ValueError, match="live secret key"):
        Settings(
            _env_file=None,
            app_env="production",
            api_origin="https://watch.example.com/api",
            web_origin="https://watch.example.com",
            billing_provider="stripe",
            stripe_secret_key="sk_test_fake_only",
            stripe_webhook_secret="whsec_fake_only",
            platform_control_plane_enabled=False,
            captcha_required=False,
            captcha_test_mode=False,
            session_secret="s" * 40,
            database_url="postgresql+psycopg://production:fake@db/production",
            s3_endpoint="https://tor1.digitaloceanspaces.com",
            s3_access_key="fake-access",
            s3_secret_key="fake-secret",
            smtp_host="smtp.example.com",
            smtp_username="fake-user",
            smtp_password="fake-password",
            smtp_from_email="billing@example.com",
            metrics_bearer_token="m" * 40,
            error_tracking_dsn="https://public@example.ingest.sentry.io/1",
        )
