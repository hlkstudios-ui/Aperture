from dataclasses import dataclass
from typing import Protocol

import stripe

from app.config import get_settings
from app.models import Plan, User


class BillingUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckoutResult:
    provider: str
    checkout_url: str
    external_reference: str


@dataclass(frozen=True)
class PortalResult:
    provider: str
    portal_url: str


class BillingProvider(Protocol):
    name: str
    production_ready: bool

    def create_checkout(self, user: User, plan: Plan) -> CheckoutResult: ...

    def create_portal(self, customer_reference: str) -> PortalResult: ...


class DevelopmentBillingProvider:
    name = "development_stub"
    production_ready = False

    def create_checkout(self, user: User, plan: Plan) -> CheckoutResult:
        del user, plan
        raise BillingUnavailable(
            "Development billing stub is non-production and does not process or simulate payments"
        )

    def create_portal(self, customer_reference: str) -> PortalResult:
        del customer_reference
        raise BillingUnavailable("Development billing stub has no customer portal")


@dataclass(frozen=True)
class UnavailableBillingProvider:
    name: str
    production_ready: bool = False

    def create_checkout(self, user: User, plan: Plan) -> CheckoutResult:
        del user, plan
        raise BillingUnavailable(f"Billing provider '{self.name}' is not installed")

    def create_portal(self, customer_reference: str) -> PortalResult:
        del customer_reference
        raise BillingUnavailable(f"Billing provider '{self.name}' is not installed")


@dataclass(frozen=True)
class StripeBillingProvider:
    secret_key: str
    name: str = "stripe"
    production_ready: bool = True

    def create_checkout(self, user: User, plan: Plan) -> CheckoutResult:
        settings = get_settings()
        try:
            session = stripe.checkout.Session.create(
                api_key=self.secret_key,
                idempotency_key=f"checkout:{user.id}:{plan.id}",
                mode="subscription",
                customer_email=user.email,
                client_reference_id=str(user.id),
                line_items=[
                    {
                        "price_data": {
                            "currency": plan.currency.lower(),
                            "product_data": {"name": plan.name, "description": plan.description},
                            "recurring": {"interval": plan.interval.value},
                            "unit_amount": plan.price_cents,
                        },
                        "quantity": 1,
                    }
                ],
                metadata={"user_id": str(user.id), "plan_code": plan.code},
                subscription_data={"metadata": {"user_id": str(user.id), "plan_code": plan.code}},
                success_url=f"{str(settings.web_origin).rstrip('/')}/account?checkout=success",
                cancel_url=f"{str(settings.web_origin).rstrip('/')}/account?checkout=canceled",
            )
        except stripe.StripeError as exc:
            raise BillingUnavailable("Stripe checkout is temporarily unavailable") from exc
        if not session.url:
            raise BillingUnavailable("Stripe checkout did not return a redirect URL")
        return CheckoutResult(
            provider=self.name,
            checkout_url=session.url,
            external_reference=session.id,
        )

    def create_portal(self, customer_reference: str) -> PortalResult:
        settings = get_settings()
        try:
            session = stripe.billing_portal.Session.create(
                api_key=self.secret_key,
                customer=customer_reference,
                return_url=f"{str(settings.web_origin).rstrip('/')}/account",
            )
        except stripe.StripeError as exc:
            raise BillingUnavailable("Stripe billing portal is temporarily unavailable") from exc
        if not session.url:
            raise BillingUnavailable("Stripe billing portal did not return a redirect URL")
        return PortalResult(provider=self.name, portal_url=session.url)


def get_billing_provider() -> BillingProvider:
    configured = get_settings().billing_provider
    if configured == "development_stub":
        return DevelopmentBillingProvider()
    if configured == "stripe":
        return StripeBillingProvider(secret_key=get_settings().stripe_secret_key or "")
    return UnavailableBillingProvider(name=configured)
