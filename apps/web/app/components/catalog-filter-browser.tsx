"use client";

import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import isoCountries from "i18n-iso-countries";
import englishCountries from "i18n-iso-countries/langs/en.json";
import type { TrendingTitlesResponse } from "@/app/browse/browse-types";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import { useSiteBrand } from "@/app/components/site-brand-provider";
import { rememberClientSearch } from "@/app/lib/client-state";
import type { ExploreCardTitle, ExploreCriteria, ExploreEntry } from "@/app/lib/explore";

isoCountries.registerLocale(englishCountries);

export type FilterTitle = {
  id: string;
  kind: "movie" | "series";
  title: string;
  slug: string;
  short_description: string;
  poster_url: string | null;
  release_date: string | null;
  maturity_rating: string | null;
  country_code: string | null;
  original_language_code: string | null;
  is_ongoing: boolean | null;
  content_format: string | null;
  studios: string[];
  genres: string[];
  duration_minutes: number | null;
  season_count: number;
  episode_count: number;
  audio_languages?: string[];
  subtitle_languages?: string[];
  href?: string;
  source?: "local" | "aperture" | "tmdb";
  availability?: string;
  vote_average?: number | null;
  vote_count?: number | null;
  popularity?: number | null;
};

const ALL = "all";
const TRENDING_REVEAL_SIZE = 12;
const BUILTIN_EXPLORE_OPTIONS = [
  { value: "recent", label: "Recent Searches", detail: "Return to searches you made", icon: "↺" },
  { value: "trending", label: "Trending", detail: "See what is popular now", icon: "↗" },
  { value: "ongoing", label: "Ongoing", detail: "Find currently airing series", icon: "●" },
] as const;

