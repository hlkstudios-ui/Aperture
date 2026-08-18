import { cookies } from "next/headers";
import Link from "next/link";
import { SiteHeader } from "@/app/components/site-header";
import { SearchAnalytics } from "@/app/components/search-analytics";
import { PersistentSearchForm } from "@/app/components/persistent-search-form";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import { catalogFetch } from "@/app/lib/catalog";

type SearchTitle = {
  id: string;
  kind: "movie" | "series";
  title: string;
  original_title: string | null;
  slug: string;
  short_description: string;
  release_date: string | null;
  maturity_rating: string | null;
  poster_url: string | null;
  content_format: string | null;
  country_code: string | null;
  original_language_code: string | null;
  studios: string[];
  genres: string[];
  season_count: number;
  episode_count: number;
  href: string;
  source: string;
  availability: string;
};
type SearchEntity = {
  id: string;
  kind: string;
  name: string;
  slug: string;
  detail: string | null;
  href: string | null;
};
type SearchResponse = {
  query: string;
  page: number;
  page_size: number;
  total_titles: number;
  total_entities: number;
  has_more: boolean;
  titles: SearchTitle[];
  entities: SearchEntity[];
};

export const metadata = { title: "Search" };

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[]; page?: string | string[] }>;
}) {
  const params = await searchParams;
  const analyticsEnabled = Boolean((await cookies()).get("aperture_session"));
  const query = typeof params.q === "string" ? params.q.trim() : "";
  const requestedPage =
    typeof params.page === "string" ? Number(params.page) : 1;
  const page =
    Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const results = query
    ? await catalogFetch<SearchResponse>(
        `/catalog/search?q=${encodeURIComponent(query)}&page=${page}&page_size=24`,
      )
    : null;
  const resultCount =
    (results?.total_titles ?? 0) + (results?.total_entities ?? 0);
  const pageHref = (nextPage: number) =>
    `/search?q=${encodeURIComponent(query)}&page=${nextPage}`;
  return (
    <main className="catalog-page universal-search-page">
      <SearchAnalytics
        enabled={analyticsEnabled}
        query={query}
        resultCount={resultCount}
      />
      <SiteHeader />
      <header className="search-heading universal-search-heading">
        <p className="eyebrow">Search the entire Aperture universe</p>
        <h1>Find anything.</h1>
        <p>
          Titles, original names, cast, characters, studios, episodes, genres,
          countries, languages and more.
        </p>
        <PersistentSearchForm query={query} />
      </header>
      {!query ? (
        <section className="search-prompt universal-search-prompt">
          <strong>Search without boundaries</strong>
          <span>
            Try a title, actor, character, studio, year, language, genre—or even
            a line from a synopsis.
          </span>
        </section>
      ) : null}
      {query && results && resultCount === 0 ? (
        <section className="catalog-state compact">
          <h2>No results for “{query}”</h2>
          <p>
            Try a shorter spelling, an original title, cast member, studio,
            country or genre.
          </p>
        </section>
      ) : null}
      {results && resultCount > 0 ? (
        <div className="universal-search-results">
          <header>
            <div>
              <p className="eyebrow">Complete database search</p>
              <h2>{results.total_titles} titles found</h2>
            </div>
            <span>
              {results.total_entities
                ? `Plus ${results.total_entities} related people and subjects`
                : "All matching titles"}
            </span>
          </header>
          {results.entities.length ? (
            <section
              className="search-entity-strip"
              aria-labelledby="related-matches"
            >
              <h2 id="related-matches">Related matches</h2>
              <div>
                {results.entities.map((entity) => (
                  <Link
                    href={
                      entity.href ??
                      `/search?q=${encodeURIComponent(entity.name)}`
                    }
                    key={`${entity.kind}:${entity.id}`}
                  >
                    <small>{entity.kind}</small>
                    <strong>{entity.name}</strong>
                  </Link>
                ))}
              </div>
            </section>
          ) : null}
          <section
            className="universal-title-grid"
            aria-label="Matching movies and series"
          >
            {results.titles.map((title) => (
              <Link
                className="universal-title-card"
                href={title.href}
                key={`${title.kind}:${title.id}`}
              >
                <span className="universal-title-art">
                  {title.poster_url ? (
                    <ResponsivePoster
                      src={title.poster_url}
                      sizes="(max-width: 760px) 120px, 180px"
                    />
                  ) : (
                    <i>{title.title.slice(0, 1)}</i>
                  )}
                  <small>{title.content_format ?? title.kind}</small>
                </span>
                <span className="universal-title-copy">
                  <strong>{title.title}</strong>
                  <span className={`search-availability ${title.source}`}>
                    {title.availability}
                  </span>
                  {title.original_title &&
                  title.original_title !== title.title ? (
                    <em>{title.original_title}</em>
                  ) : null}
                  <span className="universal-title-meta">
                    {title.release_date ? (
                      <b>{title.release_date.slice(0, 4)}</b>
                    ) : null}
                    {title.maturity_rating ? (
                      <b>{title.maturity_rating}</b>
                    ) : null}
                    {title.country_code ? <b>{title.country_code}</b> : null}
                    {title.original_language_code ? (
                      <b>{title.original_language_code.toUpperCase()}</b>
                    ) : null}
                  </span>
                  <p>{title.short_description}</p>
                  {title.kind === "series" ? (
                    <span className="universal-series-facts">
                      {title.season_count} seasons · {title.episode_count}{" "}
                      episodes
                    </span>
                  ) : null}
                  {title.genres.length ? (
                    <small>{title.genres.slice(0, 3).join(" · ")}</small>
                  ) : null}
                  {title.studios.length ? (
                    <small>
                      Studio · {title.studios.slice(0, 2).join(" · ")}
                    </small>
                  ) : null}
                </span>
              </Link>
            ))}
          </section>
          <nav
            className="universal-search-pagination"
            aria-label="Search result pages"
          >
            {page > 1 ? (
              <Link href={pageHref(page - 1)}>← Previous</Link>
            ) : (
              <span />
            )}
            <strong>Page {page}</strong>
            {results.has_more ? (
              <Link href={pageHref(page + 1)}>Next →</Link>
            ) : (
              <span />
            )}
          </nav>
        </div>
      ) : null}
    </main>
  );
}
