import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  revalidatePath: vi.fn(),
  updateTag: vi.fn(),
}));

vi.mock("next/cache", () => ({
  revalidatePath: mocks.revalidatePath,
  updateTag: mocks.updateTag,
}));
vi.mock("@/app/lib/admin-catalog", () => ({
  adminCatalogFetch: mocks.fetch,
  CatalogActionError: class CatalogActionError extends Error {
    code?: string;
    constructor(detail: string, code?: string) {
      super(detail);
      this.code = code;
    }
    get detail() { return this.message; }
  },
}));

import {
  addDomainAction,
  makePrimaryDomainAction,
  refreshDomainAction,
  removeDomainAction,
  usePlatformDomainAction,
  type DomainActionState,
} from "./actions";

const initial: DomainActionState = { sequence: 0, error: "", notice: "" };

function form(values: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

beforeEach(() => {
  mocks.fetch.mockReset();
  mocks.fetch.mockResolvedValue({});
  mocks.revalidatePath.mockReset();
  mocks.updateTag.mockReset();
});

describe("Studio domain actions", () => {
  it("adds a normalized hostname and refreshes only the Domains page", async () => {
    const result = await addDomainAction(initial, form({ hostname: "  Watch.Example.COM. " }));

    expect(mocks.fetch).toHaveBeenCalledWith("/admin/site/domains", {
      method: "POST",
      body: JSON.stringify({ hostname: "watch.example.com" }),
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/studio/domains");
    expect(mocks.updateTag).toHaveBeenCalledWith("site-domain");
    expect(result.notice).toContain("watch.example.com was added");
  });

  it("rejects URLs before making an API request", async () => {
    const result = await addDomainAction(initial, form({ hostname: "https://watch.example.com/path" }));

    expect(result.error).toContain("domain name only");
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it.each([
    [refreshDomainAction, "refresh"],
    [makePrimaryDomainAction, "make-primary"],
  ] as const)("posts the optimistic revision for %s", async (action, operation) => {
    await action(initial, form({ domain_id: "domain/1", hostname: "watch.example.com", revision: "7" }));

    expect(mocks.fetch).toHaveBeenCalledWith(`/admin/site/domains/domain%2F1/${operation}`, {
      method: "POST",
      body: JSON.stringify({ revision: 7 }),
    });
  });

  it("requires exact-host confirmation and removes by revision query", async () => {
    const mismatch = await removeDomainAction(initial, form({
      domain_id: "domain-1",
      hostname: "watch.example.com",
      revision: "9",
      confirmation: "www.example.com",
    }));
    expect(mismatch.error).toContain("Type watch.example.com exactly");
    expect(mocks.fetch).not.toHaveBeenCalled();

    await removeDomainAction(initial, form({
      domain_id: "domain-1",
      hostname: "watch.example.com",
      revision: "9",
      confirmation: "WATCH.EXAMPLE.COM.",
    }));
    expect(mocks.fetch).toHaveBeenCalledWith("/admin/site/domains/domain-1?revision=9&confirmation=watch.example.com", {
      method: "DELETE",
    });
  });

  it("switches back to the hosted address without removing custom domains", async () => {
    const result = await usePlatformDomainAction(initial, form({
      platform_hostname: "apertures.online",
      revision: "12",
    }));

    expect(mocks.fetch).toHaveBeenCalledWith("/admin/site/domains/use-platform", {
      method: "POST",
      body: JSON.stringify({ revision: 12 }),
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/studio/domains");
    expect(result.notice).toContain("Connected custom domains remain available");
  });
});
