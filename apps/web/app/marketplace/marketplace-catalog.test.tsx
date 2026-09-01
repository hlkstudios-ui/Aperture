import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarketplaceCatalog } from "./marketplace-catalog";
import type { PlatformTemplate } from "./platform-marketplace";

const agreementHash = "a".repeat(64);
const templateId = "11111111-1111-4111-8111-111111111111";
const versionId = "22222222-2222-4222-8222-222222222222";
const agreementId = "33333333-3333-4333-8333-333333333333";
const verifiedAccount = {
  id: "account-1",
  email: "owner@example.com",
  email_verified: true,
  unverified_account_expires_at: null,
  created_at: "2026-08-31T12:00:00Z",
};
const unverifiedAccount = {
  ...verifiedAccount,
  email_verified: false,
  unverified_account_expires_at: "2026-09-02T12:00:00Z",
};

function template(overrides: Partial<PlatformTemplate> = {}): PlatformTemplate {
  return {
    id: templateId,
    slug: "apertures",
    name: "Apertures",
    description: "A complete cinema platform for movies, series, anime, and podcasts.",
    category: "Streaming platform",
    thumbnail_url: null,
    preview_assets: [],
    demo_url: "https://apertures.online",
    status: "published",
    current_version: {
      id: versionId,
      version: "1.0.0",
      feature_manifest: { features: ["Movies", "Series", { label: "Custom identity" }] },
      configuration_schema: {},
    },
    starting_price: { price_cents: 4900, currency: "USD", interval: "month" },
    rental_available: true,
    unavailable_reason: null,
    ...overrides,
  };
}

const detail = {
  ...template(),
  rental_agreement: {
    id: agreementId,
    version: "2026-01",
    title: "Apertures template rental agreement",
    content: "These are the complete, immutable rental terms.\n\nReview every provision before accepting.",
    content_sha256: agreementHash,
    published_at: "2026-08-31T12:00:00Z",
  },
};

