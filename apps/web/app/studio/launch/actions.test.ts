import { beforeEach, describe, expect, it, vi } from "vitest";

import { defaultLaunchSetup } from "./launch-setup-types";
import { CatalogActionError } from "@/app/lib/admin-catalog";

const actionMocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  revalidatePath: vi.fn(),
  updateTag: vi.fn(),
}));

vi.mock("@/app/lib/admin-catalog", () => {
  class CatalogActionError extends Error {
    constructor(public detail: string, public code?: string) {
      super(detail);
    }
  }
  return { adminCatalogFetch: actionMocks.fetch, CatalogActionError };
});
vi.mock("@/app/lib/admin-session", () => ({ requireAdminSession: vi.fn() }));
vi.mock("@/app/lib/studio-edge", () => ({ studioEdgeHeaders: vi.fn(() => ({})) }));
vi.mock("next/cache", () => ({
  revalidatePath: actionMocks.revalidatePath,
  updateTag: actionMocks.updateTag,
}));
vi.mock("next/headers", () => ({ cookies: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));

import { assistBrandCopyAction, mutateLaunchSetupAction } from "./actions";

const suggestions = [
  {
    short_name: "Northstar",
    tagline: "The screen, seen differently.",
    description: "A considered home for daring films and the people who love them.",
    tone_direction: "Editorial and assured",
  },
  {
    short_name: "Northstar House",
    tagline: "Stay for the final frame.",
    description: "Cinema with a point of view, selected for endlessly curious viewers.",
    tone_direction: "Intimate and cinematic",
  },
  {
    short_name: "Northstar",
    tagline: "Your next obsession starts here.",
    description: "A vivid destination for cult discoveries and stories worth sharing.",
    tone_direction: "Bold and contemporary",
  },
];

describe("launch copy assistance actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("requests three suggestions without a revision or draft mutation", async () => {
    actionMocks.fetch.mockResolvedValueOnce({ generated_by: "ai", suggestions });

    const result = await assistBrandCopyAction({
      business_name: "Northstar Cinema",
      short_name: null,
      existing_tagline: "Films that leave the light on.",
      existing_description: null,
      audience: "Independent-film devotees",
      tone: "refined",
      additional_direction: "Avoid clichés.",
    });

    expect(result).toEqual({ error: "", suggestions });
    expect(actionMocks.fetch).toHaveBeenCalledOnce();
    const [path, init] = actionMocks.fetch.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/admin/site/brand/assist-copy");
    expect(JSON.parse(String(init.body))).toEqual({
      business_name: "Northstar Cinema",
      short_name: null,
      existing_tagline: "Films that leave the light on.",
      existing_description: null,
      audience: "Independent-film devotees",
      tone: "refined",
      additional_direction: "Avoid clichés.",
    });
    expect(actionMocks.revalidatePath).not.toHaveBeenCalled();
    expect(actionMocks.updateTag).not.toHaveBeenCalled();
  });

  it("rejects an incomplete provider result without exposing it to the editor", async () => {
    actionMocks.fetch.mockResolvedValueOnce({ generated_by: "ai", suggestions: suggestions.slice(0, 2) });

    const result = await assistBrandCopyAction({
      business_name: "Northstar Cinema",
      short_name: null,
      existing_tagline: null,
      existing_description: null,
      audience: null,
      tone: "cinematic",
      additional_direction: null,
    });

    expect(result.suggestions).toEqual([]);
    expect(result.error).toMatch(/incomplete set/i);
  });

  it("maps stable provider error codes without depending on human-readable API copy", async () => {
    actionMocks.fetch.mockRejectedValueOnce(
      new CatalogActionError("Ce service est indisponible.", "brand_ai_unavailable"),
    );

    const result = await assistBrandCopyAction({
      business_name: "Northstar Cinema",
      short_name: null,
      existing_tagline: null,
      existing_description: null,
      audience: null,
      tone: "cinematic",
      additional_direction: null,
    });

    expect(result.suggestions).toEqual([]);
    expect(result.error).toMatch(/not available yet/i);
  });

  it("preserves an AI-applied compact name in the explicit Stage 1 save", async () => {
    actionMocks.fetch.mockResolvedValueOnce({
      ...defaultLaunchSetup,
      revision: 1,
      current_step: 2,
      completed_steps: [1],
      config: { ...defaultLaunchSetup.config, business_name: "Northstar Cinema", short_name: "Northstar" },
    });
    const form = new FormData();
    form.set("revision", "0");
    form.set("step", "1");
    form.set("current_step", "1");
    form.set("completed_steps", "[]");
    form.set("intent", "save");
    form.set("payload", JSON.stringify({
      business_name: "Northstar Cinema",
      short_name: "Northstar",
      tagline: "The screen, seen differently.",
      description: "A considered home for daring films and the people who love them.",
      palette: {
        accent: defaultLaunchSetup.config.palette.accent,
        accent_hover: defaultLaunchSetup.config.palette.accent_hover,
        surface: defaultLaunchSetup.config.palette.surface,
        surface_elevated: defaultLaunchSetup.config.palette.surface_elevated,
        text: defaultLaunchSetup.config.palette.text,
        text_muted: defaultLaunchSetup.config.palette.text_muted,
      },
      locale: defaultLaunchSetup.config.locale,
    }));

    const result = await mutateLaunchSetupAction(
      { sequence: 0, error: "", notice: "", setup: null },
      form,
    );

    expect(result.error).toBe("");
    const [, init] = actionMocks.fetch.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body)).config).toEqual(expect.objectContaining({ short_name: "Northstar" }));
  });
});
