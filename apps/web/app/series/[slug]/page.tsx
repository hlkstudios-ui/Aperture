import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch, releaseYear, Series } from "@/app/lib/catalog";
import { ContentCard } from "@/app/components/content-card";
import { ResponsiveBackdrop } from "@/app/components/responsive-backdrop";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import { SeasonBrowser } from "./season-browser";
import { TitleStateActions } from "@/app/components/title-state-actions";

async function loadSeries(slug: string) {
  try {
    return await catalogFetch<Series>(
      `/catalog/series/${encodeURIComponent(slug)}`,
    );
  } catch (error) {
    if ((error as Error & { status?: number }).status === 404) notFound();
    throw error;
  }
}
type SeriesPageProps = { params: Promise<{ slug: string }> };
export async function generateMetadata({
  params,
}: SeriesPageProps): Promise<Metadata> {
  const { slug } = await params;
  const series = await loadSeries(slug);
  return { title: series.title, description: series.short_description };
}

export default async function SeriesDetail({ params }: SeriesPageProps) {
  const { slug } = await params;
  const [series, related] = await Promise.all([
    loadSeries(slug),
    catalogFetch<Series[]>("/catalog/series?limit=20"),
  ]);
  const episodeCount = series.seasons.reduce(
    (total, season) => total + season.episodes.length,
    0,
  );
  return (
    <main className="detail-page">
      <SiteHeader />
      <section className="detail-hero series-detail cinematic-detail-hero">
        {series.backdrop_url ? (
          <ResponsiveBackdrop
            className="detail-backdrop"
            src={series.backdrop_url}
          />
        ) : null}
        <div className="detail-backdrop-shade" aria-hidden="true" />
        <div className="detail-art" aria-hidden="true">
          {series.poster_url ? (
            <ResponsivePoster
              src={series.poster_url}
              sizes="(max-width: 760px) 46vw, 300px"
              loading="eager"
              fetchPriority="high"
            />
          ) : (
            <span>{series.title[0]}</span>
          )}
        </div>
        <div className="detail-copy">
          <Link className="back-link" href="/series">
            ← Series
          </Link>
          <p className="eyebrow">
            {series.is_ongoing ? "Ongoing series" : "Series"}
          </p>
          <h1>{series.title}</h1>
          {series.original_title ? (
            <p className="detail-original-title">
              Original title · {series.original_title}
            </p>
          ) : null}
          <p className="detail-meta">
            {releaseYear(series.release_date)} · {series.seasons.length}{" "}
            {series.seasons.length === 1 ? "season" : "seasons"}
            {episodeCount ? ` · ${episodeCount} episodes` : ""} ·{" "}
            {series.maturity_rating ?? "Not rated"}
          </p>
          {series.genres.length ? (
            <div className="detail-genre-chips">
              {series.genres.map((genre) => (
                <span key={genre.id}>{genre.name}</span>
              ))}
            </div>
          ) : null}
          <p className="detail-lede">{series.short_description}</p>
          <div className="hero-actions">
            <a className="primary action-link" href="#episodes">
              Start series
            </a>
            <TitleStateActions
              id={series.id}
              kind="series"
              title={series.title}
              slug={series.slug}
              posterUrl={series.poster_url}
            />
          </div>
        </div>
      </section>
      <section className="detail-body series-about">
        <article>
          <p className="eyebrow">The story</p>
          <h2>About the series</h2>
          <p>{series.synopsis}</p>
        </article>
        <aside>
          <p className="eyebrow">At a glance</p>
          <h2>Series details</h2>
          <dl>
            {series.original_title ? (
              <div>
                <dt>Original title</dt>
                <dd>{series.original_title}</dd>
              </div>
            ) : null}
            {series.genres.length ? (
              <div>
                <dt>Genres</dt>
                <dd>{series.genres.map((genre) => genre.name).join(", ")}</dd>
              </div>
            ) : null}
            {series.original_language_code ? (
              <div>
                <dt>Language</dt>
                <dd>{series.original_language_code.toUpperCase()}</dd>
              </div>
            ) : null}
            {series.country_code ? (
              <div>
                <dt>Country</dt>
                <dd>{series.country_code}</dd>
              </div>
            ) : null}
            <div>
              <dt>Status</dt>
              <dd>
                {series.is_ongoing
                  ? "Ongoing"
                  : "Completed or returning status unavailable"}
              </dd>
            </div>
            <div>
              <dt>Catalog</dt>
              <dd>
                {series.seasons.length} seasons · {episodeCount} episodes
              </dd>
            </div>
          </dl>
        </aside>
      </section>
      <section className="episode-library" id="episodes">
        <SeasonBrowser seasons={series.seasons} />
      </section>
      <section className="related">
        <p className="eyebrow">More like this</p>
        <h2>Continue exploring</h2>
        <div className="card-rail">
          {related
            .filter((item) => item.id !== series.id)
            .slice(0, 6)
            .map((item) => (
              <ContentCard title={item} kind="series" key={item.id} />
            ))}
        </div>
      </section>
    </main>
  );
}