const rental = {
  schema_version: 1,
  id: "44444444-4444-4444-8444-444444444444",
  status: "awaiting_payment",
  tenant: {
    id: "55555555-5555-4555-8555-555555555555",
    slug: "north-star-cinema",
    business_name: "North Star Cinema",
    hosted_hostname: "north-star-cinema.apertures.online",
    status: "reserved",
  },
  template: {
    id: templateId,
    slug: "apertures",
    name: "Apertures",
    version_id: versionId,
    version: "1.0.0",
  },
  price_snapshot: { price_cents: 4900, currency: "USD", interval: "month" },
  legal_acceptance: {
    id: "66666666-6666-4666-8666-666666666666",
    agreement_version_id: agreementId,
    version: "2026-01",
    content_sha256: agreementHash,
    accepted_at: "2026-08-31T12:30:00Z",
  },
  platform_billing: { status: "disabled", checkout_available: false },
  provisioning_status: "not_started",
  domain_status: "not_created",
  next_action: "platform_billing_unavailable",
  reservation_active: true,
  reservation_expires_at: "2026-09-01T12:30:00Z",
  status_changed_at: "2026-08-31T12:30:00Z",
  expired_at: null,
  created_at: "2026-08-31T12:30:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("Apertures marketplace catalog", () => {
  it("renders professional registry cards and keeps unavailable server reasons visible", () => {
    const preview = template({
      id: "template-2",
      slug: "apertures-preview",
      name: "Preview only",
      status: "preview",
      current_version: null,
      starting_price: null,
      demo_url: null,
      rental_available: false,
      unavailable_reason: "An approved release and agreement have not been published.",
    });

    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template(), preview] }} />);

    expect(screen.getByRole("heading", { name: "Apertures" })).toBeInTheDocument();
    expect(screen.getByText("$49")).toBeInTheDocument();
    expect(screen.getByText("Custom identity")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View preview/ })).toHaveAttribute("href", "https://apertures.online");
    expect(screen.getByRole("button", { name: "Rent Preview only" })).toBeDisabled();
    expect(screen.getByText("An approved release and agreement have not been published.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview unavailable" })).toBeDisabled();
  });

  it("fails closed when the server-side registry is unavailable", () => {
    render(<MarketplaceCatalog initialState={{ status: "unavailable", reason: "Registry offline; rental is paused." }} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Marketplace temporarily unavailable");
    expect(screen.getByRole("alert")).toHaveTextContent("Registry offline; rental is paused.");
    expect(screen.queryByRole("button", { name: /Rent/ })).not.toBeInTheDocument();
  });

  it("opens terms over the catalogue, gates continuation on consent, and restores focus", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json(detail)));
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);
    const trigger = screen.getByRole("button", { name: "Rent Apertures" });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = await screen.findByRole("dialog", { name: "Apertures" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Apertures" })).toHaveLength(2);
    expect(screen.getByText(/complete, immutable rental terms/)).toBeInTheDocument();
    const continueButton = screen.getByRole("button", { name: /Continue securely/ });
    expect(continueButton).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    expect(continueButton).toBeEnabled();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("uses separate platform auth and retries one rental payload with the same idempotency key", async () => {
    let rentalAttempts = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      if (url.endsWith("/platform/auth/me")) return Response.json({ detail: "Not authenticated" }, { status: 401 });
      if (url.endsWith("/platform/auth/config")) return Response.json({ captcha: { required: false, test_mode: false } });
      if (url.endsWith("/platform/auth/login")) {
        return Response.json({
          id: "account-1",
          email: "owner@example.com",
          email_verified: true,
          unverified_account_expires_at: null,
          created_at: "2026-08-31T12:00:00Z",
        });
      }
      if (url.endsWith("/platform/rental-intents")) {
        rentalAttempts += 1;
        return rentalAttempts === 1
          ? Response.json({ detail: "The reservation service is restarting." }, { status: 503 })
          : Response.json(rental);
      }
      throw new Error(`Unexpected fetch: ${url} (${init?.method ?? "GET"})`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue securely/ }));

    await screen.findByRole("heading", { name: "Continue your rental request." });
    const emailField = screen.getByLabelText("Email address");
    await waitFor(() => expect(emailField).toHaveFocus());
    const outsideControl = document.createElement("button");
    document.body.append(outsideControl);
    outsideControl.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Close rental dialog" })).toHaveFocus();
    outsideControl.remove();
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in and continue" })).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "owner@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct horse battery staple" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in and continue" }));

    await screen.findByRole("heading", { name: "Name your front door." });
    fireEvent.change(screen.getByLabelText("Business name"), { target: { value: "North Star Cinema" } });
    fireEvent.change(screen.getByLabelText("Desired Apertures-hosted address"), { target: { value: "north-star-cinema" } });
    fireEvent.click(screen.getByRole("button", { name: "Reserve rental request" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The reservation service is restarting.");
    fireEvent.click(screen.getByRole("button", { name: "Reserve rental request" }));

    expect(await screen.findByRole("heading", { name: "Your rental request is reserved." })).toBeInTheDocument();
    expect(screen.getByText(/No charge was attempted/)).toBeInTheDocument();
    expect(screen.getByText("Checkout unavailable")).toBeInTheDocument();
    expect(screen.getByText("north-star-cinema.apertures.online")).toBeInTheDocument();

    const authCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/platform/auth/login"));
    expect(authCall).toBeDefined();
    expect(JSON.parse(String(authCall?.[1]?.body))).toEqual({
      email: "owner@example.com",
      password: "correct horse battery staple",
      captcha_token: null,
    });
    const rentalCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/platform/rental-intents"));
    expect(rentalCalls).toHaveLength(2);
    const firstHeaders = new Headers(rentalCalls[0][1]?.headers);
    const secondHeaders = new Headers(rentalCalls[1][1]?.headers);
    expect(firstHeaders.get("Idempotency-Key")).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    expect(secondHeaders.get("Idempotency-Key")).toBe(firstHeaders.get("Idempotency-Key"));
    expect(JSON.parse(String(rentalCalls[0][1]?.body))).toEqual({
      template_slug: "apertures",
      template_version_id: versionId,
      agreement_version_id: agreementId,
      agreement_version: "2026-01",
      agreement_sha256: agreementHash,
      business_name: "North Star Cinema",
      requested_tenant_slug: "north-star-cinema",
      accepted: true,
    });
  });

  it("keeps an unverified login in an accessible verification step and supports resend and confirm", async () => {
    let confirmationAttempts = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      if (url.endsWith("/platform/auth/me")) return Response.json({ detail: "Not authenticated" }, { status: 401 });
      if (url.endsWith("/platform/auth/config")) return Response.json({ captcha: { required: false, test_mode: false } });
      if (url.endsWith("/platform/auth/login")) return Response.json(unverifiedAccount);
      if (url.endsWith("/platform/auth/email-verification/resend")) {
        return Response.json({
          status: "sent",
          verification_token_expires_at: "2026-08-31T13:00:00Z",
          development_verification_token: null,
        });
      }
      if (url.endsWith("/platform/auth/email-verification/confirm")) {
        confirmationAttempts += 1;
        return confirmationAttempts === 1
          ? Response.json({
            detail: {
              code: "platform_email_verification_invalid",
              message: "Email verification token is invalid or expired.",
            },
          }, { status: 400 })
          : Response.json(verifiedAccount);
      }
      throw new Error(`Unexpected fetch: ${url} (${_init?.method ?? "GET"})`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue securely/ }));
    await screen.findByRole("heading", { name: "Continue your rental request." });
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in and continue" })).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "owner@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct horse battery staple" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in and continue" }));

    expect(await screen.findByRole("heading", { name: "Verify your renter account." })).toBeInTheDocument();
    const tokenField = screen.getByLabelText("Verification token");
    expect(tokenField).toHaveValue("");
    expect(screen.getByText(/This unverified account remains claimable until/)).toBeInTheDocument();
    expect(screen.queryByText(/current verification link and token expire/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reserve rental request" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/platform/rental-intents"))).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Request a new verification email" }));
    expect(await screen.findByText("A new verification email has been sent.")).toBeInTheDocument();
    expect(screen.getByText(/current verification link and token expire/)).toBeInTheDocument();
    fireEvent.change(tokenField, { target: { value: "x".repeat(32) } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm email and continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email verification token is invalid or expired.");
    fireEvent.change(tokenField, { target: { value: "y".repeat(32) } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm email and continue" }));

    expect(await screen.findByRole("heading", { name: "Name your front door." })).toBeInTheDocument();
    const confirmCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/platform/auth/email-verification/confirm"));
    expect(confirmCalls).toHaveLength(2);
    expect(JSON.parse(String(confirmCalls[1][1]?.body))).toEqual({ token: "y".repeat(32) });
  });

  it("routes an existing unverified session to verification without exposing rental submission", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      if (url.endsWith("/platform/auth/me")) return Response.json(unverifiedAccount);
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue securely/ }));

    expect(await screen.findByRole("heading", { name: "Verify your renter account." })).toBeInTheDocument();
    expect(screen.getByLabelText("Verification token")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Reserve rental request" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/platform/auth/config"))).toBe(false);
  });

  it("uses a registration development token only when the server explicitly returns one", async () => {
    const developmentToken = "development-verification-token-123456789";
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      if (url.endsWith("/platform/auth/me")) return Response.json({ detail: "Not authenticated" }, { status: 401 });
      if (url.endsWith("/platform/auth/config")) return Response.json({ captcha: { required: false, test_mode: false } });
      if (url.endsWith("/platform/auth/register")) {
        return Response.json({
          ...unverifiedAccount,
          verification_delivery: "development",
          verification_token_expires_at: "2026-08-31T13:00:00Z",
          development_verification_token: developmentToken,
        }, { status: 201 });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue securely/ }));
    await screen.findByRole("heading", { name: "Continue your rental request." });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Create account and continue" })).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "owner@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Correct horse battery 1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account and continue" }));

    expect(await screen.findByRole("heading", { name: "Verify your renter account." })).toBeInTheDocument();
    expect(screen.getByText(developmentToken)).toBeInTheDocument();
    expect(screen.getByLabelText("Verification token")).toHaveValue(developmentToken);
    expect(screen.getByText(/This unverified account remains claimable until/)).toBeInTheDocument();
    expect(screen.getByText(/current verification link and token expire/)).toBeInTheDocument();
  });

  it("keeps the account claim deadline when initial verification delivery is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      if (url.endsWith("/platform/auth/me")) return Response.json({ detail: "Not authenticated" }, { status: 401 });
      if (url.endsWith("/platform/auth/config")) return Response.json({ captcha: { required: false, test_mode: false } });
      if (url.endsWith("/platform/auth/register")) {
        return Response.json({
          ...unverifiedAccount,
          verification_delivery: "unavailable",
          verification_token_expires_at: null,
          development_verification_token: null,
        }, { status: 201 });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue securely/ }));
    await screen.findByRole("heading", { name: "Continue your rental request." });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Create account and continue" })).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "owner@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Correct horse battery 1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account and continue" }));

    expect(await screen.findByRole("heading", { name: "Verify your renter account." })).toBeInTheDocument();
    expect(screen.getByText(/This unverified account remains claimable until/)).toBeInTheDocument();
    expect(screen.getByText(/Email delivery is unavailable right now/)).toBeInTheDocument();
    expect(screen.queryByText(/current verification link and token expire/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Verification token")).toHaveValue("");
  });

  it("confirms a verification fragment automatically and removes the token from the URL", async () => {
    const token = "fragment-verification-token-123456789";
    window.history.replaceState(null, "", `/marketplace#verify-email=${encodeURIComponent(token)}`);
    const fetchMock = vi.fn(async (input: string | URL | Request, _init?: RequestInit) => {
      if (String(input).endsWith("/platform/auth/email-verification/confirm")) {
        return Response.json(verifiedAccount);
      }
      throw new Error(`Unexpected fetch: ${String(input)} (${_init?.method ?? "GET"})`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StrictMode>
        <MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />
      </StrictMode>,
    );

    expect(await screen.findByText("Your platform account email is verified.")).toHaveAttribute("role", "status");
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/marketplace");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ token });
  });

  it("aborts automatic fragment confirmation when the catalog unmounts", async () => {
    const token = "unmounted-fragment-confirmation-token-123456789";
    let resolveConfirmation!: (response: Response) => void;
    const pendingConfirmation = new Promise<Response>((resolve) => {
      resolveConfirmation = resolve;
    });
    window.history.replaceState(null, "", `/marketplace#verify-email=${encodeURIComponent(token)}`);
    const fetchMock = vi.fn((input: string | URL | Request, init?: RequestInit) => {
      if (String(input).endsWith("/platform/auth/email-verification/confirm")) {
        return pendingConfirmation;
      }
      return Promise.reject(new Error(`Unexpected fetch: ${String(input)} (${init?.method ?? "GET"})`));
    });
    vi.stubGlobal("fetch", fetchMock);

    const view = render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const signal = fetchMock.mock.calls[0][1]?.signal as AbortSignal | undefined;
    expect(signal?.aborted).toBe(false);
    view.unmount();
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      resolveConfirmation(Response.json(verifiedAccount));
      await pendingConfirmation;
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("claims an unauthenticated verification fragment with a strong new password and captcha", async () => {
    const token = "unauthenticated-fragment-token-123456789";
    const password = "Replacement Platform Password 123";
    window.history.replaceState(null, "", `/marketplace#verify-email=${encodeURIComponent(token)}`);
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/platform/auth/email-verification/confirm")) {
        return Response.json({ detail: "Platform authentication required" }, { status: 401 });
      }
      if (url.endsWith("/platform/auth/config")) {
        return Response.json({ captcha: { required: true, test_mode: true } });
      }
      if (url.endsWith("/platform/auth/email-verification/claim")) {
        return Response.json(verifiedAccount);
      }
      throw new Error(`Unexpected fetch: ${url} (${init?.method ?? "GET"})`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    expect(await screen.findByRole("heading", { name: "Set a password to finish verification." })).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    expect(document.body).not.toHaveTextContent(token);
    expect(screen.queryByLabelText("Verification token")).not.toBeInTheDocument();
    const passwordField = screen.getByLabelText("New platform account password");
    const claimButton = screen.getByRole("button", { name: "Verify email, set password, and sign in" });
    expect(claimButton).toBeDisabled();
    fireEvent.change(passwordField, { target: { value: password } });
    await waitFor(() => expect(claimButton).toBeEnabled());
    fireEvent.click(claimButton);

    expect(await screen.findByText("Your platform account email is verified and this browser is signed in.")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("heading", { name: "Set a password to finish verification." })).not.toBeInTheDocument();
    const claimCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/platform/auth/email-verification/claim"));
    expect(claimCall).toBeDefined();
    expect(JSON.parse(String(claimCall?.[1]?.body))).toEqual({
      token,
      password,
      captcha_token: "local-captcha-pass",
    });
  });

  it("offers secure claim when an authenticated browser is signed in to a different account", async () => {
    const token = "different-account-fragment-token-123456789";
    window.history.replaceState(null, "", `/marketplace#verify-email=${encodeURIComponent(token)}`);
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/platform/auth/email-verification/confirm")) {
        return Response.json({
          detail: {
            code: "platform_email_verification_invalid",
            message: "Email verification token is invalid or expired.",
          },
        }, { status: 400 });
      }
      if (url.endsWith("/platform/auth/config")) {
        return Response.json({ captcha: { required: false, test_mode: false } });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    expect(await screen.findByRole("heading", { name: "Set a password to finish verification." })).toBeInTheDocument();
    expect(screen.getByText(/belongs to a different platform account/)).toHaveAttribute("role", "status");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(token);
    expect(window.location.hash).toBe("");
  });

  it("keeps unrelated fragment-confirmation failures as errors", async () => {
    const token = "unrelated-confirmation-error-token-123456789";
    window.history.replaceState(null, "", `/marketplace#verify-email=${encodeURIComponent(token)}`);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      if (String(input).endsWith("/platform/auth/email-verification/confirm")) {
        return Response.json({
          detail: { code: "platform_origin_invalid", message: "Request origin does not match host." },
        }, { status: 400 });
      }
      throw new Error(`Unexpected fetch: ${String(input)}`);
    }));

    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Request origin does not match host.");
    expect(screen.queryByRole("heading", { name: "Set a password to finish verification." })).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(token);
    expect(window.location.hash).toBe("");
  });

  it("keeps a fragment claim alive when a rental dialog opens concurrently", async () => {
    const token = "claim-survives-rental-dialog-token-123456789";
    const password = "Concurrent Claim Password 123";
    let resolveClaim!: (response: Response) => void;
    const pendingClaim = new Promise<Response>((resolve) => {
      resolveClaim = resolve;
    });
    window.history.replaceState(null, "", `/marketplace#verify-email=${encodeURIComponent(token)}`);
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/platform/auth/email-verification/confirm")) {
        return Response.json({ detail: "Platform authentication required" }, { status: 401 });
      }
      if (url.endsWith("/platform/auth/config")) {
        return Response.json({ captcha: { required: false, test_mode: false } });
      }
      if (url.endsWith("/platform/auth/email-verification/claim")) return pendingClaim;
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      throw new Error(`Unexpected fetch: ${url} (${init?.method ?? "GET"})`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    await screen.findByRole("heading", { name: "Set a password to finish verification." });
    fireEvent.change(screen.getByLabelText("New platform account password"), { target: { value: password } });
    const claimButton = screen.getByRole("button", { name: "Verify email, set password, and sign in" });
    await waitFor(() => expect(claimButton).toBeEnabled());
    fireEvent.click(claimButton);
    expect(await screen.findByRole("button", { name: "Claiming account…" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    const claimCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/platform/auth/email-verification/claim"));
    expect((claimCall?.[1]?.signal as AbortSignal | undefined)?.aborted).toBe(false);

    await act(async () => {
      resolveClaim(Response.json(verifiedAccount));
      await pendingClaim;
    });
    expect(await screen.findByText("Your platform account email is verified and this browser is signed in.")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("heading", { name: "Set a password to finish verification." })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Apertures" })).toBeInTheDocument();
  });

  it("atomically advances a matching verification step after a late fragment confirmation", async () => {
    const token = "late-matching-fragment-confirmation-123456789";
    let resolveConfirmation!: (response: Response) => void;
    const pendingConfirmation = new Promise<Response>((resolve) => {
      resolveConfirmation = resolve;
    });
    window.history.replaceState(null, "", `/marketplace#verify-email=${encodeURIComponent(token)}`);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/platform/auth/email-verification/confirm")) return pendingConfirmation;
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      if (url.endsWith("/platform/auth/me")) return Response.json(unverifiedAccount);
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue securely/ }));
    expect(await screen.findByRole("heading", { name: "Verify your renter account." })).toBeInTheDocument();

    await act(async () => {
      resolveConfirmation(Response.json(verifiedAccount));
      await pendingConfirmation;
    });
    expect(await screen.findByRole("heading", { name: "Name your front door." })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Verify your renter account." })).not.toBeInTheDocument();
  });

  it("does not let a late fragment confirmation overwrite a newer platform login", async () => {
    const token = "late-stale-account-confirmation-token-123456789";
    const newerAccount = {
      ...verifiedAccount,
      id: "account-2",
      email: "newer@example.com",
    };
    let resolveConfirmation!: (response: Response) => void;
    const pendingConfirmation = new Promise<Response>((resolve) => {
      resolveConfirmation = resolve;
    });
    window.history.replaceState(null, "", `/marketplace#verify-email=${encodeURIComponent(token)}`);
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/platform/auth/email-verification/confirm")) return pendingConfirmation;
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      if (url.endsWith("/platform/auth/me")) return Response.json({ detail: "Not authenticated" }, { status: 401 });
      if (url.endsWith("/platform/auth/config")) return Response.json({ captcha: { required: false, test_mode: false } });
      if (url.endsWith("/platform/auth/login")) return Response.json(newerAccount);
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue securely/ }));
    await screen.findByRole("heading", { name: "Continue your rental request." });
    await waitFor(() => expect(screen.getByRole("button", { name: "Sign in and continue" })).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: newerAccount.email } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct horse battery staple" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in and continue" }));
    expect(await screen.findByRole("heading", { name: "Name your front door." })).toBeInTheDocument();
    expect(screen.getByText(newerAccount.email)).toBeInTheDocument();

    await act(async () => {
      resolveConfirmation(Response.json(verifiedAccount));
      await pendingConfirmation;
    });
    expect(screen.getByRole("heading", { name: "Name your front door." })).toBeInTheDocument();
    expect(screen.getByText(newerAccount.email)).toBeInTheDocument();
    expect(screen.queryByText(verifiedAccount.email)).not.toBeInTheDocument();
  });

  it("does not claim success for an expired idempotency replay and rotates the next request key", async () => {
    const expiredRental = {
      ...rental,
      status: "expired",
      tenant: { ...rental.tenant, status: "released" },
      next_action: "start_new_rental_request",
      reservation_active: false,
      status_changed_at: "2026-09-01T12:30:00Z",
      expired_at: "2026-09-01T12:30:00Z",
    };
    let rentalAttempts = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      if (url.endsWith("/platform/auth/me")) return Response.json(verifiedAccount);
      if (url.endsWith("/platform/rental-intents")) {
        rentalAttempts += 1;
        return rentalAttempts === 1
          ? Response.json(expiredRental, { headers: { "Idempotency-Replayed": "true" } })
          : Response.json(rental);
      }
      throw new Error(`Unexpected fetch: ${url} (${_init?.method ?? "GET"})`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketplaceCatalog initialState={{ status: "ready", templates: [template()] }} />);

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue securely/ }));
    await screen.findByRole("heading", { name: "Name your front door." });
    fireEvent.change(screen.getByLabelText("Business name"), { target: { value: "North Star Cinema" } });
    fireEvent.change(screen.getByLabelText("Desired Apertures-hosted address"), { target: { value: "north-star-cinema" } });
    fireEvent.click(screen.getByRole("button", { name: "Reserve rental request" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/rental reservation expired/i);
    expect(screen.queryByRole("heading", { name: "Your rental request is reserved." })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reserve rental request" }));
    expect(await screen.findByRole("heading", { name: "Your rental request is reserved." })).toBeInTheDocument();

    const rentalCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/platform/rental-intents"));
    const firstKey = new Headers(rentalCalls[0][1]?.headers).get("Idempotency-Key");
    const secondKey = new Headers(rentalCalls[1][1]?.headers).get("Idempotency-Key");
    expect(firstKey).toMatch(/^[0-9a-f-]{36}$/i);
    expect(secondKey).toMatch(/^[0-9a-f-]{36}$/i);
    expect(secondKey).not.toBe(firstKey);
  });

  it("ignores an account response from a closed flow after another template opens", async () => {
    let resolveStaleAccount!: (response: Response) => void;
    const staleAccount = new Promise<Response>((resolve) => {
      resolveStaleAccount = resolve;
    });
    const secondTemplate = template({
      id: "44444444-4444-4444-8444-444444444444",
      slug: "second-system",
      name: "Second System",
      current_version: {
        id: "55555555-5555-4555-8555-555555555555",
        version: "2.0.0",
        feature_manifest: { features: ["Independent branding"] },
        configuration_schema: {},
      },
    });
    const secondDetail = {
      ...secondTemplate,
      rental_agreement: {
        id: "66666666-6666-4666-8666-666666666666",
        version: "2026-02",
        title: "Second system rental agreement",
        content: "These terms belong only to the second system and its exact release.",
        content_sha256: "b".repeat(64),
        published_at: "2026-08-31T13:00:00Z",
      },
    };
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/platform/templates/apertures")) return Response.json(detail);
      if (url.endsWith("/platform/templates/second-system")) return Response.json(secondDetail);
      if (url.endsWith("/platform/auth/me")) return staleAccount;
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    render(
      <MarketplaceCatalog
        initialState={{ status: "ready", templates: [template(), secondTemplate] }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Rent Apertures" }));
    await screen.findByText(/complete, immutable rental terms/);
    fireEvent.click(screen.getByRole("checkbox", { name: /read and accept this exact rental agreement/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue securely/ }));
    await screen.findByText(/Checking your Apertures platform account/);

    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Rent Second System" }));
    await screen.findByText(/terms belong only to the second system/);

    await act(async () => {
      resolveStaleAccount(Response.json({
        id: "77777777-7777-4777-8777-777777777777",
        email: "stale@example.com",
        email_verified: true,
        unverified_account_expires_at: null,
        created_at: "2026-08-31T12:00:00Z",
      }));
      await staleAccount;
    });

    expect(screen.getByRole("dialog", { name: "Second System" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Second system rental agreement" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Name your front door." })).not.toBeInTheDocument();
  });
});
