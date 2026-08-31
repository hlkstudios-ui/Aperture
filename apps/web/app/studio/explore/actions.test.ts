import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ExploreCardTitle, ExploreEntry } from "@/app/lib/explore";

const actionMocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("@/app/lib/admin-catalog", () => ({
  adminCatalogFetch: actionMocks.fetch,
}));
vi.mock("next/cache", () => ({
  revalidatePath: actionMocks.revalidatePath,
}));

import {
  attachExploreCard,
  moveExploreCard,
  removeExploreCard,
  toggleExploreEntry,
} from "./actions";

function title(id: string, kind: "movie" | "series", name: string): ExploreCardTitle {
  return {
    id,
    kind,
    title: name,
    original_title: null,
    slug: name.toLocaleLowerCase().replaceAll(" ", "-"),
    short_description: "A Studio-programmed title.",
    release_date: "2026-08-27",
    maturity_rating: "PG",
    poster_url: null,
    content_format: kind === "movie" ? "movie" : "tv",
    country_code: "CA",
    original_language_code: "en",
    studios: ["Northstar"],
    genres: ["Drama"],
    duration_minutes: kind === "movie" ? 102 : 24,
    is_ongoing: kind === "series" ? true : null,
    season_count: kind === "series" ? 2 : 0,
    episode_count: kind === "series" ? 18 : 0,
    href: `/titles/${kind}/${id}`,
    source: "local",
    availability: "Explore this title",
  };
}

function entry(overrides: Partial<ExploreEntry> = {}): ExploreEntry {
  return {
    id: "5a8ab95a-5f10-4da1-b8f7-1cc9e3a73a80",
    label: "Series Spotlight",
    description: "Episodic stories selected by Studio.",
    icon: "*",
    position: 3,
    enabled: true,
    criteria: {
      content_type: "series",
      query: null,
      genre: "Animation",
      studio: null,
      country_code: "CA",
      original_language_code: "en",
      maturity_rating: "PG",
      release_period: "2020s",
      duration: "standard",
      airing: "ongoing",
    },
    cards: [],
    ...overrides,
  };
}

describe("Explore Studio actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends an exact write payload when toggling an entry", async () => {
    const entry: ExploreEntry = {
      id: "5a8ab95a-5f10-4da1-b8f7-1cc9e3a73a80",
      label: "Series Spotlight",
      description: "Episodic stories selected by Studio.",
      icon: "✦",
      position: 3,
      enabled: true,
      criteria: {
        content_type: "series",
        query: null,
        genre: "Animation",
        studio: null,
        country_code: "CA",
        original_language_code: "en",
        maturity_rating: "PG",
        release_period: "2020s",
        duration: "standard",
        airing: "ongoing",
      },
      created_at: "2026-08-27T14:00:00Z",
      updated_at: "2026-08-27T14:30:00Z",
    };
    actionMocks.fetch.mockResolvedValueOnce([entry]).mockResolvedValueOnce({
      ...entry,
      enabled: false,
    });

    await toggleExploreEntry(entry.id, false);

    expect(actionMocks.fetch).toHaveBeenNthCalledWith(1, "/admin/explore");
    expect(actionMocks.fetch).toHaveBeenNthCalledWith(
      2,
      `/admin/explore/${entry.id}`,
      expect.objectContaining({ method: "PUT" }),
    );
    const [, init] = actionMocks.fetch.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      label: entry.label,
      description: entry.description,
      icon: entry.icon,
      position: entry.position,
      enabled: false,
      criteria: entry.criteria,
    });
    expect(actionMocks.revalidatePath).toHaveBeenCalledWith("/studio/explore");
    expect(actionMocks.revalidatePath).toHaveBeenCalledWith("/");
  });

  it("attaches a selected title after the existing pinned cards", async () => {
    const current = entry({
      cards: [{
        id: "card-1",
        movie_id: "movie-1",
        series_id: null,
        position: 4,
        title: title("movie-1", "movie", "Lantern Sea"),
      }],
    });
    actionMocks.fetch.mockResolvedValueOnce([current]).mockResolvedValueOnce(undefined);
    const form = new FormData();
    form.set("title", "series:series-2");

    await attachExploreCard(current.id, form);

    expect(actionMocks.fetch).toHaveBeenNthCalledWith(1, "/admin/explore");
    expect(actionMocks.fetch).toHaveBeenNthCalledWith(
      2,
      `/admin/explore/${current.id}/cards`,
      expect.objectContaining({ method: "POST" }),
    );
    const [, init] = actionMocks.fetch.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      movie_id: null,
      series_id: "series-2",
      position: 5,
    });
  });

  it("reorders the complete card association set by saved position", async () => {
    const current = entry({
      cards: [
        { id: "card-2", movie_id: null, series_id: "series-2", position: 8, title: title("series-2", "series", "Night Signal") },
        { id: "card-1", movie_id: "movie-1", series_id: null, position: 2, title: title("movie-1", "movie", "Lantern Sea") },
      ],
    });
    actionMocks.fetch.mockResolvedValueOnce([current]).mockResolvedValueOnce(undefined);

    await moveExploreCard(current.id, "card-2", -1);

    expect(actionMocks.fetch).toHaveBeenNthCalledWith(
      2,
      `/admin/explore/${current.id}/cards/order`,
      expect.objectContaining({ method: "PUT" }),
    );
    const [, init] = actionMocks.fetch.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ ids: ["card-2", "card-1"] });
  });

  it("removes a card association and refreshes Studio and the storefront", async () => {
    actionMocks.fetch.mockResolvedValueOnce(undefined);

    await removeExploreCard("card-1");

    expect(actionMocks.fetch).toHaveBeenCalledWith("/admin/explore/cards/card-1", { method: "DELETE" });
    expect(actionMocks.revalidatePath).toHaveBeenCalledWith("/studio/explore");
    expect(actionMocks.revalidatePath).toHaveBeenCalledWith("/");
  });
});
