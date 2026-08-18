import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WatchMoviePage from "./page";

const playbackFetch = vi.fn();
vi.mock("@/app/lib/playback", () => ({
  playbackFetch: (...args: unknown[]) => playbackFetch(...args),
  isPlaybackUnavailable: (value: object) => "error" in value,
}));

describe("watch stream-limit state", () => {
  beforeEach(() => playbackFetch.mockReset());

  it("explains how to recover when the account stream limit is reached", async () => {
    playbackFetch.mockResolvedValue({
      error: "stream_limit",
      message: "This account is already streaming on the maximum number of devices.",
    });

    render(await WatchMoviePage({ params: Promise.resolve({ slug: "the-lantern-sea" }) }));

    expect(screen.getByRole("heading", { name: "Your account is already streaming." })).toBeInTheDocument();
    expect(screen.getByText(/Inactive device slots expire automatically/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to film" })).toHaveAttribute("href", "/movies/the-lantern-sea");
  });
});
