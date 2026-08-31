"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { BrowseSpecialistRail } from "@/app/browse/browse-specialist-rail";
import { CatalogCard } from "@/app/components/catalog-card";
import { useSiteBrand } from "@/app/components/site-brand-provider";
import {
  EMPTY_BROWSE_FILTERS,
  type BrowseFacetGroup,
  type BrowseFacetOption,
  type BrowseFilters,
  type BrowseItem,
  type BrowseResponse,
  type BrowseSearchResponse,
  type BrowseSection,
  type BrowseSectionsResponse,
} from "@/app/browse/browse-types";

const RESULT_PAGE_SIZE = 32;
const SECTION_PAGE_SIZE = 6;
const ITEMS_PER_SECTION = 18;

type IconName = "search" | "sliders" | "sparkles" | "film" | "clock" | "globe" | "shield" | "close" | "compass" | "arrow";

export function BrowseIcon({ name }: { name: IconName }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return <svg className="browse-experience__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    {name === "search" ? <><circle {...common} cx="10.8" cy="10.8" r="6.4"/><path {...common} d="m16 16 4.2 4.2"/></> : null}
    {name === "sliders" ? <><path {...common} d="M4 6h7M15 6h5M4 12h2M10 12h10M4 18h10M18 18h2"/><circle {...common} cx="13" cy="6" r="2"/><circle {...common} cx="8" cy="12" r="2"/><circle {...common} cx="16" cy="18" r="2"/></> : null}
    {name === "sparkles" ? <><path {...common} d="m12 2 1.4 4.1L17.5 7.5l-4.1 1.4L12 13l-1.4-4.1-4.1-1.4 4.1-1.4L12 2Z"/><path {...common} d="m18.5 13 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z"/><path {...common} d="m5.5 14 .8 2.2 2.2.8-2.2.8L5.5 20l-.8-2.2-2.2-.8 2.2-.8.8-2.2Z"/></> : null}
    {name === "film" ? <><rect {...common} x="3" y="5" width="18" height="14" rx="2"/><path {...common} d="M7 5v14M17 5v14M3 9h4M17 9h4M3 15h4M17 15h4"/></> : null}
    {name === "clock" ? <><circle {...common} cx="12" cy="12" r="8.5"/><path {...common} d="M12 7.5V12l3.2 2"/></> : null}
    {name === "globe" ? <><circle {...common} cx="12" cy="12" r="9"/><path {...common} d="M3 12h18M12 3c2.2 2.5 3.3 5.5 3.3 9S14.2 18.5 12 21c-2.2-2.5-3.3-5.5-3.3-9S9.8 5.5 12 3Z"/></> : null}
    {name === "shield" ? <path {...common} d="M12 2.8 19 5v5.8c0 4.5-2.7 8.1-7 10.4-4.3-2.3-7-5.9-7-10.4V5l7-2.2Z"/> : null}
    {name === "close" ? <path {...common} d="m6 6 12 12M18 6 6 18"/> : null}
    {name === "compass" ? <><circle {...common} cx="12" cy="12" r="9"/><path {...common} d="m15.8 8.2-2.1 5.5-5.5 2.1 2.1-5.5 5.5-2.1Z"/></> : null}
    {name === "arrow" ? <path {...common} d="M5 12h14m-5-5 5 5-5 5"/> : null}
  </svg>;
}

function appendMany(params: URLSearchParams, key: string, values: readonly string[]) {
  values.forEach((value) => params.append(key, value));
}

function initialBrowseState(serialized: string) {
  const params = new URLSearchParams(serialized);
  const sort = params.get("sort");
  const kind = params.get("kind");
  const airing = params.get("airing");
  const filters: BrowseFilters = {
    ...EMPTY_BROWSE_FILTERS,
    kind: kind === "movie" || kind === "series" ? kind : "",
    genres: params.getAll("genre"), themes: params.getAll("theme"), tags: params.getAll("tag"),
    languages: params.getAll("language"), countries: params.getAll("country"), contentFormats: params.getAll("content_format"),
    maturityRatings: params.getAll("maturity_rating"), studios: params.getAll("studio"), releaseDecades: params.getAll("release_decade"),
    runtimeBands: params.getAll("runtime_band"), yearMin: params.get("release_year_from") ?? "", yearMax: params.get("release_year_to") ?? "",
    runtimeMin: params.get("runtime_minutes_min") ?? "", runtimeMax: params.get("runtime_minutes_max") ?? "",
    airing: airing === "ongoing" || airing === "completed" ? airing : "",
    sort: sort === "oldest" || sort === "title_asc" || sort === "title_desc" ? sort : "newest",
  };
  return { query: params.get("q") ?? "", filters };
}

