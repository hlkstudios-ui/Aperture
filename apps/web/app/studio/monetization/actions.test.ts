import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  redirect: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    mocks.redirect(url);
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
}));
vi.mock("@/app/lib/admin-catalog", () => ({
  adminCatalogFetch: mocks.fetch,
  CatalogActionError: class CatalogActionError extends Error {
    constructor(public detail: string) { super(detail); }
  },
}));

import {
  beginStripeConnectAction,
  refreshMonetizationStatusAction,
  type MonetizationActionState,
} from "./actions";

const initial: MonetizationActionState = { sequence: 0, error: "", notice: "" };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetch.mockResolvedValue({});
});

describe("viewer monetization actions", () => {
  it("starts hosted Stripe onboarding and only redirects to Stripe Connect", async () => {
    mocks.fetch.mockResolvedValueOnce({ onboarding_url: "https://connect.stripe.com/setup/s/test" });

    await expect(beginStripeConnectAction(initial)).rejects.toThrow("NEXT_REDIRECT");
    expect(mocks.fetch).toHaveBeenCalledWith(
      "/admin/viewer-monetization/providers/stripe/connect",
      { method: "POST" },
    );
    expect(mocks.redirect).toHaveBeenCalledWith("https://connect.stripe.com/setup/s/test");
  });

  it("rejects a non-Stripe onboarding redirect", async () => {
    mocks.fetch.mockResolvedValueOnce({ onboarding_url: "https://evil.example/collect" });

    const result = await beginStripeConnectAction(initial);
    expect(result.error).toMatch(/invalid hosted onboarding address/i);
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("refreshes provider state without changing viewer access", async () => {
    const result = await refreshMonetizationStatusAction(initial);

    expect(mocks.fetch).toHaveBeenCalledWith("/admin/viewer-monetization/refresh", { method: "POST" });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/studio/monetization");
    expect(result.notice).toMatch(/Free access and paid-checkout availability remain unchanged/i);
  });

});
