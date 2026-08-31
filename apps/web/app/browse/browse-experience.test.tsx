import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { BrowseExperience, buildBrowseSearchParams } from "@/app/browse/browse-experience";
import { BrowseSpecialistRail } from "@/app/browse/browse-specialist-rail";
import {
  EMPTY_BROWSE_FILTERS,
  type BrowseItem,
  type BrowseResponse,
  type BrowseSearchResponse,
  type BrowseSection,
  type BrowseSectionsResponse,
} from "@/app/browse/browse-types";

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a href={String(href)} {...props}>{children}</a> }));

function item(index: number, overrides: Partial<BrowseItem> = {}): BrowseItem {
  return {
    id: `title-${index}`, kind: index % 2 ? "movie" : "series", title: `Story ${index}`, original_title: null, slug: `story-${index}`,
    short_description: `A complete cinematic description for story ${index}.`, release_date: "2026-08-22", maturity_rating: "PG-13", poster_url: null,
    content_format: "feature", country_code: "CA", original_language_code: "en", studios: ["Aperture Pictures"], genres: ["Drama", "Adventure"],
    season_count: index % 2 ? 0 : 2, episode_count: index % 2 ? 0 : 16, duration_minutes: index % 2 ? 126 : null, is_ongoing: index % 2 ? null : true,
    href: index % 2 ? `/movies/story-${index}` : `/series/story-${index}`, source: "local", availability: "In the Aperture catalog", ...overrides,
  };
}

function browseResponse(overrides: Partial<BrowseResponse> = {}): BrowseResponse {
  return {
    query: null, page: 1, page_size: 32, total: 70, has_more: true, next_page: 2,
    sort: "newest", items: Array.from({ length: 32 }, (_, index) => item(index + 1)),
    facet_groups: [
      { key: "story", label: "Story & mood", icon: "sparkles", facets: [
        { key: "genre", label: "Genres", icon: "masks", selection: "multiple", options: [{ value: "science-fiction", label: "Science Fiction", count: 12 }] },
        { key: "theme", label: "Themes", icon: "sparkles", selection: "multiple", options: [{ value: "found-family", label: "Found family", count: 7 }] },
      ] },
      { key: "origin", label: "Time & origin", icon: "globe", facets: [
        { key: "language", label: "Languages", icon: "language", selection: "multiple", options: [{ value: "en", label: "English", count: 30 }] },
        { key: "country", label: "Countries", icon: "globe", selection: "multiple", options: [{ value: "CA", label: "Canada", count: 9 }] },
        { key: "studio", label: "Studios", icon: "building-2", selection: "multiple", options: Array.from({ length: 71 }, (_, index) => ({ value: `Studio ${index + 1}`, label: `Studio ${index + 1}`, count: 71 - index })) },
      ] },
    ],
    ...overrides,
  };
}

function section(index: number, count = 3): BrowseSection {
  return {
    id: `specialist-${index}`, slug: `specialist-${index}`, eyebrow: `Specialist cut ${index}`, title: `Collection ${index}`,
    description: `A sharply programmed cinematic collection number ${index}.`, media_type: "mixed", source: "tmdb", status: "ready",
    items: Array.from({ length: count }, (_, itemIndex) => item(index * 100 + itemIndex, { source: "tmdb", href: `/external/tmdb/movie/${index * 100 + itemIndex}` })),
  };
}

function sectionsResponse(overrides: Partial<BrowseSectionsResponse> = {}): BrowseSectionsResponse {
  return {
    page: 1, page_size: 6, total_sections: 100, has_more: true, next_page: 2, items_per_section: 18,
    sections: Array.from({ length: 6 }, (_, index) => section(index + 1)), partial: false,
    attribution: { provider: "TMDB", notice: "This product uses the TMDB API but is not endorsed or certified by TMDB.", url: "https://www.themoviedb.org/" },
    ...overrides,
  };
}