function countAdvancedFilters(filters: BrowseFilters) {
  return filters.genres.length + filters.themes.length + filters.tags.length + filters.languages.length + filters.countries.length
    + filters.contentFormats.length + filters.maturityRatings.length + filters.studios.length + filters.releaseDecades.length + filters.runtimeBands.length
    + Number(Boolean(filters.kind)) + Number(Boolean(filters.yearMin)) + Number(Boolean(filters.yearMax)) + Number(Boolean(filters.runtimeMin))
    + Number(Boolean(filters.runtimeMax)) + Number(Boolean(filters.airing)) + Number(filters.sort !== "newest");
}

function validateBrowseRanges(filters: BrowseFilters) {
  const integerInRange = (value: string, minimum: number, maximum: number) => !value || (Number.isInteger(Number(value)) && Number(value) >= minimum && Number(value) <= maximum);
  let yearError = "";
  let runtimeError = "";
  if (!integerInRange(filters.yearMin, 1888, 2100) || !integerInRange(filters.yearMax, 1888, 2100)) yearError = "Use a four-digit year from 1888 through 2100.";
  else if (filters.yearMin && filters.yearMax && Number(filters.yearMin) > Number(filters.yearMax)) yearError = "The starting year must come before the ending year.";
  if (!integerInRange(filters.runtimeMin, 1, 600) || !integerInRange(filters.runtimeMax, 1, 600)) runtimeError = "Use a runtime from 1 through 600 minutes.";
  else if (filters.runtimeMin && filters.runtimeMax && Number(filters.runtimeMin) > Number(filters.runtimeMax)) runtimeError = "The minimum runtime must not exceed the maximum.";
  return { valid: !yearError && !runtimeError, yearError, runtimeError };
}

export function buildBrowseSearchParams({ page, query, filters }: { page: number; query: string; filters: BrowseFilters }) {
  const params = new URLSearchParams({ page: String(page), page_size: String(RESULT_PAGE_SIZE) });
  if (query.trim()) params.set("q", query.trim());
  if (filters.kind) params.set("kind", filters.kind);
  appendMany(params, "genre", filters.genres); appendMany(params, "theme", filters.themes); appendMany(params, "tag", filters.tags);
  appendMany(params, "language", filters.languages); appendMany(params, "country", filters.countries); appendMany(params, "content_format", filters.contentFormats);
  appendMany(params, "maturity_rating", filters.maturityRatings); appendMany(params, "studio", filters.studios); appendMany(params, "release_decade", filters.releaseDecades);
  appendMany(params, "runtime_band", filters.runtimeBands);
  if (filters.yearMin) params.set("release_year_from", filters.yearMin);
  if (filters.yearMax) params.set("release_year_to", filters.yearMax);
  if (filters.runtimeMin) params.set("runtime_minutes_min", filters.runtimeMin);
  if (filters.runtimeMax) params.set("runtime_minutes_max", filters.runtimeMax);
  if (filters.airing) params.set("airing", filters.airing);
  params.set("sort", filters.sort);
  return params;
}

function FilterChoices({ label, values, selected, onToggle }: { label: string; values: BrowseFacetOption[]; selected: string[]; onToggle: (value: string) => void }) {
  if (!values.length) return null;
  return <fieldset className="browse-experience__filter-set"><legend>{label}</legend><div className="browse-experience__filter-choices">
    {values.map(({ value, label: optionLabel, count }) => <button className={selected.includes(value) ? "browse-experience__filter-choice browse-experience__filter-choice--active" : "browse-experience__filter-choice"} type="button" aria-pressed={selected.includes(value)} onClick={() => onToggle(value)} key={value}><span>{optionLabel}</span><small>{count}</small></button>)}
  </div></fieldset>;
}