function mergeTrendingTitles(current: FilterTitle[], incoming: FilterTitle[]) {
  const seen = new Set(current.map((item) => `${item.kind}:${item.id}`));
  return [
    ...current,
    ...incoming.filter((item) => {
      const key = `${item.kind}:${item.id}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }),
  ];
}

function trendingRuntime(minutes: number | null) {
  if (!minutes) return null;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours}h ${remainder ? `${remainder}m` : ""}` : `${minutes}m`;
}

function trendingFacts(item: FilterTitle) {
  const format = item.kind === "series"
    ? item.episode_count > 0
      ? `${item.episode_count} ${item.episode_count === 1 ? "episode" : "episodes"}`
      : item.season_count > 0
        ? `${item.season_count} ${item.season_count === 1 ? "season" : "seasons"}`
        : item.is_ongoing
          ? "Ongoing"
          : null
    : trendingRuntime(item.duration_minutes);
  return [format, item.maturity_rating, item.country_code, item.original_language_code?.toUpperCase()]
    .filter((value): value is string => Boolean(value))
    .slice(0, 3);
}

function ExploreTitleCards({
  items,
  labelledBy,
}: {
  items: FilterTitle[];
  labelledBy: string;
}) {
  return <ol className="trending-card-list" aria-labelledby={labelledBy}>
    {items.map((item, index) => <li key={`explore-${item.kind}-${item.id}`}>
      <Link className="trending-card" href={item.href ?? `/${item.kind === "movie" ? "movies" : "series"}/${item.slug}`}>
        <div className={`trending-card-art ${item.poster_url ? "" : "missing"}`}>
          {item.poster_url ? <ResponsivePoster src={item.poster_url} sizes="72px" alt={`${item.title} poster`} /> : <span aria-hidden="true">{item.title.slice(0, 1)}</span>}
          <b aria-label={`Rank ${index + 1}`}>{String(index + 1).padStart(2, "0")}</b>
        </div>
        <div className="trending-card-copy">
          <div className="trending-card-kicker"><span>{item.kind === "series" ? "Series" : "Movie"}</span><span>{item.release_date?.slice(0, 4) ?? "Upcoming"}</span>{item.vote_average ? <span>★ {item.vote_average.toFixed(1)}</span> : null}</div>
          <strong>{item.title}</strong>
          <p>{item.short_description || "More details are coming soon."}</p>
          {item.genres.length ? <small className="trending-card-genres">{item.genres.slice(0, 2).join(" · ")}</small> : null}
          {trendingFacts(item).length ? <small className="trending-card-facts">{trendingFacts(item).join(" · ")}</small> : null}
        </div>
      </Link>
    </li>)}
  </ol>;
}

function titleMatchesExploreCriteria(item: FilterTitle, criteria: ExploreCriteria) {
  if (criteria.content_type === "movie" && item.kind !== "movie") return false;
  if (criteria.content_type === "series" && item.kind !== "series") return false;
  if (criteria.content_type === "ova" && item.content_format !== "ova") return false;
  const query = criteria.query?.toLocaleLowerCase();
  if (query && !`${item.title} ${item.short_description} ${item.genres.join(" ")} ${item.studios.join(" ")}`.toLocaleLowerCase().includes(query)) return false;
  if (criteria.genre && !item.genres.some((genre) => genre.toLocaleLowerCase() === criteria.genre?.toLocaleLowerCase())) return false;
  if (criteria.studio && !item.studios.some((studio) => studio.toLocaleLowerCase() === criteria.studio?.toLocaleLowerCase())) return false;
  if (criteria.country_code && item.country_code !== criteria.country_code) return false;
  if (criteria.original_language_code && item.original_language_code !== criteria.original_language_code) return false;
  if (criteria.maturity_rating && item.maturity_rating !== criteria.maturity_rating) return false;
  if (criteria.airing === "ongoing" && item.is_ongoing !== true) return false;
  if (criteria.airing === "finished" && (item.kind !== "series" || item.is_ongoing !== false)) return false;
  const year = item.release_date ? Number(item.release_date.slice(0, 4)) : null;
  if (criteria.release_period === "2020s" && (!year || year < 2020)) return false;
  if (criteria.release_period === "2010s" && (!year || year < 2010 || year > 2019)) return false;
  if (criteria.release_period === "classic" && (!year || year >= 2010)) return false;
  if (criteria.duration === "short" && (!item.duration_minutes || item.duration_minutes >= 30)) return false;
  if (criteria.duration === "standard" && (!item.duration_minutes || item.duration_minutes < 30 || item.duration_minutes > 90)) return false;
  if (criteria.duration === "long" && (!item.duration_minutes || item.duration_minutes <= 90)) return false;
  return true;
}

function exploreCardTitle(title: ExploreCardTitle): FilterTitle {
  return {
    id: title.id,
    kind: title.kind,
    title: title.title,
    slug: title.slug,
    short_description: title.short_description,
    poster_url: title.poster_url,
    release_date: title.release_date,
    maturity_rating: title.maturity_rating,
    country_code: title.country_code,
    original_language_code: title.original_language_code,
    is_ongoing: title.is_ongoing,
    content_format: title.content_format,
    studios: title.studios,
    genres: title.genres,
    duration_minutes: title.duration_minutes,
    season_count: title.season_count,
    episode_count: title.episode_count,
    audio_languages: [],
    subtitle_languages: [],
    href: title.href,
    source: title.source,
    availability: title.availability,
  };
}

function ExploreCollectionView({
  feedId,
  eyebrow,
  heading,
  description,
  items,
  actionLabel,
  onAction,
  headerExtras,
  loadMoreLabel,
  emptyHeading = "No matching titles yet.",
  emptyDescription = "This view will fill automatically as matching catalog titles become available.",
}: {
  feedId: string;
  eyebrow: string;
  heading: string;
  description: string;
  items: FilterTitle[];
  actionLabel?: string;
  onAction?: () => void;
  headerExtras?: ReactNode;
  loadMoreLabel?: string;
  emptyHeading?: string;
  emptyDescription?: string;
}) {
  const [visibleCount, setVisibleCount] = useState(() => Math.min(TRENDING_REVEAL_SIZE, items.length));
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const hasMore = visibleCount < items.length;
  const revealMore = useCallback(() => {
    setVisibleCount((current) => Math.min(current + TRENDING_REVEAL_SIZE, items.length));
  }, [items.length]);

  useEffect(() => {
    const root = scrollRef.current;
    const sentinel = sentinelRef.current;
    if (!root || !sentinel || !hasMore || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((items) => {
      if (items.some((item) => item.isIntersecting)) revealMore();
    }, { root, rootMargin: "0px 0px 240px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, revealMore]);

  const visibleItems = items.slice(0, visibleCount);
  return <div className="managed-explore-view" data-explore-card-feed="true">
    <header className="managed-explore-heading">
      <div><p className="eyebrow">{eyebrow}</p><h3 id={feedId}>{heading}</h3></div>
      <span>{visibleItems.length} / {items.length}</span>
      <p>{description}</p>
      {actionLabel && onAction ? <button type="button" onClick={onAction}>{actionLabel}</button> : null}
      {headerExtras ? <div className="explore-card-feed-extras">{headerExtras}</div> : null}
    </header>
    <div className="managed-explore-scroll" ref={scrollRef}>
      {visibleItems.length ? <ExploreTitleCards items={visibleItems} labelledBy={feedId} /> : <div className="trending-feed-empty"><strong>{emptyHeading}</strong><p>{emptyDescription}</p></div>}
      {hasMore ? <div className="trending-feed-sentinel" ref={sentinelRef} aria-hidden="true" /> : null}
      {hasMore ? <button className="trending-load-more" type="button" onClick={revealMore}>Load more {loadMoreLabel ?? heading}</button> : visibleItems.length ? <p className="trending-feed-end">You’ve reached the end of this view.</p> : null}
    </div>
  </div>;
}

function ConfiguredExploreView({
  entry,
  titles,
  onApply,
}: {
  entry: ExploreEntry;
  titles: FilterTitle[];
  onApply: () => void;
}) {
  const matches = useMemo(() => {
    const catalogTitles = new Map(titles.map((title) => [`${title.kind}:${title.id}`, title]));
    const seen = new Set<string>();
    const items: FilterTitle[] = [];
    for (const card of [...(entry.cards ?? [])].sort((left, right) => left.position - right.position)) {
      const hydrated = exploreCardTitle(card.title);
      const key = `${hydrated.kind}:${hydrated.id}`;
      if (seen.has(key)) continue;
      const catalogTitle = catalogTitles.get(key);
      items.push(catalogTitle ? {
        ...hydrated,
        ...catalogTitle,
        href: catalogTitle.href ?? hydrated.href,
        poster_url: catalogTitle.poster_url ?? hydrated.poster_url,
      } : hydrated);
      seen.add(key);
    }
    for (const title of titles) {
      const key = `${title.kind}:${title.id}`;
      if (!seen.has(key) && titleMatchesExploreCriteria(title, entry.criteria)) {
        items.push(title);
        seen.add(key);
      }
    }
    return items;
  }, [entry.cards, entry.criteria, titles]);
  return <ExploreCollectionView
    feedId={`managed-explore-${entry.id}`}
    eyebrow="Studio programmed"
    heading={entry.label}
    description={entry.description || "A custom view of the catalog."}
    items={matches}
    actionLabel="Show these titles in the catalog"
    onAction={onApply}
  />;
}

function OngoingExploreView({ titles, onApply }: { titles: FilterTitle[]; onApply: () => void }) {
  const ongoingTitles = useMemo(
    () => titles.filter((item) => item.kind === "series" && item.is_ongoing),
    [titles],
  );
  return <ExploreCollectionView
    feedId="ongoing-titles-heading"
    eyebrow="New episodes"
    heading="Currently airing"
    description="Series with new episodes and seasons available now."
    items={ongoingTitles}
    actionLabel="Show all ongoing series"
    onAction={onApply}
    loadMoreLabel="ongoing titles"
    emptyHeading="No ongoing series yet."
    emptyDescription="Poster cards will appear here as currently airing series become available."
  />;
}

function RecentExploreView({
  titles,
  searches,
  onSelect,
  onClear,
}: {
  titles: FilterTitle[];
  searches: string[];
  onSelect: (search: string) => void;
  onClear: () => void;
}) {
  const recentTitles = useMemo(() => {
    const seen = new Set<string>();
    const items: FilterTitle[] = [];
    for (const search of searches) {
      const normalized = search.toLocaleLowerCase();
      for (const title of titles) {
        const key = `${title.kind}:${title.id}`;
        const haystack = `${title.title} ${title.short_description} ${title.genres.join(" ")} ${title.studios.join(" ")}`.toLocaleLowerCase();
        if (!seen.has(key) && haystack.includes(normalized)) {
          items.push(title);
          seen.add(key);
        }
      }
    }
    return items;
  }, [searches, titles]);
  const extras = searches.length ? <div className="recent-search-chips" aria-label="Recent search terms">
    {searches.map((search) => <button type="button" onClick={() => onSelect(search)} key={search}>{search}</button>)}
    <button type="button" className="clear-recent" onClick={onClear}>Clear history</button>
  </div> : null;
  return <ExploreCollectionView
    key={searches.join("\u0000")}
    feedId="recent-search-titles-heading"
    eyebrow="Your activity"
    heading="Recent searches"
    description="Poster cards connected to searches stored in this browser."
    items={recentTitles}
    headerExtras={extras}
    emptyHeading={searches.length ? "No matching cards yet." : "No recent searches yet."}
    emptyDescription={searches.length ? "Try one of the saved search terms again as the catalog grows." : "Search for a title and press Enter. Matching cards will appear here."}
  />;
}

function TrendingTitleFeed({ fallbackTitles }: { fallbackTitles: FilterTitle[] }) {
  const brand = useSiteBrand();
  const [items, setItems] = useState<FilterTitle[]>(fallbackTitles);
  const [visibleCount, setVisibleCount] = useState(Math.min(TRENDING_REVEAL_SIZE, fallbackTitles.length));
  const [mode, setMode] = useState<"loading" | "provider" | "fallback">("loading");
  const [nextPage, setNextPage] = useState<number | null>(null);
  const [remoteHasMore, setRemoteHasMore] = useState(false);
  const [totalResults, setTotalResults] = useState(fallbackTitles.length);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("Connecting to the weekly global pulse.");
  const [announcement, setAnnouncement] = useState("");
  const [attribution, setAttribution] = useState<TrendingTitlesResponse["attribution"] | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<AbortController | null>(null);
  const loadingRef = useRef(false);

  const requestPage = useCallback(async (page: number, replace: boolean) => {
    if (loadingRef.current) return;
    const controller = new AbortController();
    requestRef.current?.abort();
    requestRef.current = controller;
    loadingRef.current = true;
    setLoading(true);
    try {
      const response = await fetch(`/api/catalog/trending?page=${page}`, { signal: controller.signal });
      if (!response.ok) throw new Error("The weekly pulse could not be reached.");
      const payload = await response.json() as TrendingTitlesResponse;
      if (payload.status !== "ready") throw new Error("The weekly pulse is temporarily unavailable.");
      if (controller.signal.aborted) return;
      const unique = mergeTrendingTitles([], payload.items);
      if (replace && !unique.length && !payload.has_more) {
        throw new Error("The weekly pulse has no available artwork yet.");
      }
      setItems((current) => replace ? unique : mergeTrendingTitles(current, unique));
      setVisibleCount((current) => replace ? Math.min(TRENDING_REVEAL_SIZE, unique.length) : current);
      setMode("provider");
      setNextPage(payload.next_page);
      setRemoteHasMore(payload.has_more);
      setTotalResults(payload.total_results);
      setAttribution(payload.attribution);
      setNotice("Worldwide movie and series momentum from the past seven days.");
      setAnnouncement(`${unique.length} ${replace ? "trending titles loaded" : "more trending titles added"}.`);
    } catch (error) {
      if (controller.signal.aborted) return;
      if (replace) {
        setMode("fallback");
        setRemoteHasMore(false);
        setNextPage(null);
        setNotice("Live weekly trends are unavailable, so catalog highlights are shown instead.");
      } else {
        setNotice(error instanceof Error ? error.message : "More weekly trends could not be loaded.");
      }
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        loadingRef.current = false;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void requestPage(1, true), 0);
    return () => {
      window.clearTimeout(timer);
      requestRef.current?.abort();
    };
  }, [requestPage]);

  const hasBufferedTitles = visibleCount < items.length;
  const hasMore = hasBufferedTitles || (mode === "provider" && remoteHasMore && nextPage !== null);
  const loadMore = useCallback(() => {
    if (hasBufferedTitles) {
      const next = Math.min(visibleCount + TRENDING_REVEAL_SIZE, items.length);
      setVisibleCount(next);
      setAnnouncement(`${next} trending titles are now visible.`);
      return;
    }
    if (mode === "provider" && remoteHasMore && nextPage !== null) {
      void requestPage(nextPage, false);
    }
  }, [hasBufferedTitles, items.length, mode, nextPage, remoteHasMore, requestPage, visibleCount]);

  useEffect(() => {
    const root = scrollRef.current;
    const sentinel = sentinelRef.current;
    if (!root || !sentinel || !hasMore || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadMore();
    }, { root, rootMargin: "0px 0px 280px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  const visibleItems = items.slice(0, visibleCount);
  return <div className="trending-feed" data-fade={hasMore ? "true" : "false"}>
    <header className="trending-feed-heading">
      <div><p className="eyebrow">{mode === "provider" ? "Global · seven days" : `${brand.short_name} catalog`}</p><h3 id="trending-titles-heading">Trending titles</h3></div>
      <span>{visibleItems.length} / {(mode === "provider" ? totalResults : items.length).toLocaleString()}</span>
      <p>{notice} {mode === "provider" && attribution ? <a href={attribution.url} title={attribution.notice} target="_blank" rel="noreferrer">TMDB</a> : null}</p>
    </header>
    <div className="trending-feed-scroll" ref={scrollRef}>
      {visibleItems.length ? <ExploreTitleCards items={visibleItems} labelledBy="trending-titles-heading" /> : <div className="trending-feed-empty"><strong>The weekly chart is warming up.</strong><p>Movie and series cards will appear as soon as artwork is available.</p></div>}
      {hasMore ? <div className="trending-feed-sentinel" ref={sentinelRef} aria-hidden="true" /> : null}
      {hasMore ? <button className="trending-load-more" type="button" onClick={loadMore} disabled={loading}>{loading ? "Loading more titles…" : "Load more trending titles"}</button> : visibleItems.length ? <p className="trending-feed-end">You’ve reached the end of this pulse.</p> : null}
    </div>
    <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
  </div>;
}

function countryName(code: string) {
  return isoCountries.getName(code, "en", { select: "official" }) ?? code;
}

const ALL_COUNTRIES = Object.keys(isoCountries.getNames("en", { select: "official" }))
  .sort((left, right) => countryName(left).localeCompare(countryName(right)));

function CountryMultiSelect({
  countries,
  value,
  onChange,
}: {
  countries: string[];
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const [search, setSearch] = useState("");
  const selected = new Set(value);
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const visibleCountries = countries.filter((country) =>
    `${countryName(country)} ${country}`.toLocaleLowerCase().includes(normalizedSearch),
  );
  const summary = value.length === 0
    ? "All countries"
    : value.length === 1
      ? countryName(value[0])
      : `${value.length} countries selected`;

  const toggle = (country: string) => {
    onChange(selected.has(country) ? value.filter((item) => item !== country) : [...value, country]);
  };

  return (
    <fieldset className="filter-option-field country-multi-field">
      <legend>Country</legend>
      <details className="country-multi-select">
        <summary>{summary}</summary>
        <div className="country-multi-menu">
          <div className="country-multi-header">
            <strong>Select countries</strong>
            <span>{value.length ? `${value.length} selected` : `${countries.length} available`}</span>
          </div>
          <label className="country-multi-search">
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by country or code…"
              aria-label="Search countries"
            />
            {search ? <button type="button" onClick={() => setSearch("")} aria-label="Clear country search">×</button> : null}
          </label>
          {value.length ? <div className="country-selected-list" aria-label="Selected countries">
            {value.map((country) => <button type="button" onClick={() => toggle(country)} key={country}>
              {countryName(country)} <span aria-hidden="true">×</span>
            </button>)}
          </div> : null}
          <div className="country-multi-actions">
            <span>{visibleCountries.length} {visibleCountries.length === 1 ? "match" : "matches"}</span>
            <button type="button" onClick={() => onChange([])} disabled={value.length === 0}>Clear selection</button>
          </div>
          <div className="country-multi-options">
            {visibleCountries.map((country) => (
              <label key={country}>
                <input
                  type="checkbox"
                  checked={selected.has(country)}
                  onChange={() => toggle(country)}
                />
                <span>{countryName(country)}</span>
                <small>{country}</small>
              </label>
            ))}
            {!visibleCountries.length ? <p className="country-multi-empty">No countries match “{search}”.</p> : null}
          </div>
        </div>
      </details>
    </fieldset>
  );
}

function FilterOptions({
  label,
  value,
  options,
  onChange,
  scrollable = false,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
  scrollable?: boolean;
}) {
  return (
    <fieldset className="filter-option-field">
      <legend>{label}</legend>
      <div className={`filter-option-list ${scrollable ? "scrollable" : ""}`}>
        {options.map((option) => (
          <button
            type="button"
            className={value === option.value ? "active" : ""}
            aria-pressed={value === option.value}
            onClick={() => onChange(option.value)}
            key={option.value}
          >
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function SearchableSingleSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  const [search, setSearch] = useState("");
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const visibleOptions = options.filter((option) => option.toLocaleLowerCase().includes(normalizedSearch));
  return <fieldset className="filter-option-field compact-select-field">
    <legend>{label}</legend>
    <details className="compact-select">
      <summary>{value === ALL ? `All ${label.toLocaleLowerCase()}s` : value}</summary>
      <div className="compact-select-menu">
        <label><span aria-hidden="true">⌕</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${label.toLocaleLowerCase()}s…`} aria-label={`Search ${label.toLocaleLowerCase()}s`} /></label>
        <div className="compact-select-options">
          <button type="button" className={value === ALL ? "active" : ""} onClick={() => onChange(ALL)}>All {label.toLocaleLowerCase()}s</button>
          {visibleOptions.map((option) => <button type="button" className={value === option ? "active" : ""} onClick={() => onChange(option)} key={option}>{option}</button>)}
          {!visibleOptions.length ? <p>No matches found.</p> : null}
        </div>
      </div>
    </details>
  </fieldset>;
}

export function CatalogFilterBrowser({
  titles,
  exploreEntries = [],
}: {
  titles: FilterTitle[];
  exploreEntries?: ExploreEntry[];
}) {
  const brand = useSiteBrand();
  const [type, setType] = useState(ALL);
  const [countriesSelected, setCountriesSelected] = useState<string[]>([]);
  const [duration, setDuration] = useState(ALL);
  const [studio, setStudio] = useState(ALL);
  const [genre, setGenre] = useState(ALL);
  const [releasePeriod, setReleasePeriod] = useState(ALL);
  const [rating, setRating] = useState(ALL);
  const [language, setLanguage] = useState(ALL);
  const [airing, setAiring] = useState(ALL);
  const [query, setQuery] = useState("");
  const [moreOpen, setMoreOpen] = useState(false);
  const [discoveryView, setDiscoveryView] = useState<string>("trending");
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [resultPage, setResultPage] = useState(0);
  const [slideDirection, setSlideDirection] = useState<"forward" | "back">("forward");
  const [remoteResults, setRemoteResults] = useState<FilterTitle[] | null>(null);
  const [remoteQuery, setRemoteQuery] = useState("");
  const [searchingEverywhere, setSearchingEverywhere] = useState(false);
  const [remoteSearchFailed, setRemoteSearchFailed] = useState(false);
  const discoveryPanelRef = useRef<HTMLElement>(null);
  const discoveryFrameRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const panel = discoveryPanelRef.current;
    const frame = discoveryFrameRef.current;
    if (!panel || !frame) return;

    let animationFrame = 0;
    const updateFrameHeight = () => {
      animationFrame = 0;
      if (window.innerWidth <= 900) {
        frame.style.removeProperty("--catalog-discovery-frame-height");
        return;
      }
      const viewportHeight = Math.max(0, window.innerHeight - 108);
      const containedHeight = Math.max(0, panel.getBoundingClientRect().bottom - 93);
      frame.style.setProperty(
        "--catalog-discovery-frame-height",
        `${Math.min(viewportHeight, containedHeight)}px`,
      );
    };
    const scheduleFrameUpdate = () => {
      if (!animationFrame) animationFrame = window.requestAnimationFrame(updateFrameHeight);
    };

    updateFrameHeight();
    window.addEventListener("scroll", scheduleFrameUpdate, { passive: true });
    window.addEventListener("resize", scheduleFrameUpdate);
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(scheduleFrameUpdate);
    resizeObserver?.observe(panel);
    return () => {
      window.removeEventListener("scroll", scheduleFrameUpdate);
      window.removeEventListener("resize", scheduleFrameUpdate);
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      resizeObserver?.disconnect();
      frame.style.removeProperty("--catalog-discovery-frame-height");
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        setRecentSearches(JSON.parse(localStorage.getItem("aperture-recent-searches") ?? "[]").filter((item: unknown) => typeof item === "string").slice(0, 8));
      } catch {
        setRecentSearches([]);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const clean = query.trim();
    if (clean.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearchingEverywhere(true);
      setRemoteSearchFailed(false);
      try {
        const response = await fetch(`/api/catalog/search?q=${encodeURIComponent(clean)}&page_size=48`, { signal: controller.signal });
        if (!response.ok) throw new Error("search unavailable");
        const payload = await response.json();
        setRemoteResults(payload.titles.map((item: Record<string, unknown>) => ({
          id: String(item.id), kind: item.kind as "movie" | "series", title: String(item.title), slug: String(item.slug),
          short_description: String(item.short_description ?? ""), poster_url: item.poster_url as string | null,
          release_date: item.release_date as string | null, maturity_rating: item.maturity_rating as string | null,
          country_code: item.country_code as string | null, content_format: item.content_format as string | null,
          original_language_code: item.original_language_code as string | null, is_ongoing: null,
          studios: item.studios as string[] ?? [], genres: item.genres as string[] ?? [], duration_minutes: null,
          season_count: Number(item.season_count ?? 0), episode_count: Number(item.episode_count ?? 0),
          audio_languages: [], subtitle_languages: [], href: String(item.href), source: item.source as "local" | "tmdb",
        })));
        setRemoteQuery(clean);
        setResultPage(0);
      } catch (error) {
        if ((error as Error).name !== "AbortError") { setRemoteSearchFailed(true); setRemoteResults([]); }
      } finally {
        if (!controller.signal.aborted) setSearchingEverywhere(false);
      }
    }, 320);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  const rememberSearch = (search: string) => {
    const clean = search.trim();
    if (!clean) return;
    rememberClientSearch(clean);
    setRecentSearches((current) => {
      const next = [clean, ...current.filter((item) => item.toLocaleLowerCase() !== clean.toLocaleLowerCase())].slice(0, 8);
      localStorage.setItem("aperture-recent-searches", JSON.stringify(next));
      return next;
    });
  };

  const activeRemoteResults = remoteQuery === query.trim() ? remoteResults : null;
  const searchableTitles = activeRemoteResults ?? titles;
  const studios = useMemo(() => [...new Set(searchableTitles.flatMap((item) => item.studios))].sort((a, b) => a.localeCompare(b)), [searchableTitles]);
  const genres = useMemo(() => [...new Set(searchableTitles.flatMap((item) => item.genres))].sort((a, b) => a.localeCompare(b)), [searchableTitles]);
  const ratings = useMemo(() => [...new Set(searchableTitles.map((item) => item.maturity_rating).filter(Boolean) as string[])].sort(), [searchableTitles]);
  const languages = useMemo(() => [...new Set(searchableTitles.map((item) => item.original_language_code).filter(Boolean) as string[])].sort(), [searchableTitles]);
  const filtered = useMemo(() => searchableTitles.filter((item) => {
    if (activeRemoteResults === null && query.trim() && !`${item.title} ${item.short_description}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())) return false;
    if (type !== ALL && item.content_format !== type) return false;
    if (countriesSelected.length && (!item.country_code || !countriesSelected.includes(item.country_code))) return false;
    if (studio !== ALL && !item.studios.includes(studio)) return false;
    if (genre !== ALL && !item.genres.includes(genre)) return false;
    if (rating !== ALL && item.maturity_rating !== rating) return false;
    if (language !== ALL && item.original_language_code !== language) return false;
    if (airing === "ongoing" && item.is_ongoing !== true) return false;
    if (airing === "finished" && (item.kind !== "series" || item.is_ongoing !== false)) return false;
    const year = item.release_date ? Number(item.release_date.slice(0, 4)) : null;
    if (releasePeriod === "2020s" && (!year || year < 2020)) return false;
    if (releasePeriod === "2010s" && (!year || year < 2010 || year > 2019)) return false;
    if (releasePeriod === "classic" && (!year || year >= 2010)) return false;
    if (duration === "short" && (!item.duration_minutes || item.duration_minutes >= 30)) return false;
    if (duration === "standard" && (!item.duration_minutes || item.duration_minutes < 30 || item.duration_minutes > 90)) return false;
    if (duration === "long" && (!item.duration_minutes || item.duration_minutes <= 90)) return false;
    return true;
  }), [searchableTitles, activeRemoteResults, query, type, countriesSelected, studio, genre, duration, rating, language, airing, releasePeriod]);
  const resultPageCount = Math.max(1, Math.ceil(filtered.length / 9));
  const activeResultPage = Math.min(resultPage, resultPageCount - 1);
  const visibleResults = filtered.slice(activeResultPage * 9, activeResultPage * 9 + 9);

  const reset = () => {
    setType(ALL); setCountriesSelected([]); setDuration(ALL); setStudio(ALL); setGenre(ALL);
    setReleasePeriod(ALL); setRating(ALL); setLanguage(ALL); setAiring(ALL); setQuery("");
    setResultPage(0); setSlideDirection("back");
  };

  const activeFilters = [
    type !== ALL ? { key: "type", label: type === "tv" ? "Series" : type.toUpperCase(), clear: () => setType(ALL) } : null,
    ...countriesSelected.map((item) => ({ key: `country-${item}`, label: countryName(item), clear: () => setCountriesSelected((current) => current.filter((country) => country !== item)) })),
    genre !== ALL ? { key: "genre", label: genre, clear: () => setGenre(ALL) } : null,
    studio !== ALL ? { key: "studio", label: studio, clear: () => setStudio(ALL) } : null,
    duration !== ALL ? { key: "duration", label: duration === "short" ? "Under 30m" : duration === "standard" ? "30–90m" : "Over 90m", clear: () => setDuration(ALL) } : null,
    releasePeriod !== ALL ? { key: "release", label: releasePeriod === "classic" ? "Before 2010" : releasePeriod, clear: () => setReleasePeriod(ALL) } : null,
    rating !== ALL ? { key: "rating", label: rating, clear: () => setRating(ALL) } : null,
    language !== ALL ? { key: "language", label: language.toUpperCase(), clear: () => setLanguage(ALL) } : null,
    airing !== ALL ? { key: "airing", label: airing === "finished" ? "Completed" : "Ongoing", clear: () => setAiring(ALL) } : null,
  ].filter((item): item is { key: string; label: string; clear: () => void } => item !== null);
  const managedExploreEntry = exploreEntries.find((entry) => `managed:${entry.id}` === discoveryView);
  const resolvedDiscoveryView = BUILTIN_EXPLORE_OPTIONS.some((option) => option.value === discoveryView) || managedExploreEntry
    ? discoveryView
    : "trending";
  const discoveryOptions = [
    ...BUILTIN_EXPLORE_OPTIONS,
    ...exploreEntries.map((entry) => ({
      value: `managed:${entry.id}`,
      label: entry.label,
      detail: entry.description || "Studio-programmed catalog filter",
      icon: entry.icon,
    })),
  ];
  const activeDiscoveryOption = discoveryOptions.find((option) => option.value === resolvedDiscoveryView)
    ?? BUILTIN_EXPLORE_OPTIONS[1];

  const applyExploreEntry = (entry: ExploreEntry) => {
    const criteria = entry.criteria;
    setType(criteria.content_type === "series" ? "tv" : criteria.content_type);
    setCountriesSelected(criteria.country_code ? [criteria.country_code] : []);
    setDuration(criteria.duration);
    setStudio(criteria.studio ?? ALL);
    setGenre(criteria.genre ?? ALL);
    setReleasePeriod(criteria.release_period);
    setRating(criteria.maturity_rating ?? ALL);
    setLanguage(criteria.original_language_code ?? ALL);
    setAiring(criteria.airing);
    setQuery(criteria.query ?? "");
    setResultPage(0);
    setSlideDirection("back");
  };

  return (
    <section className="catalog-browser" aria-labelledby="browse-title">
      <header className="catalog-browser-heading">
        <div><p className="eyebrow">Browse your way</p><h2 id="browse-title">Filter catalog</h2></div>
        <span aria-live="polite">{searchingEverywhere ? "Searching everywhere…" : `${filtered.length} ${filtered.length === 1 ? "title" : "titles"}`}</span>
      </header>
      <div className="catalog-control-bar" aria-label="Catalog filters">
        <label className="catalog-main-search"><span aria-hidden="true">⌕</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") rememberSearch(event.currentTarget.value); }} placeholder="Search titles or descriptions…" aria-label="Search titles or descriptions" /></label>
        <FilterOptions label="Type" value={type} onChange={setType} options={[{ value: ALL, label: "All" }, { value: "movie", label: "Movies" }, { value: "tv", label: "Series" }, { value: "ova", label: "OVA" }]} />
        <SearchableSingleSelect label="Genre" value={genre} options={genres} onChange={setGenre} />
        <CountryMultiSelect countries={ALL_COUNTRIES} value={countriesSelected} onChange={setCountriesSelected} />
        <button type="button" className="more-filter-button" onClick={() => setMoreOpen(true)}>More filters{activeFilters.filter((item) => !["type", "genre"].includes(item.key) && !item.key.startsWith("country-")).length ? <span>{activeFilters.filter((item) => !["type", "genre"].includes(item.key) && !item.key.startsWith("country-")).length}</span> : null}</button>
      </div>
      {activeFilters.length ? <div className="active-filter-row" aria-label="Active filters">
        <span>Active</span>{activeFilters.map((item) => <button type="button" onClick={item.clear} key={item.key}>{item.label} <span aria-hidden="true">×</span></button>)}
        <button type="button" className="clear-all-filters" onClick={reset}>Clear all</button>
      </div> : null}
      <div className="catalog-browser-body simplified">
        <div className="catalog-filter-results">
          <header><div><h2>Anime and movies</h2></div></header>
          {remoteSearchFailed ? <div className="filter-empty"><h3>Global search is unavailable</h3><p>Check the connection or open the complete Search page.</p><Link href={`/search?q=${encodeURIComponent(query)}`}>Open Search</Link></div> : searchingEverywhere ? <div className="instant-search-loading" role="status"><span/><strong>Searching {brand.short_name} and the global catalog…</strong></div> : filtered.length ? <><div className={`filter-title-grid results-swoosh ${slideDirection}`} key={`${activeResultPage}:${query}:${type}:${genre}:${countriesSelected.join(",")}`}>{visibleResults.map((item) => (
            <Link href={item.href ?? `/${item.kind === "movie" ? "movies" : "series"}/${item.slug}`} className="filter-title-card" key={`${item.kind}:${item.id}`}>
              <div className={`filter-title-art ${item.poster_url ? "" : "missing"}`}>{item.poster_url ? <ResponsivePoster src={item.poster_url} sizes="(max-width: 420px) 120px, (max-width: 760px) 145px, 155px" /> : <div className="filter-title-placeholder"><span>{item.title[0]}</span><small>Artwork coming soon</small></div>}<small>{item.content_format === "ova" ? "OVA" : item.kind}</small></div>
              <div className="filter-title-info">
                <h3>{item.title}</h3>
                <div className="filter-title-meta">
                  <span>{item.release_date?.slice(0, 4) ?? "TBA"}</span>
                  {item.maturity_rating ? <span>{item.maturity_rating}</span> : null}
                  {item.country_code ? <span>{item.country_code}</span> : null}
                  {item.duration_minutes ? <span>{item.duration_minutes} min</span> : null}
                </div>
                <p className="filter-title-genres">{item.genres.slice(0, 3).join(" · ") || "Genre pending"}</p>
                {item.kind === "series" ? <div className="filter-title-facts">
                  <span><strong>{item.season_count}</strong> {item.season_count === 1 ? "Season" : "Seasons"}</span>
                  <span><strong>{item.episode_count}</strong> {item.episode_count === 1 ? "Episode" : "Episodes"}</span>
                </div> : null}
                {item.audio_languages?.length || item.subtitle_languages?.length ? <div className="filter-title-tracks">
                  {item.audio_languages?.length ? <span><strong>Dub</strong> {item.audio_languages.map((code) => code.toUpperCase()).join(", ")}</span> : null}
                  {item.subtitle_languages?.length ? <span><strong>Sub</strong> {item.subtitle_languages.map((code) => code.toUpperCase()).join(", ")}</span> : null}
                </div> : null}
                {item.kind === "series" && item.is_ongoing !== null ? <p className={`filter-title-status ${item.is_ongoing ? "ongoing" : "complete"}`}><span aria-hidden="true" />{item.is_ongoing ? "Currently airing" : "Completed series"}</p> : null}
                {item.original_language_code ? <p className="filter-title-language"><span>Original language</span>{item.original_language_code.toUpperCase()}</p> : null}
                {item.studios?.length ? <p className="filter-title-studio"><span>Studio</span> {item.studios.slice(0, 2).join(" · ")}</p> : null}
              </div>
            </Link>
          ))}</div><div className="catalog-results-pagination carousel-pagination">
            <button type="button" className="result-arrow previous" disabled={activeResultPage === 0} onClick={() => { setSlideDirection("back"); setResultPage(Math.max(0, activeResultPage - 1)); }} aria-label="Show previous titles">←</button>
            <div className="result-page-status"><strong>Page {activeResultPage + 1}</strong><span>{activeResultPage * 9 + 1}–{Math.min((activeResultPage + 1) * 9, filtered.length)} of {filtered.length} titles</span></div>
            <div className="result-page-dots" aria-hidden="true">{Array.from({ length: Math.min(resultPageCount, 7) }, (_, index) => <span className={index === Math.min(activeResultPage, 6) ? "active" : ""} key={index} />)}</div>
            <button type="button" className="result-arrow next" disabled={activeResultPage >= resultPageCount - 1} onClick={() => { setSlideDirection("forward"); setResultPage(Math.min(resultPageCount - 1, activeResultPage + 1)); }} aria-label="Show next titles">→</button>
          </div></> : <div className="filter-empty"><h3>No exact matches</h3><p>Try widening one of the filters.</p><button type="button" onClick={reset}>Show everything</button></div>}
        </div>
        <aside className="catalog-discovery-panel" aria-label="Catalog discovery" data-view={resolvedDiscoveryView} ref={discoveryPanelRef}>
          <div className="catalog-discovery-frame" ref={discoveryFrameRef}>
            <div className="discovery-view-select">
              <span>Explore</span>
              <button type="button" className="discovery-menu-trigger" aria-haspopup="listbox" aria-expanded={discoveryOpen} onClick={() => setDiscoveryOpen((open) => !open)}>
                <span aria-hidden="true">{activeDiscoveryOption.icon}</span>
                {activeDiscoveryOption.label}
                <i aria-hidden="true">⌄</i>
              </button>
              {discoveryOpen ? <div className="discovery-menu" role="listbox" aria-label="Explore catalog">
                {discoveryOptions.map((option) => <button type="button" role="option" aria-selected={resolvedDiscoveryView === option.value} onClick={() => { setDiscoveryView(option.value); setDiscoveryOpen(false); }} key={option.value}>
                  <span aria-hidden="true">{option.icon}</span><span><strong>{option.label}</strong><small>{option.detail}</small></span>{resolvedDiscoveryView === option.value ? <i aria-hidden="true">✓</i> : null}
                </button>)}
              </div> : null}
            </div>
            <div className={`discovery-panel-content ${resolvedDiscoveryView === "trending" ? "is-trending" : resolvedDiscoveryView === "recent" || resolvedDiscoveryView === "ongoing" || managedExploreEntry ? "is-managed" : ""}`}>
              {resolvedDiscoveryView === "recent" ? <RecentExploreView
                titles={titles}
                searches={recentSearches}
                onSelect={setQuery}
                onClear={() => { setRecentSearches([]); localStorage.removeItem("aperture-recent-searches"); }}
              /> : null}
              {resolvedDiscoveryView === "trending" ? <TrendingTitleFeed fallbackTitles={titles} /> : null}
              {resolvedDiscoveryView === "ongoing" ? <OngoingExploreView titles={titles} onApply={() => setAiring("ongoing")} /> : null}
              {managedExploreEntry ? <ConfiguredExploreView key={managedExploreEntry.id} entry={managedExploreEntry} titles={titles} onApply={() => applyExploreEntry(managedExploreEntry)} /> : null}
            </div>
          </div>
        </aside>
      </div>
      {moreOpen ? <div className="filter-drawer-layer" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setMoreOpen(false); }}>
        <aside className="filter-drawer" role="dialog" aria-modal="true" aria-labelledby="more-filter-title">
          <header><div><p className="eyebrow">Refine results</p><h2 id="more-filter-title">More filters</h2></div><button type="button" onClick={() => setMoreOpen(false)} aria-label="Close more filters">×</button></header>
          <div className="filter-drawer-content">
            <SearchableSingleSelect label="Studio" value={studio} options={studios} onChange={setStudio} />
            <FilterOptions label="Duration" value={duration} onChange={setDuration} options={[{ value: ALL, label: "Any" }, { value: "short", label: "Under 30m" }, { value: "standard", label: "30–90m" }, { value: "long", label: "Over 90m" }]} />
            <FilterOptions label="Release" value={releasePeriod} onChange={setReleasePeriod} options={[{ value: ALL, label: "Any year" }, { value: "2020s", label: "2020s" }, { value: "2010s", label: "2010s" }, { value: "classic", label: "Before 2010" }]} />
            <FilterOptions label="Rating" value={rating} onChange={setRating} options={[{ value: ALL, label: "Any rating" }, ...ratings.map((item) => ({ value: item, label: item }))]} />
            <FilterOptions label="Language" value={language} onChange={setLanguage} options={[{ value: ALL, label: "Any language" }, ...languages.map((item) => ({ value: item, label: item.toUpperCase() }))]} />
            <FilterOptions label="Status" value={airing} onChange={setAiring} options={[{ value: ALL, label: "Any status" }, { value: "ongoing", label: "Ongoing" }, { value: "finished", label: "Completed" }]} />
          </div>
          <footer><button type="button" onClick={reset}>Clear all</button><button type="button" className="primary" onClick={() => setMoreOpen(false)}>Show {filtered.length} {filtered.length === 1 ? "title" : "titles"}</button></footer>
        </aside>
      </div> : null}
    </section>
  );
}
