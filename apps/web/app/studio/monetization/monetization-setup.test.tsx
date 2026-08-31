import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ViewerMonetizationRecord } from "./monetization-types";

const mocks = vi.hoisted(() => ({ connect: vi.fn(), refresh: vi.fn() }));

vi.mock("./actions", () => ({
  beginStripeConnectAction: mocks.connect,
  refreshMonetizationStatusAction: mocks.refresh,
}));

import { MonetizationSetup } from "./monetization-setup";

function record(overrides: Partial<ViewerMonetizationRecord> = {}): ViewerMonetizationRecord {
  return {
    schema_version: 1,
    revision: 2,
    access_mode: "free",
    access_mode_change_available: false,
    provider: "disabled",
    connection: "disabled",
    connected_account_id: null,
    livemode: null,
    details_submitted: false,
    charges_enabled: false,
    payouts_enabled: false,
    requirements_due: [],
    active_plan_count: 0,
    subscription_mode_eligible: false,
    updated_at: null,
    notice: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  for (const action of [mocks.connect, mocks.refresh]) {
    action.mockImplementation(async (state: unknown) => state);
  }
});

describe("MonetizationSetup", () => {
  it("keeps free access explicit and separates viewer revenue from the Aperture rental", () => {
    render(<MonetizationSetup record={record()} />);

    expect(screen.getByText("Free access")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /prepare future viewer revenue separately/i })).toBeInTheDocument();
    expect(screen.getByText("Your Aperture rental")).toBeInTheDocument();
    expect(screen.getByText("Your customer payments")).toBeInTheDocument();
    expect(screen.getByText(/Connecting or completing Stripe onboarding never changes this setting/i)).toBeInTheDocument();
    expect(screen.getByText(/Subscription activation is not available in this release/i)).toBeInTheDocument();
    expect(screen.getByText(/does not enable checkout or route viewer revenue yet/i)).toBeInTheDocument();
  });

  it("fails closed when the Stripe Connect runtime is disabled", () => {
    render(<MonetizationSetup record={record()} />);

    const setup = screen.getByRole("button", { name: "Stripe setup unavailable" });
    expect(screen.getByText("Provider unavailable")).toBeInTheDocument();
    expect(screen.getByText("Provider runtime disabled")).toBeInTheDocument();
    expect(setup).toBeDisabled();
    expect(setup).toHaveAccessibleDescription(/server-side Stripe Connect setup must be enabled/i);
    expect(screen.getByRole("button", { name: "Refresh provider status" })).toBeDisabled();
  });

  it("offers hosted Stripe setup without API-key or bank-detail inputs when the runtime is available", () => {
    render(<MonetizationSetup record={record({
      provider: "stripe_connect",
      connection: "not_connected",
    })} />);

    expect(screen.getByRole("button", { name: "Set up Stripe securely" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Refresh provider status" })).toBeDisabled();
    expect(screen.getByText(/No API-key or bank form/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Bank payout is handled by the payment provider/i })).toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(document.querySelector('input[name*="bank"]')).toBeNull();
    expect(document.querySelector('input[name*="key"]')).toBeNull();
  });

  it("shows provider facts and requirements without claiming the paywall is active", () => {
    render(<MonetizationSetup record={record({
      provider: "stripe_connect",
      connection: "ready",
      connected_account_id: "acct_...1234",
      livemode: false,
      details_submitted: true,
      charges_enabled: true,
      payouts_enabled: false,
      requirements_due: ["external_account"],
      updated_at: "2026-08-31T12:00:00Z",
    })} />);

    expect(screen.getByText("Provider ready")).toBeInTheDocument();
    expect(screen.getByText("Stripe account ••••1234")).toBeInTheDocument();
    expect(screen.queryByText("acct_...1234")).not.toBeInTheDocument();
    expect(screen.getByText("Enabled by Stripe")).toBeInTheDocument();
    expect(screen.getAllByText("Not enabled")).toHaveLength(1);
    expect(screen.getByText("External account")).toBeInTheDocument();
    expect(screen.getByText("Free access")).toBeInTheDocument();
    expect(screen.getByText(/Subscription checkout planned, not enabled/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Activate subscription-required access" })).not.toBeInTheDocument();
  });

  it("labels future adapters as disabled with an accessible reason", () => {
    render(<MonetizationSetup record={record()} />);

    const buttons = screen.getAllByRole("button", { name: "Adapter unavailable" });
    expect(buttons).toHaveLength(2);
    for (const button of buttons) {
      expect(button).toBeDisabled();
      expect(button).toHaveAccessibleDescription();
    }
  });

});
