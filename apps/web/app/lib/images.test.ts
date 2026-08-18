import { describe, expect, it } from "vitest";
import { optimizedBackdrop, optimizedPoster, optimizedStill } from "./images";

describe("responsive image URLs", () => {
  const tmdb = "https://image.tmdb.org/t/p/original/example.jpg";

  it("selects bounded TMDB poster, backdrop, and still widths", () => {
    expect(optimizedPoster(tmdb, 185)).toContain("/w185/");
    expect(optimizedBackdrop(tmdb, 780)).toContain("/w780/");
    expect(optimizedStill(tmdb, 300)).toContain("/w300/");
  });

  it("does not rewrite owner-controlled or private artwork origins", () => {
    const privateArtwork = "https://media.example.com/private/poster.jpg";
    expect(optimizedPoster(privateArtwork, 185)).toBe(privateArtwork);
    expect(optimizedBackdrop(privateArtwork, 780)).toBe(privateArtwork);
    expect(optimizedStill(privateArtwork, 300)).toBe(privateArtwork);
  });
});
