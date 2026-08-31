import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TrendingTitlesResponse } from "@/app/browse/browse-types";
import {
  CatalogFilterBrowser,
  type FilterTitle,
} from "@/app/components/catalog-filter-browser";
import type { ExploreEntry } from "@/app/lib/explore";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={String(href)} {...props}>{children}</a>
  ),
}));

function title(index = 1, overrides: Partial<FilterTitle> = {}): FilterTitle {
  return {
    id: `movie-${index}`,
    kind: "movie",
    title: `The Lantern Sea ${index}`,
    slug: `the-lantern-sea-${index}`,
    short_description: "A cartographer follows a light across an impossible ocean.",
    poster_url: null,
    release_date: "2026-08-15",
    maturity_rating: "PG",
    country_code: "CA",
    original_language_code: "en",
    is_ongoing: null,
    content_format: "movie",
    studios: ["Northstar"],
    genres: ["Adventure"],
    duration_minutes: 104,
    season_count: 0,
    episode_count: 0,
    audio_languages: ["en"],
    subtitle_languages: ["en"],
    ...overrides,
  };
}

function trendingResponse(overrides: Partial<TrendingTitlesResponse> = {}): TrendingTitlesResponse {
  return {
    page: 1,
    page_size: 0,
    total_results: 0,
    total_pages: 0,
    has_more: false,
    next_page: null,
    source: "aperture",
    status: "unavailable",
    items: [],
    attribution: {
      provider: "TMDB",
      notice: "This product uses the TMDB API but is not endorsed or certified by TMDB.",
      url: "https://www.themoviedb.org/",
    },
    ...overrides,
  };
}

