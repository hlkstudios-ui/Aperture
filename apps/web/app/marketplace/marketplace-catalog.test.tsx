import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarketplaceCatalog } from "./marketplace-catalog";
import type { PlatformTemplate } from "./platform-marketplace";

const agreementHash = "a".repeat(64);
const templateId = "11111111-1111-4111-8111-111111111111";
const versionId = "22222222-2222-4222-8222-222222222222";
const agreementId = "33333333-3333-4333-8333-333333333333";

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
  created_at: "2026-08-31T12:30:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
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
        return Response.json({ id: "account-1", email: "owner@example.com", created_at: "2026-08-31T12:00:00Z" });
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
        created_at: "2026-08-31T12:00:00Z",
      }));
      await staleAccount;
    });

    expect(screen.getByRole("dialog", { name: "Second System" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Second system rental agreement" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Name your front door." })).not.toBeInTheDocument();
  });
});
