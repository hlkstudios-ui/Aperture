import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { customerAccountFetch, type AccountDashboard } from "@/app/lib/account";
import { requireCustomerSession, type ViewerAccount } from "@/app/lib/customer-session";

import AccountPage from "./page";

vi.mock("@/app/components/site-header", () => ({ SiteHeader: () => <div data-testid="site-header" /> }));
vi.mock("@/app/lib/account", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/app/lib/account")>();
  return { ...original, customerAccountFetch: vi.fn() };
});
vi.mock("@/app/lib/customer-session", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/app/lib/customer-session")>();
  return { ...original, requireCustomerSession: vi.fn() };
});
vi.mock("./actions", () => ({
  openBillingPortal: vi.fn(),
  revokeOtherSessions: vi.fn(),
  revokeSession: vi.fn(),
  setLanguagePreferences: vi.fn(),
  setPrivacyPreferences: vi.fn(),
  setRewatchIntelligence: vi.fn(),
  startCheckout: vi.fn(),
}));
vi.mock("./password-form", () => ({ PasswordForm: () => <div>Password controls</div> }));

const viewer: ViewerAccount = {
  id: "account-1",
  email: "viewer@example.com",
  active_profile_id: "profile-1",
  profiles: [{
    id: "profile-1",
    name: "Harjot",
    avatar_key: null,
    maturity_level: "adult",
    language: "en",
    is_kids: false,
    preference: {
      autoplay_next: true,
      autoplay_previews: true,
      preferred_audio_language: "en",
      preferred_subtitle_language: "en",
      preferred_secondary_subtitle_language: null,
      subtitles_enabled: false,
      timezone: "America/Toronto",
      caption_size: "medium",
      caption_background: "shadow",
      caption_position: "bottom",
      cinephile_mode: false,
      rewatch_intelligence_enabled: true,
      analytics_enabled: false,
      consent_updated_at: null,
      homepage_mode: "curated",
    },
  }],
};

const dashboard: AccountDashboard = {
  email: viewer.email,
  subscription: null,
  entitlements: [],
  sessions: [{
    id: "session-1",
    current: true,
    user_agent: "Desktop test browser",
    ip_address: "127.0.0.1",
    created_at: "2026-08-20T00:00:00Z",
    last_seen_at: "2026-08-20T00:00:00Z",
    expires_at: "2026-09-20T00:00:00Z",
  }],
  plans: [{
    id: "plan-1",
    code: "essential",
    name: "Essential",
    description: "One stream with the complete film catalog.",
    price_cents: 999,
    currency: "CAD",
    interval: "month",
    max_streams: 1,
    max_resolution: "1080p",
  }],
  billing: {
    provider: "disabled",
    production_ready: false,
    checkout_available: false,
    notice: "Payments are intentionally disabled for this launch. No payment can be accepted.",
  },
};

beforeEach(() => {
  vi.mocked(requireCustomerSession).mockResolvedValue(viewer);
  vi.mocked(customerAccountFetch).mockResolvedValue(dashboard);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AccountPage projection ledger", () => {
  it("keeps every account control discoverable inside the branded layout", async () => {
    render(await AccountPage());

    expect(screen.getByRole("heading", { name: "The projection ledger." })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Account control index" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No active subscription" })).toBeInTheDocument();
    expect(screen.getByText(/payments are intentionally disabled/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /choose essential/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Checkout unavailable" })).toBeDisabled();

    const playback = screen.getByRole("form", { name: "Harjot playback preferences" });
    expect(within(playback).getByLabelText("Interface language")).toHaveValue("en");
    expect(within(playback).getByLabelText("Enable subtitles by default")).not.toBeChecked();
    expect(within(playback).getByRole("button", { name: "Save language preferences" })).toBeEnabled();

    const privacy = screen.getByRole("form", { name: "Harjot privacy preferences" });
    expect(within(privacy).getByLabelText("Share optional usage and playback-quality analytics")).not.toBeChecked();
    expect(within(privacy).getByRole("button", { name: "Save privacy choices" })).toBeEnabled();
  });
});
