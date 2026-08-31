import { describe, expect, it } from "vitest";
import { seriesIsCurrentlyAiring, type Series } from "./catalog";

function series(overrides: Partial<Series> = {}): Series {
  return {
    is_ongoing: false,
    seasons: [],
    ...overrides,
  } as Series;
}

describe("seriesIsCurrentlyAiring", () => {
  const asOf = new Date("2026-08-27T12:00:00Z");

  it("honors the editorial ongoing flag", () => {
    expect(seriesIsCurrentlyAiring(series({ is_ongoing: true }), asOf)).toBe(true);
  });

  it("recognizes a published upcoming episode when the flag is missing", () => {
    expect(seriesIsCurrentlyAiring(series({
      seasons: [{
        id: "season-1",
        series_id: "series-1",
        number: 1,
        title: "Season 1",
        synopsis: null,
        episodes: [{
          id: "episode-1",
          season_id: "season-1",
          number: 1,
          title: "Next episode",
          synopsis: "Arriving soon.",
          runtime_minutes: 24,
          release_date: "2026-08-30",
          still_url: null,
          status: "published",
        }],
      }],
    }), asOf)).toBe(true);
  });

  it("does not infer airing from past or unpublished episodes", () => {
    const episodes = [
      { id: "past", season_id: "season-1", number: 1, title: "Past", synopsis: "", runtime_minutes: 24, release_date: "2026-08-20", still_url: null, status: "published" },
      { id: "draft", season_id: "season-1", number: 2, title: "Draft", synopsis: "", runtime_minutes: 24, release_date: "2026-09-01", still_url: null, status: "draft" },
    ];
    expect(seriesIsCurrentlyAiring(series({
      seasons: [{ id: "season-1", series_id: "series-1", number: 1, title: null, synopsis: null, episodes }],
    }), asOf)).toBe(false);
  });
});
