"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import isoCountries from "i18n-iso-countries";
import englishCountries from "i18n-iso-countries/langs/en.json";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import { rememberClientSearch } from "@/app/lib/client-state";

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
  audio_languages: string[];
  subtitle_languages: string[];
  href?: string;
  source?: "local" | "tmdb";
};

const ALL = "all";
const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

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

export function CatalogFilterBrowser({ titles }: { titles: FilterTitle[] }) {
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
  const [discoveryView, setDiscoveryView] = useState<"recent" | "trending" | "ongoing">("recent");
  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [resultPage, setResultPage] = useState(0);
  const [slideDirection, setSlideDirection] = useState<"forward" | "back">("forward");
  const [remoteResults, setRemoteResults] = useState<FilterTitle[] | null>(null);
  const [remoteQuery, setRemoteQuery] = useState("");
  const [searchingEverywhere, setSearchingEverywhere] = useState(false);
  const [remoteSearchFailed, setRemoteSearchFailed] = useState(false);

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
        const response = await fetch(`${apiOrigin}/catalog/search?q=${encodeURIComponent(clean)}&page_size=48`, { signal: controller.signal });
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
          <header><div><p className="eyebrow">Instant results</p><h2>Anime and movies</h2></div></header>
          {remoteSearchFailed ? <div className="filter-empty"><h3>Global search is unavailable</h3><p>Check the connection or open the complete Search page.</p><Link href={`/search?q=${encodeURIComponent(query)}`}>Open Search</Link></div> : searchingEverywhere ? <div className="instant-search-loading" role="status"><span/><strong>Searching Aperture and the global catalog…</strong></div> : filtered.length ? <><div className={`filter-title-grid results-swoosh ${slideDirection}`} key={`${activeResultPage}:${query}:${type}:${genre}:${countriesSelected.join(",")}`}>{visibleResults.map((item) => (
            <Link href={item.href ?? `/${item.kind === "movie" ? "movies" : "series"}/${item.slug}`} className="filter-title-card" key={`${item.kind}:${item.id}`}>
              <div className={`filter-title-art ${item.poster_url ? "" : "missing"}`}>{item.poster_url ? <ResponsivePoster src={item.poster_url} sizes="(max-width: 420px) 120px, (max-width: 760px) 145px, 155px" /> : <div className="filter-title-placeholder"><span>{item.title[0]}</span><small>Artwork coming soon</small></div>}<small>{item.content_format === "ova" ? "OVA" : item.kind}</small></div>
              <div className="filter-title-info">
                <h3>{item.title}</h3>{item.source === "tmdb" ? <span className="instant-global-badge">Global result</span> : null}
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
        <aside className="catalog-discovery-panel" aria-label="Catalog discovery">
          <div className="discovery-view-select">
            <span>Explore</span>
            <button type="button" className="discovery-menu-trigger" aria-haspopup="listbox" aria-expanded={discoveryOpen} onClick={() => setDiscoveryOpen((open) => !open)}>
              <span aria-hidden="true">{discoveryView === "recent" ? "↺" : discoveryView === "trending" ? "↗" : "●"}</span>
              {discoveryView === "recent" ? "Recent Searches" : discoveryView === "trending" ? "Trending" : "Ongoing"}
              <i aria-hidden="true">⌄</i>
            </button>
            {discoveryOpen ? <div className="discovery-menu" role="listbox" aria-label="Explore catalog">
              {([
                { value: "recent" as const, label: "Recent Searches", detail: "Return to searches you made", icon: "↺" },
                { value: "trending" as const, label: "Trending", detail: "See what is popular now", icon: "↗" },
                { value: "ongoing" as const, label: "Ongoing", detail: "Find currently airing series", icon: "●" },
              ]).map((option) => <button type="button" role="option" aria-selected={discoveryView === option.value} onClick={() => { setDiscoveryView(option.value); setDiscoveryOpen(false); }} key={option.value}>
                <span aria-hidden="true">{option.icon}</span><span><strong>{option.label}</strong><small>{option.detail}</small></span>{discoveryView === option.value ? <i aria-hidden="true">✓</i> : null}
              </button>)}
            </div> : null}
          </div>
          <div className="discovery-panel-content">
            {discoveryView === "recent" ? <>
              <header><p className="eyebrow">Your activity</p><h3>Recent searches</h3></header>
              {recentSearches.length ? <div className="recent-search-list">{recentSearches.map((search) => <button type="button" onClick={() => setQuery(search)} key={search}><span aria-hidden="true">↗</span>{search}</button>)}</div> : <p className="discovery-empty">Search for a title and press Enter. Your recent searches will appear here.</p>}
              {recentSearches.length ? <button type="button" className="clear-recent" onClick={() => { setRecentSearches([]); localStorage.removeItem("aperture-recent-searches"); }}>Clear history</button> : null}
            </> : null}
            {discoveryView === "trending" ? <>
              <header><p className="eyebrow">Popular now</p><h3>Trending titles</h3></header>
              <ol className="discovery-title-list">{titles.slice(0, 6).map((item, index) => <li key={`trending-${item.kind}-${item.id}`}><span>{String(index + 1).padStart(2, "0")}</span><Link href={`/${item.kind === "movie" ? "movies" : "series"}/${item.slug}`}><strong>{item.title}</strong><small>{item.kind === "series" ? `${item.episode_count} episodes` : item.release_date?.slice(0, 4) ?? "Coming soon"}</small></Link></li>)}</ol>
            </> : null}
            {discoveryView === "ongoing" ? <>
              <header><p className="eyebrow">New episodes</p><h3>Currently airing</h3></header>
              <button type="button" className="show-ongoing" onClick={() => setAiring("ongoing")}>Show all ongoing series</button>
              <div className="ongoing-title-list">{titles.filter((item) => item.kind === "series" && item.is_ongoing).slice(0, 6).map((item) => <Link href={`/series/${item.slug}`} key={`ongoing-${item.id}`}><strong>{item.title}</strong><span>{item.episode_count} episodes</span></Link>)}</div>
            </> : null}
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