function searchResponse(overrides: Partial<BrowseSearchResponse> = {}): BrowseSearchResponse {
  return { query: "Ellen Ripley", page: 1, page_size: 32, total_titles: 1, total_entities: 1, has_more: false, titles: [item(90, { title: "Alien", source: "tmdb", href: "/external/tmdb/movie/348" })], entities: [{ id: "person-1", kind: "person", name: "Sigourney Weaver", slug: "sigourney-weaver", detail: "Actor", href: "/people/sigourney-weaver" }], ...overrides };
}

function renderBrowse(props: Partial<React.ComponentProps<typeof BrowseExperience>> = {}) {
  return render(<BrowseExperience initial={browseResponse()} initialSections={sectionsResponse()} {...props}/>);
}

describe("BrowseExperience", () => {
  afterEach(() => {
    vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.history.replaceState(null, "", "/");
  });

  it("serializes the focused browse contract with a fixed batch size of 32", () => {
    const params = buildBrowseSearchParams({ page: 3, query: "  Ellen Ripley  ", filters: { ...EMPTY_BROWSE_FILTERS, kind: "movie", genres: ["science-fiction", "animation"], countries: ["CA"], runtimeBands: ["long"], yearMin: "1990", yearMax: "2026", airing: "ongoing", sort: "title_asc" } });
    expect(params.get("page_size")).toBe("32"); expect(params.get("q")).toBe("Ellen Ripley"); expect(params.getAll("genre")).toEqual(["science-fiction", "animation"]); expect(params.get("release_year_from")).toBe("1990"); expect(params.get("runtime_band")).toBe("long");
  });

  it("opens as specialist shelves without the removed viewing-circle chooser", () => {
    renderBrowse();
    expect(screen.getByRole("heading", { level: 1, name: "A hundred ways into the movies." })).toBeInTheDocument();
    expect(screen.queryByText(/live from TMDB/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/one catalog/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/collections open/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2, name: /Collection/ })).toHaveLength(6);
    expect(screen.queryByLabelText("Choose a viewing taste")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pause automatic movement in Collection 1" })).toBeInTheDocument();
  });

  it("prewarms every poster before a horizontal shelf moves into view", async () => {
    let railCallback: IntersectionObserverCallback = () => undefined;
    class ObserverMock {
      constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
        if (options?.rootMargin === "180px 0px") railCallback = callback;
      }
      observe() {} unobserve() {} disconnect() {} takeRecords() { return []; }
      root = null; rootMargin = ""; thresholds = [];
    }
    vi.stubGlobal("IntersectionObserver", ObserverMock);
    const posterSection = {
      ...section(1, 18),
      title: "Lives Under Pressure",
      items: section(1, 18).items.map((entry, posterIndex) => ({
        ...entry,
        poster_url: `https://image.tmdb.org/t/p/w500/poster-${posterIndex}.jpg`,
      })),
    };
    const { container } = render(<BrowseSpecialistRail section={posterSection} index={0}/>);
    const posters = Array.from(container.querySelectorAll<HTMLImageElement>("img"));
    expect(posters).toHaveLength(18);
    expect(posters.every((poster) => poster.getAttribute("loading") === "lazy")).toBe(true);

    await act(async () => {
      railCallback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
      await Promise.resolve();
    });

    // jsdom exposes the authored attribute but does not reflect the mutable
    // HTMLImageElement.loading property back to it as browsers do.
    expect(posters.every((poster) => poster.loading === "eager")).toBe(true);
    expect(container.querySelector(".browse-specialist-rail__viewport")).toHaveAttribute("data-posters-warmed", "true");
  });

  it("loads six more sections at the vertical sentinel", async () => {
    let sectionCallback: IntersectionObserverCallback = () => undefined;
    class ObserverMock {
      constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) { if (options?.rootMargin === "900px 0px") sectionCallback = callback; }
      observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } root = null; rootMargin = ""; thresholds = [];
    }
    vi.stubGlobal("IntersectionObserver", ObserverMock);
    const next = sectionsResponse({ page: 2, next_page: 3, sections: Array.from({ length: 6 }, (_, index) => section(index + 7)) });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(next), { status: 200 }));
    renderBrowse();
    await act(async () => { sectionCallback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver); await Promise.resolve(); });
    await waitFor(() => expect(screen.getAllByRole("heading", { level: 2, name: /^Collection/ })).toHaveLength(12));
    const request = new URL(String(fetchMock.mock.calls[0][0]), "http://aperture.test");
    expect(request.pathname).toBe("/api/catalog/browse/sections"); expect(request.searchParams.get("page_size")).toBe("6"); expect(request.searchParams.get("items_per_section")).toBe("18");
  });

  it("pauses automatic pagination instead of burning through empty partial TMDB batches", async () => {
    let observerCount = 0;
    class ObserverMock {
      constructor() { observerCount += 1; }
      observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } root = null; rootMargin = ""; thresholds = [];
    }
    vi.stubGlobal("IntersectionObserver", ObserverMock);
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderBrowse({ initialSections: sectionsResponse({ sections: [], partial: true }) });

    expect(screen.queryByRole("heading", { level: 2, name: /Collection/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry the first six collections" })).toBeInTheDocument();
    expect(screen.getByText(/Automatic loading is paused/)).toBeInTheDocument();
    await act(async () => Promise.resolve());
    expect(observerCount).toBe(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("retries an incomplete section page before advancing the specialist index", async () => {
    let sectionCallback: IntersectionObserverCallback = () => undefined;
    class ObserverMock {
      constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) { if (options?.rootMargin === "900px 0px") sectionCallback = callback; }
      observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } root = null; rootMargin = ""; thresholds = [];
    }
    vi.stubGlobal("IntersectionObserver", ObserverMock);
    const unavailable = { ...section(12), status: "unavailable" as const, items: [] };
    const partial = sectionsResponse({ page: 2, next_page: 3, partial: true, sections: [...Array.from({ length: 5 }, (_, index) => section(index + 7)), unavailable] });
    const recovered = sectionsResponse({ page: 2, next_page: 3, sections: Array.from({ length: 6 }, (_, index) => section(index + 7)) });
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(partial), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(recovered), { status: 200 }));
    renderBrowse();

    await act(async () => { sectionCallback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver); await Promise.resolve(); });
    await waitFor(() => expect(screen.getAllByRole("heading", { level: 2, name: /^Collection/ })).toHaveLength(11));
    fireEvent.click(screen.getByRole("button", { name: "Retry collection batch 2" }));
    await waitFor(() => expect(screen.getAllByRole("heading", { level: 2, name: /^Collection/ })).toHaveLength(12));

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.map(([request]) => new URL(String(request), "http://aperture.test").searchParams.get("page"))).toEqual(["2", "2"]);
    expect(screen.getByRole("button", { name: "Reveal six more collections" })).toBeInTheDocument();
  });

  it("debounces unfiltered search through the same-origin universal TMDB route", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(searchResponse()), { status: 200 }));
    renderBrowse();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search titles, stories, or cast" }), { target: { value: "Ellen Ripley" } });
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => { vi.advanceTimersByTime(351); await Promise.resolve(); await Promise.resolve(); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = new URL(String(fetchMock.mock.calls[0][0]), "http://aperture.test");
    expect(request.pathname).toBe("/api/catalog/search"); expect(request.searchParams.get("q")).toBe("Ellen Ripley"); expect(request.searchParams.get("page_size")).toBe("32");
  });

  it("re-enables pagination when a new search supersedes an in-flight append", async () => {
    vi.useFakeTimers();
    const nextSearch = searchResponse({ query: "Dune", has_more: true, titles: [item(91, { title: "Dune", source: "tmdb", href: "/external/tmdb/movie/438631" })] });
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => new Promise<Response>(() => undefined))
      .mockResolvedValueOnce(new Response(JSON.stringify(nextSearch), { status: 200 }));
    renderBrowse({ initialSearch: searchResponse({ has_more: true }), initialParams: "q=Ellen+Ripley" });

    fireEvent.click(screen.getByRole("button", { name: "Load 32 more" }));
    expect(screen.getByRole("button", { name: /Opening the next reel/ })).toBeDisabled();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search titles, stories, or cast" }), { target: { value: "Dune" } });
    await act(async () => { vi.advanceTimersByTime(351); await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("link", { name: "View Dune" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load 32 more" })).toBeEnabled();
  });

  it("restores a universal-search URL without repeating its server request", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    render(<StrictMode><BrowseExperience initial={browseResponse()} initialSections={sectionsResponse()} initialSearch={searchResponse()} initialParams="q=Ellen+Ripley"/></StrictMode>);
    expect(screen.getByRole("searchbox", { name: "Search titles, stories, or cast" })).toHaveValue("Ellen Ripley");
    expect(screen.getByRole("link", { name: "View Alien" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Related people and subjects" })).toBeInTheDocument();
    await act(async () => Promise.resolve()); expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uses the licensed browse endpoint when an advanced filter is active", async () => {
    const filtered = browseResponse({ total: 12, has_more: false, items: [item(200)] });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(filtered), { status: 200 }));
    renderBrowse(); fireEvent.click(screen.getByRole("button", { name: "Advanced filters" })); fireEvent.click(screen.getByRole("button", { name: /Science Fiction/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("/api/catalog/browse?");
    expect(screen.getByText(/advanced filters refine playable titles/i)).toBeInTheDocument();
  });

  it("offers grouped filters and returns focus to the trigger", async () => {
    renderBrowse(); const trigger = screen.getByRole("button", { name: "Advanced filters" }); fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Advanced filters" })).toBeInTheDocument(); expect(screen.getByRole("heading", { name: "Story & mood" })).toBeInTheDocument(); expect(screen.getByRole("heading", { name: "Format & commitment" })).toBeInTheDocument(); expect(screen.getByRole("heading", { name: "Time & origin" })).toBeInTheDocument(); expect(screen.getByRole("heading", { name: "Audience" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Close advanced filters" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Close advanced filters" })); await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("keeps a large studio facet compact and searchable", () => {
    const { container } = renderBrowse(); fireEvent.click(screen.getByRole("button", { name: "Advanced filters" }));
    const studioFacet = container.querySelector(".browse-experience__searchable-facet"); expect(studioFacet?.querySelectorAll(".browse-experience__filter-choice")).toHaveLength(12); expect(screen.getByText("59 more studios available")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show all studios (71)" })); expect(studioFacet?.querySelectorAll(".browse-experience__filter-choice")).toHaveLength(71);
    const studioSearch = screen.getByRole("searchbox", { name: "Search studios" }); fireEvent.change(studioSearch, { target: { value: "Studio 64" } }); expect(screen.getByRole("button", { name: /Studio 64/ })).toBeInTheDocument(); expect(screen.queryByRole("button", { name: /Studio 63/ })).not.toBeInTheDocument();
  });

  it("keeps partial range input local instead of sending a failing request", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch"); renderBrowse(); fireEvent.click(screen.getByRole("button", { name: "Advanced filters" })); fireEvent.change(screen.getByRole("spinbutton", { name: "From year" }), { target: { value: "2" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("four-digit year"); await act(async () => Promise.resolve()); expect(fetchMock).not.toHaveBeenCalled(); expect(screen.getByRole("button", { name: /Show 70 titles/ })).toBeDisabled();
  });

  it("exposes keyboard and pointer controls on every horizontal shelf", () => {
    renderBrowse(); const shelf = screen.getByRole("region", { name: /Collection 1\. 3 titles/ }); expect(within(shelf).getAllByRole("link")).toHaveLength(3);
    expect(screen.getByRole("group", { name: "Collection 1 carousel controls" })).toBeInTheDocument();
    const pause = screen.getByRole("button", { name: "Pause automatic movement in Collection 1" }); fireEvent.click(pause); expect(screen.getByRole("button", { name: "Resume automatic movement in Collection 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous titles in Collection 1" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Next titles in Collection 1" })).toBeInTheDocument();
  });
});
