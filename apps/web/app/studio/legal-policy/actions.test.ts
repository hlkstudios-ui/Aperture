import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/app/lib/admin-catalog", () => ({
  adminCatalogFetch: mocks.fetch,
  CatalogActionError: class CatalogActionError extends Error {
    constructor(public detail: string) {
      super(detail);
    }
  },
}));

import { saveLegalPolicyDraftAction, type LegalPolicyFormState } from "./actions";

const initial: LegalPolicyFormState = {
  sequence: 0,
  revision: 3,
  updatedAt: null,
  error: "",
  notice: "",
};

function form(overrides: Record<string, string> = {}): FormData {
  const data = new FormData();
  const values = {
    revision: "3",
    legal_operator_name: "",
    country_code: "",
    region: "",
    support_email: "",
    privacy_email: "",
    copyright_email: "",
    minimum_user_age: "",
    governing_law_jurisdiction: "",
    ...overrides,
  };
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetch.mockResolvedValue({
    schema_version: 1,
    revision: 4,
    status: "draft",
    legal_operator_name: "HLK Studios Inc.",
    country_code: "CA",
    region: "Ontario",
    support_email: null,
    privacy_email: "privacy@example.com",
    copyright_email: null,
    minimum_user_age: 13,
    governing_law_jurisdiction: "Ontario, Canada",
    updated_at: "2026-08-31T05:00:00Z",
  });
});

describe("saveLegalPolicyDraftAction", () => {
  it("normalizes and saves only the complete editable draft contract", async () => {
    const result = await saveLegalPolicyDraftAction(initial, form({
      legal_operator_name: "  HLK   Studios Inc. ",
      country_code: " ca ",
      region: " Ontario ",
      privacy_email: " privacy@example.com ",
      minimum_user_age: "13",
      governing_law_jurisdiction: " Ontario,   Canada ",
    }));

    expect(mocks.fetch).toHaveBeenCalledWith("/admin/site/legal-policy", {
      method: "PUT",
      body: JSON.stringify({
        revision: 3,
        legal_operator_name: "HLK Studios Inc.",
        country_code: "CA",
        region: "Ontario",
        support_email: null,
        privacy_email: "privacy@example.com",
        copyright_email: null,
        minimum_user_age: 13,
        governing_law_jurisdiction: "Ontario, Canada",
      }),
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/studio/legal-policy");
    expect(result).toEqual(expect.objectContaining({
      revision: 4,
      error: "",
      notice: expect.stringMatching(/No policy was approved or published/i),
    }));
  });

  it("allows an intentionally empty partial draft without inventing policy choices", async () => {
    await saveLegalPolicyDraftAction(initial, form());

    const body = JSON.parse(String(mocks.fetch.mock.calls[0]?.[1]?.body));
    expect(body).toEqual({
      revision: 3,
      legal_operator_name: null,
      country_code: null,
      region: null,
      support_email: null,
      privacy_email: null,
      copyright_email: null,
      minimum_user_age: null,
      governing_law_jurisdiction: null,
    });
    expect(body).not.toHaveProperty("status");
    expect(body).not.toHaveProperty("approved_by");
  });

  it.each([
    [{ support_email: "not-an-email" }, /valid support email/i],
    [{ country_code: "Canada" }, /two-letter country code/i],
    [{ minimum_user_age: "13.5" }, /whole number/i],
    [{ minimum_user_age: "121" }, /0 to 120/i],
  ])("rejects invalid draft input before the API call", async (values, message) => {
    const result = await saveLegalPolicyDraftAction(initial, form(values));

    expect(result.error).toMatch(message);
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it("rejects a stale rendered revision before the API call", async () => {
    const result = await saveLegalPolicyDraftAction(initial, form({ revision: "2" }));

    expect(result.error).toMatch(/changed.*reload/i);
    expect(mocks.fetch).not.toHaveBeenCalled();
  });
});