function SearchableFilterChoices({ label, values, selected, onToggle, initialLimit = 12 }: { label: string; values: BrowseFacetOption[]; selected: string[]; onToggle: (value: string) => void; initialLimit?: number }) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(false);
  if (!values.length) return null;
  const selectedSet = new Set(selected);
  const ordered = [...values].sort((left, right) => Number(selectedSet.has(right.value)) - Number(selectedSet.has(left.value)));
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const matches = normalizedSearch ? ordered.filter((option) => option.label.toLocaleLowerCase().includes(normalizedSearch)) : ordered;
  const visible = normalizedSearch || expanded ? matches : matches.slice(0, initialLimit);
  const hiddenCount = Math.max(0, matches.length - visible.length);
  return <fieldset className="browse-experience__filter-set browse-experience__searchable-facet"><legend>{label}</legend>
    <label className="browse-experience__facet-search"><BrowseIcon name="search"/><span>Search {label.toLocaleLowerCase()}</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${values.length} ${label.toLocaleLowerCase()}…`}/>{search ? <button type="button" onClick={() => setSearch("")} aria-label={`Clear ${label.toLocaleLowerCase()} search`}><BrowseIcon name="close"/></button> : null}</label>
    <div className="browse-experience__filter-choices">{visible.map(({ value, label: optionLabel, count }) => <button className={selectedSet.has(value) ? "browse-experience__filter-choice browse-experience__filter-choice--active" : "browse-experience__filter-choice"} type="button" aria-pressed={selectedSet.has(value)} onClick={() => onToggle(value)} key={value}><span>{optionLabel}</span><small>{count}</small></button>)}</div>
    {normalizedSearch && !visible.length ? <p className="browse-experience__facet-summary" role="status">No studios match “{search.trim()}”.</p> : null}
    {!normalizedSearch && values.length > initialLimit ? <button className="browse-experience__facet-toggle" type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>{expanded ? "Show fewer studios" : `Show all studios (${values.length})`}</button> : null}
    {!normalizedSearch && hiddenCount > 0 ? <small className="browse-experience__facet-summary">{hiddenCount} more studios available</small> : null}
  </fieldset>;
}

function releaseYear(date: string | null) { return date?.slice(0, 4) || "Coming soon"; }
function runtimeLabel(minutes: number | null) { if (!minutes) return null; const hours = Math.floor(minutes / 60); const remainder = minutes % 60; return hours ? `${hours}h ${remainder}m` : `${minutes}m`; }
function cardFacts(item: BrowseItem) {
  const facts = item.kind === "movie" ? [runtimeLabel(item.duration_minutes), item.maturity_rating] : [item.season_count ? `${item.season_count} ${item.season_count === 1 ? "season" : "seasons"}` : null, item.is_ongoing === true ? "Ongoing" : item.maturity_rating];
  return facts.filter(Boolean).join(" · ");
}
function mergeUniqueItems(current: BrowseItem[], incoming: BrowseItem[]) { const seen = new Set(current.map((item) => `${item.kind}:${item.id}`)); return [...current, ...incoming.filter((item) => !seen.has(`${item.kind}:${item.id}`))]; }
function mergeUniqueSections(current: BrowseSection[], incoming: BrowseSection[]) { const seen = new Set(current.map((section) => section.id)); return [...current, ...incoming.filter((section) => !seen.has(section.id))]; }

export function BrowseExperience({ initial, initialSections, initialSearch = null, initialParams = "" }: { initial: BrowseResponse; initialSections: BrowseSectionsResponse; initialSearch?: BrowseSearchResponse | null; initialParams?: string }) {
  const brand = useSiteBrand();
  const restored = useMemo(() => initialBrowseState(initialParams), [initialParams]);
  const restoredAdvancedCount = useMemo(() => countAdvancedFilters(restored.filters), [restored.filters]);
  const startsWithUniversalSearch = Boolean(restored.query.trim() && !restoredAdvancedCount && initialSearch);
  const [query, setQuery] = useState(restored.query);
  const [debouncedQuery, setDebouncedQuery] = useState(restored.query);
  const [filters, setFilters] = useState<BrowseFilters>(restored.filters);
  const [items, setItems] = useState(startsWithUniversalSearch ? initialSearch?.titles ?? [] : initial.items);
  const [entities, setEntities] = useState(startsWithUniversalSearch ? initialSearch?.entities ?? [] : []);
  const [facetGroups, setFacetGroups] = useState(initial.facet_groups);
  const [page, setPage] = useState(startsWithUniversalSearch ? initialSearch?.page ?? 1 : initial.page);
  const [total, setTotal] = useState(startsWithUniversalSearch ? initialSearch?.total_titles ?? 0 : initial.total);
  const [hasMore, setHasMore] = useState(startsWithUniversalSearch ? initialSearch?.has_more ?? false : initial.has_more);
  const [sections, setSections] = useState(initialSections.sections.filter((section) => section.items.length));
  const [sectionPage, setSectionPage] = useState(initialSections.page);
  const [sectionHasMore, setSectionHasMore] = useState(initialSections.has_more);
  const [sectionRetryPage, setSectionRetryPage] = useState<number | null>(initialSections.partial && (!initialSections.sections.length || initialSections.sections.some((section) => !section.items.length)) ? initialSections.page : null);
  const [sectionsPartial, setSectionsPartial] = useState(initialSections.partial);
  const [filterOpen, setFilterOpen] = useState(false);
  const [loading, setLoading] = useState(false); const [loadingMore, setLoadingMore] = useState(false); const [loadingSections, setLoadingSections] = useState(false);
  const [error, setError] = useState<string | null>(null); const [sectionError, setSectionError] = useState<string | null>(null); const [announcement, setAnnouncement] = useState(""); const [retryNonce, setRetryNonce] = useState(0);
  const resultSentinelRef = useRef<HTMLDivElement>(null); const sectionSentinelRef = useRef<HTMLDivElement>(null); const filterTriggerRef = useRef<HTMLButtonElement>(null); const closeButtonRef = useRef<HTMLButtonElement>(null); const dialogRef = useRef<HTMLDivElement>(null);
  const requestSequence = useRef(0); const sectionRequestSequence = useRef(0); const refreshController = useRef<AbortController | null>(null); const appendController = useRef<AbortController | null>(null); const sectionController = useRef<AbortController | null>(null);
  const advancedCount = useMemo(() => countAdvancedFilters(filters), [filters]);
  const rangeValidation = useMemo(() => validateBrowseRanges(filters), [filters]);
  const focused = Boolean(debouncedQuery.trim() || advancedCount);
  const universalSearch = Boolean(debouncedQuery.trim() && !advancedCount);

  useEffect(() => { const timer = window.setTimeout(() => setDebouncedQuery(query), 350); return () => window.clearTimeout(timer); }, [query]);
  const queryKey = useMemo(() => buildBrowseSearchParams({ page: 1, query: debouncedQuery, filters }).toString(), [debouncedQuery, filters]);
  const lastRefreshKey = useRef(`${startsWithUniversalSearch ? "search" : "browse"}:${queryKey}:0`);

  useEffect(() => {
    if (!rangeValidation.valid) return;
    const visibleParams = new URLSearchParams(queryKey); visibleParams.delete("page"); visibleParams.delete("page_size"); if (visibleParams.get("sort") === "newest") visibleParams.delete("sort");
    window.history.replaceState(null, "", `${window.location.pathname}${visibleParams.size ? `?${visibleParams}` : ""}`);
  }, [queryKey, rangeValidation.valid]);

  useEffect(() => {
    if (!focused || !rangeValidation.valid) { refreshController.current?.abort(); appendController.current?.abort(); return; }
    const requestKind = universalSearch ? "search" : "browse"; const refreshKey = `${requestKind}:${queryKey}:${retryNonce}`; if (lastRefreshKey.current === refreshKey) return; lastRefreshKey.current = refreshKey;
    refreshController.current?.abort(); appendController.current?.abort(); const controller = new AbortController(); refreshController.current = controller; const sequence = ++requestSequence.current;
    setLoading(true); setError(null);
    const request = universalSearch ? `/api/catalog/search?q=${encodeURIComponent(debouncedQuery.trim())}&page=1&page_size=${RESULT_PAGE_SIZE}` : `/api/catalog/browse?${queryKey}`;
    void fetch(request, { signal: controller.signal }).then(async (response) => { if (!response.ok) throw new Error(`Browse request failed with status ${response.status}`); return response.json() as Promise<BrowseResponse | BrowseSearchResponse>; }).then((data) => {
      if (sequence !== requestSequence.current) return;
      if ("titles" in data) { setItems(data.titles); setEntities(data.entities); setPage(data.page); setTotal(data.total_titles); setHasMore(data.has_more); setAnnouncement(`${data.titles.length} titles found.`); }
      else { setItems(data.items); setEntities([]); setFacetGroups(data.facet_groups); setPage(data.page); setTotal(data.total); setHasMore(data.has_more); setAnnouncement(`${data.items.length} filtered titles now on screen.`); }
    }).catch((reason: unknown) => { if (controller.signal.aborted || sequence !== requestSequence.current) return; setError(reason instanceof Error ? reason.message : "The catalog could not be reached."); }).finally(() => { if (sequence === requestSequence.current) { setLoading(false); setLoadingMore(false); } });
    return () => controller.abort();
  }, [debouncedQuery, focused, queryKey, rangeValidation.valid, retryNonce, universalSearch]);

  useEffect(() => () => { refreshController.current?.abort(); appendController.current?.abort(); sectionController.current?.abort(); }, []);
  useEffect(() => {
    if (!filterOpen) return; const trigger = filterTriggerRef.current; document.documentElement.classList.add("browse-filter-open"); closeButtonRef.current?.focus();
    const onKeyDown = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") { setFilterOpen(false); return; } if (event.key !== "Tab") return; const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled), [href]") ?? []); if (!focusable.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } };
    window.addEventListener("keydown", onKeyDown); return () => { window.removeEventListener("keydown", onKeyDown); document.documentElement.classList.remove("browse-filter-open"); trigger?.focus(); };
  }, [filterOpen]);

  const loadMoreResults = useCallback(() => {
    if (!focused || !hasMore || loading || loadingMore || !rangeValidation.valid) return;
    appendController.current?.abort(); const controller = new AbortController(); appendController.current = controller; const sequence = ++requestSequence.current;
    const browseParams = buildBrowseSearchParams({ page: page + 1, query: debouncedQuery, filters }); browseParams.set("include_facets", "false");
    const request = universalSearch ? `/api/catalog/search?q=${encodeURIComponent(debouncedQuery.trim())}&page=${page + 1}&page_size=${RESULT_PAGE_SIZE}` : `/api/catalog/browse?${browseParams}`;
    setLoadingMore(true); setError(null);
    void fetch(request, { signal: controller.signal }).then(async (response) => { if (!response.ok) throw new Error(`Browse request failed with status ${response.status}`); return response.json() as Promise<BrowseResponse | BrowseSearchResponse>; }).then((data) => {
      if (sequence !== requestSequence.current) return;
      if ("titles" in data) { setItems((current) => mergeUniqueItems(current, data.titles)); setEntities((current) => current.length ? current : data.entities); setPage(data.page); setTotal(data.total_titles); setHasMore(data.has_more); setAnnouncement(`${data.titles.length} more titles entered the room.`); }
      else { setItems((current) => mergeUniqueItems(current, data.items)); if (data.facet_groups.length) setFacetGroups(data.facet_groups); setPage(data.page); setTotal(data.total); setHasMore(data.has_more); setAnnouncement(`${data.items.length} more filtered titles entered the room.`); }
    }).catch((reason: unknown) => { if (controller.signal.aborted || sequence !== requestSequence.current) return; setError(reason instanceof Error ? reason.message : "More titles could not be loaded."); }).finally(() => { if (appendController.current === controller) setLoadingMore(false); });
  }, [debouncedQuery, filters, focused, hasMore, loading, loadingMore, page, rangeValidation.valid, universalSearch]);

  const loadMoreSections = useCallback(() => {
    if (focused || (!sectionHasMore && sectionRetryPage === null) || loadingSections) return;
    const retryCurrentBatch = sectionRetryPage !== null;
    sectionController.current?.abort(); const controller = new AbortController(); sectionController.current = controller; const sequence = ++sectionRequestSequence.current; setLoadingSections(true); setSectionError(null); const nextPage = sectionRetryPage ?? sectionPage + 1;
    void fetch(`/api/catalog/browse/sections?page=${nextPage}&page_size=${SECTION_PAGE_SIZE}&items_per_section=${ITEMS_PER_SECTION}`, { signal: controller.signal }).then(async (response) => { if (!response.ok) throw new Error(`Collection request failed with status ${response.status}`); return response.json() as Promise<BrowseSectionsResponse>; }).then((data) => {
      if (sequence !== sectionRequestSequence.current) return; const readySections = data.sections.filter((section) => section.items.length); const hasMissingSections = readySections.length < data.sections.length; setSections((current) => mergeUniqueSections(current, readySections)); setSectionRetryPage(hasMissingSections ? data.page : null); if (!hasMissingSections) setSectionPage(data.page); setSectionHasMore(hasMissingSections || data.has_more); setSectionsPartial((current) => retryCurrentBatch ? data.partial : current || data.partial); setAnnouncement(hasMissingSections ? `${readySections.length} collections opened; the incomplete batch is waiting to be retried.` : `${readySections.length} more specialist collections opened.`);
    }).catch((reason: unknown) => { if (controller.signal.aborted || sequence !== sectionRequestSequence.current) return; setSectionError(reason instanceof Error ? reason.message : "More collections could not be loaded."); }).finally(() => { if (sequence === sectionRequestSequence.current) setLoadingSections(false); });
  }, [focused, loadingSections, sectionHasMore, sectionPage, sectionRetryPage]);

  useEffect(() => {
    const sentinel = focused ? resultSentinelRef.current : sectionSentinelRef.current; const canLoad = focused ? hasMore : sectionHasMore && sectionRetryPage === null; const load = focused ? loadMoreResults : loadMoreSections;
    if (!sentinel || !canLoad || typeof IntersectionObserver === "undefined") return; const observer = new IntersectionObserver((entries) => { if (entries.some((entry) => entry.isIntersecting)) load(); }, { rootMargin: "900px 0px" }); observer.observe(sentinel); return () => observer.disconnect();
  }, [focused, hasMore, loadMoreResults, loadMoreSections, sectionHasMore, sectionRetryPage]);

  const toggleArray = <K extends "genres" | "themes" | "tags" | "languages" | "countries" | "contentFormats" | "maturityRatings" | "studios" | "releaseDecades" | "runtimeBands">(key: K, value: string) => { setFilters((current) => ({ ...current, [key]: current[key].includes(value) ? current[key].filter((item) => item !== value) : [...current[key], value] })); };
  const facets = useMemo(() => { const byKey = new Map<string, BrowseFacetOption[]>(); facetGroups.forEach((group: BrowseFacetGroup) => group.facets.forEach((facet) => byKey.set(facet.key, facet.options))); return (key: string) => byKey.get(key) ?? []; }, [facetGroups]);
  const onSearchSubmit = (event: FormEvent) => { event.preventDefault(); setDebouncedQuery(query); };
  const resetDiscovery = () => { setQuery(""); setDebouncedQuery(""); setFilters(EMPTY_BROWSE_FILTERS); setEntities([]); };

  return <main className="browse-experience">
    <section className="browse-experience__hero browse-experience__hero--library" aria-labelledby="browse-heading">
      <div className="browse-experience__hero-copy"><div><h1 id="browse-heading">A hundred ways into the movies.</h1><p>From impossible worlds to razor-edged thrillers, each shelf follows a precise cinematic instinct through a vast movie and series universe. Keep moving—the program changes beneath you.</p></div></div>
    </section>
    <section className="browse-experience__discovery" aria-label="Search and filter the catalog">
      <form className="browse-experience__search" role="search" onSubmit={onSearchSubmit}><BrowseIcon name="search"/><label htmlFor="browse-search">Search titles, stories, or cast</label><input id="browse-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try Interstellar, Sigourney Weaver, or Studio Ghibli…" autoComplete="off"/>{query ? <button className="browse-experience__search-clear" type="button" onClick={() => setQuery("")} aria-label="Clear search"><BrowseIcon name="close"/></button> : null}</form>
      <button ref={filterTriggerRef} className="browse-experience__filter-trigger" type="button" onClick={() => setFilterOpen(true)} aria-haspopup="dialog" aria-label={`Advanced filters${advancedCount ? `, ${advancedCount} active` : ""}`}><BrowseIcon name="sliders"/><span>Advanced filters</span>{advancedCount ? <b aria-hidden="true">{advancedCount}</b> : null}</button>
    </section>

    {!focused ? <section className="browse-experience__collections" aria-labelledby="browse-collections-heading" aria-busy={loadingSections}>
      <header className="browse-experience__collection-intro"><div><p className="browse-experience__eyebrow">The specialist index</p><h2 id="browse-collections-heading">Every shelf has a point of view.</h2></div></header>
      <div className="browse-experience__section-stack">{sections.map((section, index) => <BrowseSpecialistRail section={section} index={index} key={section.id}/>)}</div>
      <div className="browse-experience__sentinel" ref={sectionSentinelRef} aria-hidden="true"/>
      {sectionError ? <div className="browse-experience__error browse-experience__error--compact" role="alert"><strong>The next shelves missed their cue.</strong><p>{sectionError}</p><button type="button" onClick={loadMoreSections}>Try again</button></div> : null}
      {sectionHasMore || sectionRetryPage !== null ? <div className="browse-experience__more"><button type="button" onClick={loadMoreSections} disabled={loadingSections}>{loadingSections ? "Programming the next six…" : sectionRetryPage !== null ? sectionRetryPage === 1 && !sections.length ? "Retry the first six collections" : `Retry collection batch ${sectionRetryPage}` : "Reveal six more collections"}<BrowseIcon name="arrow"/></button>{sectionRetryPage !== null ? <small>Automatic loading is paused until every shelf in this batch is ready.</small> : null}</div> : sections.length === initialSections.total_sections ? <p className="browse-experience__end">The final shelf is open.</p> : <div className="browse-experience__error browse-experience__error--compact" role="status"><strong>{sections.length ? "The open shelves remain available." : "The specialist index is waiting."}</strong><p>The remaining collections are temporarily unavailable, so they have not been represented as empty shelves.</p><button type="button" onClick={() => window.location.reload()}>Retry unavailable collections</button></div>}
      {sectionsPartial ? <p className="browse-experience__partial">A few shelves may be temporarily unavailable while the catalog reconnects.</p> : null}
    </section> : <section className="browse-experience__results" aria-labelledby="browse-results-heading" aria-busy={loading}>
      <header className="browse-experience__results-header"><div><p className="browse-experience__eyebrow">Focused discovery</p><h2 id="browse-results-heading">{debouncedQuery ? `Stories answering “${debouncedQuery}”` : "Your filtered program"}</h2></div><span>{items.length} of {total.toLocaleString()}</span></header>
      {advancedCount ? <p className="browse-experience__scope-note"><BrowseIcon name="shield"/> Advanced filters refine playable titles. Clear them to search everything.</p> : null}
      {entities.length ? <section className="browse-experience__entities" aria-labelledby="browse-related-heading"><h3 id="browse-related-heading">Related people and subjects</h3><div>{entities.map((entity) => <Link href={entity.href ?? `/browse?q=${encodeURIComponent(entity.name)}`} key={`${entity.kind}:${entity.id}`}><small>{entity.kind}</small><strong>{entity.name}</strong>{entity.detail ? <span>{entity.detail}</span> : null}</Link>)}</div></section> : null}
      {loading ? <div className="browse-experience__loading" role="status"><span/><p>Searching beyond the visible shelves…</p></div> : null}
      {error ? <div className="browse-experience__error" role="alert"><strong>The reel caught for a moment.</strong><p>{error}</p><button type="button" onClick={() => setRetryNonce((value) => value + 1)}>Try again</button></div> : null}
      {!loading && !error && !items.length ? <div className="browse-experience__empty"><BrowseIcon name="search"/><h3>No story answered that call.</h3><p>Try another character, loosen a filter, or return to all collections.</p><button type="button" onClick={resetDiscovery}>Return to collections</button></div> : null}
      {!loading && items.length ? <div className="browse-experience__grid">{items.map((item, index) => <div className="browse-experience__card" style={{ animationDelay: `${Math.min(index % RESULT_PAGE_SIZE, 12) * 45}ms` }} key={`${item.kind}:${item.id}`}><CatalogCard density="detailed" item={{ href: item.href || `/${item.kind === "movie" ? "movies" : "series"}/${item.slug}`, title: item.title, kind: item.kind, posterUrl: item.poster_url, description: item.short_description, primaryMeta: releaseYear(item.release_date), secondaryMeta: cardFacts(item), genres: item.genres }}/></div>)}</div> : null}
      <div className="browse-experience__sentinel" ref={resultSentinelRef} aria-hidden="true"/>
      {hasMore && !loading ? <div className="browse-experience__more"><button type="button" onClick={loadMoreResults} disabled={loadingMore}>{loadingMore ? "Opening the next reel…" : "Load 32 more"}<BrowseIcon name="arrow"/></button><small>More titles arrive automatically as you explore.</small></div> : null}
      {!hasMore && items.length ? <p className="browse-experience__end">You have reached the final frame of this search.</p> : null}
      <button className="browse-experience__return" type="button" onClick={resetDiscovery}>← Return to all collections</button>
    </section>}
    <p className="browse-experience__announcement" aria-live="polite" aria-atomic="true">{announcement}</p>

    {filterOpen ? <div className="browse-experience__dialog-layer"><button className="browse-experience__dialog-scrim" type="button" onClick={() => setFilterOpen(false)} aria-label="Dismiss advanced filters"/><div ref={dialogRef} className="browse-experience__dialog" role="dialog" aria-modal="true" aria-labelledby="browse-filter-heading">
      <header className="browse-experience__dialog-header"><div><p className="browse-experience__eyebrow">Shape the program</p><h2 id="browse-filter-heading">Advanced filters</h2></div><button ref={closeButtonRef} type="button" onClick={() => setFilterOpen(false)} aria-label="Close advanced filters"><BrowseIcon name="close"/></button></header>
      <p className="browse-experience__filter-scope"><BrowseIcon name="shield"/> These precise filters apply to playable {brand.short_name} titles. The search bar explores the complete discovery catalog.</p>
      <div className="browse-experience__filter-groups">
        <section className="browse-experience__filter-group" aria-labelledby="filter-story"><header><BrowseIcon name="sparkles"/><div><h3 id="filter-story">Story &amp; mood</h3><p>Choose the emotional language of the night.</p></div></header><FilterChoices label="Genres" values={facets("genre")} selected={filters.genres} onToggle={(value) => toggleArray("genres", value)}/><FilterChoices label="Themes" values={facets("theme")} selected={filters.themes} onToggle={(value) => toggleArray("themes", value)}/><FilterChoices label="Tags" values={facets("tag")} selected={filters.tags} onToggle={(value) => toggleArray("tags", value)}/></section>
        <section className="browse-experience__filter-group" aria-labelledby="filter-format"><header><BrowseIcon name="film"/><div><h3 id="filter-format">Format &amp; commitment</h3><p>Set the shape and time the story can take.</p></div></header>
          <fieldset className="browse-experience__filter-set"><legend>Title type</legend><div className="browse-experience__filter-choices">{[{ value: "", label: "Movies & series" }, { value: "movie", label: "Movies" }, { value: "series", label: "Series" }].map((option) => <button className={filters.kind === option.value ? "browse-experience__filter-choice browse-experience__filter-choice--active" : "browse-experience__filter-choice"} type="button" aria-pressed={filters.kind === option.value} onClick={() => setFilters((current) => ({ ...current, kind: option.value as BrowseFilters["kind"] }))} key={option.label}>{option.label}</button>)}</div></fieldset>
          <FilterChoices label="Formats" values={facets("content_format")} selected={filters.contentFormats} onToggle={(value) => toggleArray("contentFormats", value)}/><FilterChoices label="Runtime bands" values={facets("runtime_band")} selected={filters.runtimeBands} onToggle={(value) => toggleArray("runtimeBands", value)}/>
          <div className="browse-experience__range"><label>Minimum runtime<input type="number" min="1" max="600" inputMode="numeric" value={filters.runtimeMin} aria-invalid={Boolean(rangeValidation.runtimeError)} aria-describedby={rangeValidation.runtimeError ? "browse-runtime-error" : undefined} onChange={(event) => setFilters((current) => ({ ...current, runtimeMin: event.target.value }))} placeholder="Any"/><span>minutes</span></label><label>Maximum runtime<input type="number" min="1" max="600" inputMode="numeric" value={filters.runtimeMax} aria-invalid={Boolean(rangeValidation.runtimeError)} aria-describedby={rangeValidation.runtimeError ? "browse-runtime-error" : undefined} onChange={(event) => setFilters((current) => ({ ...current, runtimeMax: event.target.value }))} placeholder="Any"/><span>minutes</span></label></div>{rangeValidation.runtimeError ? <p className="browse-experience__range-error" id="browse-runtime-error" role="alert">{rangeValidation.runtimeError}</p> : null}
          <fieldset className="browse-experience__filter-set"><legend>Series status</legend><div className="browse-experience__filter-choices">{[{ value: "", label: "Any status" }, { value: "ongoing", label: "Still unfolding" }, { value: "completed", label: "Complete" }].map((option) => <button className={filters.airing === option.value ? "browse-experience__filter-choice browse-experience__filter-choice--active" : "browse-experience__filter-choice"} type="button" aria-pressed={filters.airing === option.value} onClick={() => setFilters((current) => ({ ...current, airing: option.value as BrowseFilters["airing"] }))} key={option.label}>{option.label}</button>)}</div></fieldset>
        </section>
        <section className="browse-experience__filter-group" aria-labelledby="filter-origin"><header><BrowseIcon name="globe"/><div><h3 id="filter-origin">Time &amp; origin</h3><p>Travel by release era, language, or place.</p></div></header>
          <div className="browse-experience__range"><label>From year<input type="number" min="1888" max="2100" inputMode="numeric" value={filters.yearMin} aria-invalid={Boolean(rangeValidation.yearError)} aria-describedby={rangeValidation.yearError ? "browse-year-error" : undefined} onChange={(event) => setFilters((current) => ({ ...current, yearMin: event.target.value }))} placeholder="Any"/></label><label>Through year<input type="number" min="1888" max="2100" inputMode="numeric" value={filters.yearMax} aria-invalid={Boolean(rangeValidation.yearError)} aria-describedby={rangeValidation.yearError ? "browse-year-error" : undefined} onChange={(event) => setFilters((current) => ({ ...current, yearMax: event.target.value }))} placeholder="Any"/></label></div>{rangeValidation.yearError ? <p className="browse-experience__range-error" id="browse-year-error" role="alert">{rangeValidation.yearError}</p> : null}
          <FilterChoices label="Release decades" values={facets("release_decade")} selected={filters.releaseDecades} onToggle={(value) => toggleArray("releaseDecades", value)}/><FilterChoices label="Languages" values={facets("language")} selected={filters.languages} onToggle={(value) => toggleArray("languages", value)}/><FilterChoices label="Countries" values={facets("country")} selected={filters.countries} onToggle={(value) => toggleArray("countries", value)}/>
        </section>
        <section className="browse-experience__filter-group" aria-labelledby="filter-audience"><header><BrowseIcon name="shield"/><div><h3 id="filter-audience">Audience</h3><p>Match the room and decide how the program is ordered.</p></div></header><FilterChoices label="Maturity ratings" values={facets("maturity_rating")} selected={filters.maturityRatings} onToggle={(value) => toggleArray("maturityRatings", value)}/><SearchableFilterChoices label="Studios" values={facets("studio")} selected={filters.studios} onToggle={(value) => toggleArray("studios", value)}/><label className="browse-experience__select">Order the program<select value={filters.sort} onChange={(event) => setFilters((current) => ({ ...current, sort: event.target.value as BrowseFilters["sort"] }))}><option value="newest">Newest arrivals</option><option value="oldest">Earliest releases</option><option value="title_asc">Title, A to Z</option><option value="title_desc">Title, Z to A</option></select></label></section>
      </div>
      <footer className="browse-experience__dialog-footer"><button type="button" onClick={() => setFilters(EMPTY_BROWSE_FILTERS)} disabled={!advancedCount}>Clear all</button><button type="button" onClick={() => setFilterOpen(false)} disabled={!rangeValidation.valid}>{advancedCount ? `Show ${total.toLocaleString()} titles` : debouncedQuery ? "Search everything" : "Return to collections"}<BrowseIcon name="arrow"/></button></footer>
    </div></div> : null}
  </main>;
}