describe("CatalogFilterBrowser discovery panel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(trendingResponse()), { status: 200 })));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("shows Trending by default while keeping Recent Searches available", async () => {
    render(<CatalogFilterBrowser titles={[title()]} />);

    expect(screen.getByRole("heading", { name: "Trending titles" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Recent searches" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/catalog highlights are shown instead/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Trending/ }));
    fireEvent.click(screen.getByRole("option", { name: /Recent Searches/ }));

    expect(screen.getByRole("heading", { name: "Recent searches" })).toBeInTheDocument();
  });

  it("restores Recent Searches as a bounded, progressive poster-card feed", async () => {
    const savedSearches = ["Signal", ...Array.from({ length: 9 }, (_, index) => `Saved search ${index + 1}`)];
    localStorage.setItem("aperture-recent-searches", JSON.stringify(savedSearches));
    const recentTitles = Array.from({ length: 25 }, (_, index) => title(index + 1, {
      title: `Signal Archive ${index + 1}`,
      slug: `signal-archive-${index + 1}`,
      href: `/movies/signal-archive-${index + 1}`,
      poster_url: index === 0 ? "https://image.tmdb.org/t/p/w500/recent.jpg" : null,
    }));
    render(<CatalogFilterBrowser titles={recentTitles} />);

    fireEvent.click(screen.getByRole("button", { name: /Trending/ }));
    fireEvent.click(screen.getByRole("option", { name: /Recent Searches/ }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Signal" })).toBeInTheDocument());
    const searchTerms = screen.getByLabelText("Recent search terms");
    expect(within(searchTerms).getAllByRole("button")).toHaveLength(9);
    expect(within(searchTerms).getByRole("button", { name: "Saved search 7" })).toBeInTheDocument();
    expect(within(searchTerms).queryByRole("button", { name: "Saved search 8" })).not.toBeInTheDocument();

    const list = screen.getByRole("list", { name: "Recent searches" });
    const initialCards = within(list).getAllByRole("listitem");
    expect(initialCards).toHaveLength(12);
    expect(within(initialCards[0]).getByRole("img", { name: "Signal Archive 1 poster" })).toBeInTheDocument();
    expect(within(initialCards[0]).getByText("A cartographer follows a light across an impossible ocean.")).toBeInTheDocument();
    expect(within(initialCards[0]).getByText(/1h 44m.*PG.*CA/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more Recent searches" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(24);

    fireEvent.click(within(searchTerms).getByRole("button", { name: "Signal" }));
    expect(screen.getByRole("searchbox", { name: "Search titles or descriptions" })).toHaveValue("Signal");

    fireEvent.click(within(searchTerms).getByRole("button", { name: "Clear history" }));
    expect(screen.queryByLabelText("Recent search terms")).not.toBeInTheDocument();
    expect(localStorage.getItem("aperture-recent-searches")).toBeNull();
  });

  it("renders Ongoing as poster/info cards and progressively reveals the feed", () => {
    const ongoingTitles = Array.from({ length: 25 }, (_, index) => title(index + 1, {
      id: `series-${index + 1}`,
      kind: "series",
      title: `Ongoing Signal ${index + 1}`,
      slug: `ongoing-signal-${index + 1}`,
      href: `/series/ongoing-signal-${index + 1}`,
      content_format: "tv",
      poster_url: index === 0 ? "https://image.tmdb.org/t/p/w500/ongoing.jpg" : null,
      duration_minutes: 24,
      is_ongoing: true,
      season_count: 2,
      episode_count: 20,
      genres: ["Animation", "Mystery"],
    }));
    const { container } = render(<CatalogFilterBrowser titles={ongoingTitles} />);

    fireEvent.click(screen.getByRole("button", { name: /Trending/ }));
    fireEvent.click(screen.getByRole("option", { name: /Ongoing/ }));

    expect(container.querySelector(".catalog-discovery-panel")).toHaveAttribute("data-view", "ongoing");
    const list = screen.getByRole("list", { name: "Currently airing" });
    const initialCards = within(list).getAllByRole("listitem");
    expect(initialCards).toHaveLength(12);
    expect(within(initialCards[0]).getByRole("img", { name: "Ongoing Signal 1 poster" })).toHaveAttribute("loading", "lazy");
    expect(within(initialCards[0]).getByText("A cartographer follows a light across an impossible ocean.")).toBeInTheDocument();
    expect(within(initialCards[0]).getByText(/20 episodes.*PG.*CA/)).toBeInTheDocument();
    expect(within(initialCards[0]).getByRole("link", { name: /Ongoing Signal 1/ })).toHaveAttribute("href", "/series/ongoing-signal-1");

    fireEvent.click(screen.getByRole("button", { name: "Load more ongoing titles" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(24);
  });

  it("renders and selects a Studio-managed series view", async () => {
    const movie = title(1, { title: "Feature Signal" });
    const series = title(2, {
      id: "series-2",
      kind: "series",
      title: "Night Signal",
      slug: "night-signal",
      content_format: "tv",
      duration_minutes: 24,
      is_ongoing: true,
      season_count: 2,
      episode_count: 24,
    });
    const entry: ExploreEntry = {
      id: "5a8ab95a-5f10-4da1-b8f7-1cc9e3a73a80",
      label: "Series Spotlight",
      description: "Episodic stories selected by Studio.",
      icon: "✦",
      position: 0,
      criteria: {
        content_type: "series",
        query: null,
        genre: null,
        studio: null,
        country_code: null,
        original_language_code: null,
        maturity_rating: null,
        release_period: "all",
        duration: "all",
        airing: "all",
      },
    };

    render(<CatalogFilterBrowser titles={[movie, series]} exploreEntries={[entry]} />);

    fireEvent.click(screen.getByRole("button", { name: /Trending/ }));
    fireEvent.click(screen.getByRole("option", { name: /Series Spotlight/ }));

    expect(screen.getByRole("heading", { name: "Series Spotlight" })).toBeInTheDocument();
    const managedList = screen.getByRole("list", { name: "Series Spotlight" });
    expect(within(managedList).getByRole("link", { name: /Night Signal/ })).toBeInTheDocument();
    expect(within(managedList).queryByRole("link", { name: /Feature Signal/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show these titles in the catalog" }));
    expect(screen.getByRole("button", { name: "Series", pressed: true })).toBeInTheDocument();
  });

  it("leads with ordered Studio cards and fills from criteria without duplicates", () => {
    const automatic = title(1, { title: "Automatic Discovery" });
    const pinned = title(2, {
      id: "series-2",
      kind: "series",
      title: "Pinned Premiere",
      slug: "pinned-premiere",
      content_format: "tv",
      poster_url: "https://image.tmdb.org/t/p/w500/pinned.jpg",
      duration_minutes: 24,
      is_ongoing: true,
      season_count: 2,
      episode_count: 24,
    });
    const entry: ExploreEntry = {
      id: "c93ace97-5776-40e0-8e53-5375f3277006",
      label: "Premiere Shelf",
      description: "Pinned first, then automatically filled.",
      icon: "✦",
      position: 0,
      criteria: {
        content_type: "all",
        release_period: "all",
        duration: "all",
        airing: "all",
      },
      cards: [{
        id: "b307f724-c037-4e2d-b0db-bc322bace29a",
        movie_id: null,
        series_id: pinned.id,
        position: 0,
        title: {
          ...pinned,
          original_title: null,
          href: "/series/pinned-premiere",
          source: "aperture",
          availability: "Available now",
        },
      }],
    };

    render(<CatalogFilterBrowser titles={[automatic, pinned]} exploreEntries={[entry]} />);
    fireEvent.click(screen.getByRole("button", { name: /Trending/ }));
    fireEvent.click(screen.getByRole("option", { name: /Premiere Shelf/ }));

    const cards = within(screen.getByRole("list", { name: "Premiere Shelf" })).getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByRole("link", { name: /Pinned Premiere/ })).toBeInTheDocument();
    expect(within(cards[0]).getByRole("img", { name: "Pinned Premiere poster" })).toBeInTheDocument();
    expect(within(cards[1]).getByRole("link", { name: /Automatic Discovery/ })).toBeInTheDocument();
  });

  it("gives every future Studio Explore view the progressive card feed", () => {
    const entry: ExploreEntry = {
      id: "90bcab06-3818-46c2-b07d-8e73c95e953a",
      label: "Future Shelf",
      description: "The complete reusable Explore package.",
      icon: "+",
      position: 0,
      criteria: {
        content_type: "all",
        release_period: "all",
        duration: "all",
        airing: "all",
      },
      cards: [],
    };

    render(<CatalogFilterBrowser
      titles={Array.from({ length: 25 }, (_, index) => title(index + 1))}
      exploreEntries={[entry]}
    />);
    fireEvent.click(screen.getByRole("button", { name: /Trending/ }));
    fireEvent.click(screen.getByRole("option", { name: /Future Shelf/ }));

    const list = screen.getByRole("list", { name: "Future Shelf" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(12);
    fireEvent.click(screen.getByRole("button", { name: "Load more Future Shelf" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(24);
  });

  it("renders readable poster cards with movie and series metadata", async () => {
    const movie = title(1, {
      href: "/titles/movie/amt-movie-1",
      poster_url: "https://image.tmdb.org/t/p/w500/lantern.jpg",
      vote_average: 8.4,
    });
    const series = title(2, {
      id: "series-2",
      kind: "series",
      title: "Night Signal",
      slug: "night-signal",
      href: "/titles/series/amt-series-2",
      content_format: "tv",
      duration_minutes: null,
      season_count: 2,
      episode_count: 24,
      genres: ["Animation", "Mystery"],
      poster_url: null,
      vote_average: 8.9,
    });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(trendingResponse({
      page_size: 2,
      total_results: 2,
      total_pages: 1,
      source: "aperture",
      status: "ready",
      items: [movie, series].map((item) => ({
        ...item,
        original_title: null,
        href: item.href as string,
        source: "aperture" as const,
        availability: "Explore this title",
      })),
    })), { status: 200 })));

    const { container } = render(<CatalogFilterBrowser titles={[title(90)]} />);
    await waitFor(() => expect(screen.getByText("Global · seven days")).toBeInTheDocument());

    const list = screen.getByRole("list", { name: "Trending titles" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByRole("img", { name: "The Lantern Sea 1 poster" })).toHaveAttribute("loading", "lazy");
    expect(within(list).getByRole("link", { name: /The Lantern Sea 1/ })).toHaveAttribute("href", "/titles/movie/amt-movie-1");
    expect(within(list).getByText("★ 8.4")).toBeInTheDocument();
    expect(within(list).getByText("24 episodes · PG · CA")).toBeInTheDocument();
    expect(container.querySelector(".trending-card-art.missing")).toHaveTextContent("N");
    expect(screen.getByRole("link", { name: "TMDB" })).toHaveAttribute("href", "https://www.themoviedb.org/");
  });

  it("progressively reveals a 100-plus fallback feed without a hard bottom", async () => {
    const titles = Array.from({ length: 125 }, (_, index) => title(index + 1));
    const { container } = render(<CatalogFilterBrowser titles={titles} />);
    await waitFor(() => expect(screen.getByText(/catalog highlights are shown instead/i)).toBeInTheDocument());

    const list = screen.getByRole("list", { name: "Trending titles" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(12);
    expect(container.querySelector(".trending-feed")).toHaveAttribute("data-fade", "true");

    for (let batch = 0; batch < 10; batch += 1) {
      fireEvent.click(screen.getByRole("button", { name: "Load more trending titles" }));
    }

    expect(within(list).getAllByRole("listitem")).toHaveLength(125);
    expect(container.querySelector(".trending-feed")).toHaveAttribute("data-fade", "false");
    expect(screen.queryByRole("button", { name: "Load more trending titles" })).not.toBeInTheDocument();
  });

  it("loads the next batch when the internal scroll sentinel intersects", async () => {
    let callback: IntersectionObserverCallback = () => undefined;
    let observedRoot: Element | Document | null = null;
    class ObserverMock {
      constructor(next: IntersectionObserverCallback, options?: IntersectionObserverInit) {
        callback = next;
        observedRoot = options?.root ?? null;
      }
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() { return []; }
      root = null;
      rootMargin = "";
      thresholds = [];
    }
    vi.stubGlobal("IntersectionObserver", ObserverMock);
    const { container } = render(<CatalogFilterBrowser titles={Array.from({ length: 30 }, (_, index) => title(index + 1))} />);
    await waitFor(() => expect(screen.getByText(/catalog highlights are shown instead/i)).toBeInTheDocument());
    expect(observedRoot).toBe(container.querySelector(".trending-feed-scroll"));

    await act(async () => {
      callback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
      await Promise.resolve();
    });

    expect(within(screen.getByRole("list", { name: "Trending titles" })).getAllByRole("listitem")).toHaveLength(24);
  });
});
