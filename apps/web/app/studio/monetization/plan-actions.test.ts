import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), revalidatePath: vi.fn() }));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/app/lib/admin-catalog", () => ({
  adminCatalogFetch: mocks.fetch,
  CatalogActionError: class CatalogActionError extends Error {
    constructor(public detail: string) { super(detail); }
  },
}));

import {
  archiveViewerPlanAction,
  createViewerPlanAction,
  type ViewerPlanActionState,
} from "./plan-actions";

const initial: ViewerPlanActionState = { sequence: 0, error: "", notice: "" };

function createForm(overrides: Record<string, string> = {}): FormData {
  const form = new FormData();
  const values = {
    code: " Cinema  Monthly ",
    name: " Cinema   Monthly ",
    description: " Two streams with the complete catalogue. ",
    price: "12.99",
    currency: " cad ",
    interval: "month",
    max_streams: "2",
    max_resolution: "1080p",
    ...overrides,
  };
  for (const [key, value] of Object.entries(values)) form.set(key, value);
  return form;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetch.mockResolvedValue({
    id: "11111111-1111-4111-8111-111111111111",
    code: "cinema-monthly",
    name: "Cinema Monthly",
    description: "Two streams with the complete catalogue.",
    price_cents: 1299,
    currency: "CAD",
    interval: "month",
    max_streams: 2,
    max_resolution: "1080p",
    is_active: true,
    created_at: "2026-08-31T12:00:00Z",
    updated_at: "2026-08-31T12:00:00Z",
  });
});

describe("viewer plan actions", () => {
  it("normalizes owner input and converts price to integer cents", async () => {
    const result = await createViewerPlanAction(initial, createForm());

    expect(mocks.fetch).toHaveBeenCalledWith("/admin/viewer-plans", {
      method: "POST",
      body: JSON.stringify({
        code: "cinema-monthly",
        name: "Cinema Monthly",
        description: "Two streams with the complete catalogue.",
        price_cents: 1299,
        currency: "CAD",
        interval: "month",
        max_streams: 2,
        max_resolution: "1080p",
      }),
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/studio/monetization");
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/account");
    expect(result.notice).toMatch(/Free access remains unchanged/i);
  });

  it.each(["AUD", "CAD", "EUR", "GBP", "USD"])(
    "accepts the initial two-decimal currency %s",
    async (currency) => {
      await createViewerPlanAction(initial, createForm({ currency: currency.toLowerCase() }));
      const request = mocks.fetch.mock.calls[0]?.[1] as RequestInit;
      expect(JSON.parse(String(request.body))).toMatchObject({ currency });
    },
  );

  it.each([
    [{ price: "0" }, /between 0\.01/i],
    [{ price: "12.999" }, /two decimal places/i],
    [{ price: "999999999999999999999" }, /1,000,000\.00/i],
    [{ currency: "JPY" }, /AUD, CAD, EUR, GBP, or USD/i],
    [{ currency: "ZZZ" }, /AUD, CAD, EUR, GBP, or USD/i],
    [{ max_streams: "1.5" }, /whole number/i],
    [{ max_streams: "101" }, /1 to 100/i],
    [{ interval: "week" }, /monthly or yearly/i],
    [{ max_resolution: "8K" }, /720p, 1080p, or 4K/i],
  ])("rejects invalid typed values before the API call", async (values, message) => {
    const result = await createViewerPlanAction(initial, createForm(values));
    expect(result.error).toMatch(message);
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it("requires exact plan-code confirmation before archiving", async () => {
    const form = new FormData();
    form.set("plan_id", "11111111-1111-4111-8111-111111111111");
    form.set("confirmation", "Cinema Monthly");
    const refused = await archiveViewerPlanAction(initial, form);
    expect(refused.error).toMatch(/displayed plan code exactly/i);
    expect(mocks.fetch).not.toHaveBeenCalled();

    form.set("confirmation", "cinema-monthly");
    const archived = await archiveViewerPlanAction(initial, form);
    expect(mocks.fetch).toHaveBeenCalledWith(
      "/admin/viewer-plans/11111111-1111-4111-8111-111111111111/archive",
      {
        method: "POST",
        body: JSON.stringify({ confirmation_code: "cinema-monthly" }),
      },
    );
    expect(archived.notice).toMatch(/Existing subscription records were not rewritten/i);
  });

  it("returns provider-safe API errors without claiming an archive succeeded", async () => {
    const { CatalogActionError } = await import("@/app/lib/admin-catalog");
    mocks.fetch.mockRejectedValueOnce(new CatalogActionError(
      "Create another active plan before archiving the final plan",
    ));
    const form = new FormData();
    form.set("plan_id", "11111111-1111-4111-8111-111111111111");
    form.set("confirmation", "cinema-monthly");

    const result = await archiveViewerPlanAction(initial, form);
    expect(result.error).toMatch(/Create another active plan/i);
    expect(result.notice).toBe("");
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });
});
