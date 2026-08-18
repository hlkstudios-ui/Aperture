import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("customer feature flags", () => {
  it("default to enabled for local development", async () => {
    const { featureFlags } = await import("./feature-flags");
    expect(Object.values(featureFlags).every(Boolean)).toBe(true);
  });

  it("remove disabled domains from primary and mobile navigation", async () => {
    vi.stubEnv("NEXT_PUBLIC_FEATURE_COMMUNITY_ENABLED", "false");
    vi.stubEnv("NEXT_PUBLIC_FEATURE_EXPERIMENTAL_RECOMMENDATIONS_ENABLED", "false");
    const { SiteHeader } = await import("../components/site-header");
    render(<SiteHeader />);

    expect(screen.queryByRole("link", { name: "Community" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Clubs" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Discover" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Prescription" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Movies" })).toHaveLength(2);
  });

  it("keeps SceneLens available while removing Ask This Movie independently", async () => {
    vi.doMock("../watch/components/cinephile-toolkit", () => ({ CinephileToolkit: () => null }));
    vi.stubGlobal("fetch", vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      return new Response(JSON.stringify(url.includes("relationship-graph")
        ? { nodes: [], edges: [], timestamp_seconds: 12 }
        : {
            current_scene: null, safety_state: "protected", equality_policy: "inclusive",
            completion_unlock: false, facts: [], bookmarks: [], notes: [],
          }), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    const { SceneLens } = await import("../watch/components/scene-lens");
    render(<SceneLens sourceId="source" movieId={null} episodeId={null} duration={60}
      timestamp={12} open onClose={() => undefined} askEnabled={false} />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "SceneLens" })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Scene metadata unavailable")).toBeInTheDocument());
    expect(screen.queryByText("Ask This Movie")).not.toBeInTheDocument();
  });
});
