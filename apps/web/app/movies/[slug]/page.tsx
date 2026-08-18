import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ContentCard } from "@/app/components/content-card";
import { MyListButton } from "@/app/components/my-list-button";
import { ResponsiveBackdrop } from "@/app/components/responsive-backdrop";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import { TitleStateActions } from "@/app/components/title-state-actions";
import { forwardedGeoHeaders } from "@/app/lib/geo-headers";
import { SiteHeader } from "@/app/components/site-header";
import {
  catalogFetch,
  Credit,
  FilmKnowledgeGraph,
  Movie,
  NamedRecord,
  Preview,
  releaseYear,
  runtimeLabel,
} from "@/app/lib/catalog";
import { FilmKnowledgeGraphView } from "./film-knowledge-graph";
import { CommunityPanel, type Community } from "./community-panel";
import { featureFlags } from "@/app/lib/feature-flags";

async function loadMovie(slug: string) {
  try {
    return await catalogFetch<Movie>(
      `/catalog/movies/${encodeURIComponent(slug)}`,
    );
  } catch (error) {
    if ((error as Error & { status?: number }).status === 404) notFound();
    throw error;
  }
}
type MoviePageProps = { params: Promise<{ slug: string }> };

export async function generateMetadata({
  params,
}: MoviePageProps): Promise<Metadata> {
  const { slug } = await params;
  const movie = await loadMovie(slug);
  return { title: movie.title, description: movie.short_description };
}

export default async function MoviePage({ params }: MoviePageProps) {
  const { slug } = await params;
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("aperture_session");
  const authenticated = Boolean(sessionCookie);
  const moviePromise = loadMovie(slug);
  const [movie, credits, people, previews, related, playback, knowledge] =
    await Promise.all([
      moviePromise,
      catalogFetch<Credit[]>(
        `/catalog/movies/${encodeURIComponent(slug)}/credits`,
      ),
      catalogFetch<NamedRecord[]>("/catalog/metadata/people"),
      catalogFetch<Preview[]>(
        `/catalog/movies/${encodeURIComponent(slug)}/previews`,
      ),
      catalogFetch<Movie[]>("/catalog/movies"),
      catalogFetch<{ available: boolean }>(
        `/catalog/movies/${encodeURIComponent(slug)}/playback-availability`,
      ),
      catalogFetch<FilmKnowledgeGraph>(
        `/catalog/movies/${encodeURIComponent(slug)}/knowledge-graph`,
      ),
    ]);
  const peopleById = new Map(people.map((person) => [person.id, person.name]));
  let community: Community | null = null;
  if (featureFlags.community && sessionCookie) {
    const response = await fetch(
      `${process.env.API_ORIGIN ?? "http://localhost:8000"}/community/movies/${movie.id}`,
      {
        cache: "no-store",
        headers: {
          cookie: `${sessionCookie.name}=${sessionCookie.value}`,
          ...(await forwardedGeoHeaders()),
        },
      },
    );
    if (response.ok) community = (await response.json()) as Community;
  }
  const creditLine = (role: string) =>
    credits
      .filter((c) => c.role.toLowerCase() === role)
      .map((c) => peopleById.get(c.person_id))
      .filter(Boolean)
      .join(", ");
  return (
    <main className="detail-page">
      <SiteHeader />
      <section className="detail-hero cinematic-detail-hero">
        {movie.backdrop_url ? (
          <ResponsiveBackdrop
            className="detail-backdrop"
            src={movie.backdrop_url}
          />
        ) : null}
        <div className="detail-backdrop-shade" aria-hidden="true" />
        <div className="detail-art" aria-hidden="true">
          {movie.poster_url ? (
            <ResponsivePoster
              src={movie.poster_url}
              sizes="(max-width: 760px) 46vw, 300px"
              loading="eager"
              fetchPriority="high"
            />
          ) : (
            <span>{movie.title[0]}</span>
          )}
        </div>
        <div className="detail-copy">
          <Link className="back-link" href="/movies">
            ← Movies
          </Link>
          <p className="eyebrow">Featured film</p>
          <h1>{movie.title}</h1>
          {movie.original_title ? (
            <p className="detail-original-title">
              Original title · {movie.original_title}
            </p>
          ) : null}
          <p className="detail-meta">
            {releaseYear(movie.release_date)} ·{" "}
            {runtimeLabel(movie.runtime_minutes)} ·{" "}
            {movie.maturity_rating ?? "Not rated"}
          </p>
          {movie.genres.length ? (
            <div className="detail-genre-chips">
              {movie.genres.map((genre) => (
                <span key={genre.id}>{genre.name}</span>
              ))}
            </div>
          ) : null}
          <p className="detail-lede">{movie.short_description}</p>
          <div className="hero-actions">
            {playback.available ? (
              <Link
                className="primary action-link"
                href={`/watch/movies/${movie.slug}`}
              >
                Play
              </Link>
            ) : (
              <a className="primary action-link" href="#availability">
                Playback status
              </a>
            )}
            <MyListButton movieId={movie.id} authenticated={authenticated} />
            <TitleStateActions
              id={movie.id}
              kind="movie"
              title={movie.title}
              slug={movie.slug}
              posterUrl={movie.poster_url}
            />
          </div>
        </div>
      </section>
      <section className="detail-body">
        <article>
          <p className="eyebrow">The story</p>
          <h2>About the film</h2>
          <p>{movie.synopsis}</p>
          <div className="availability" id="availability">
            <strong>
              {playback.available ? "Ready to watch" : "Playback preparation"}
            </strong>
            <span>
              {playback.available
                ? "Sign in, select a profile, and start the adaptive stream."
                : "This catalog title has no licensed video asset attached yet."}
            </span>
          </div>
          {previews.length > 0 && (
            <div>
              <h2>Trailers & clips</h2>
              {previews.map((p) => (
                <p key={p.id}>
                  {p.title} {p.duration_seconds && `· ${p.duration_seconds}s`}
                </p>
              ))}
            </div>
          )}
        </article>
        <aside>
          <p className="eyebrow">At a glance</p>
          <h2>Film details</h2>
          <dl>
            {movie.original_title ? (
              <div>
                <dt>Original title</dt>
                <dd>{movie.original_title}</dd>
              </div>
            ) : null}
            {movie.genres.length ? (
              <div>
                <dt>Genres</dt>
                <dd>{movie.genres.map((g) => g.name).join(", ")}</dd>
              </div>
            ) : null}
            {movie.themes.length ? (
              <div>
                <dt>Themes</dt>
                <dd>{movie.themes.map((g) => g.name).join(", ")}</dd>
              </div>
            ) : null}
            {creditLine("actor") ? (
              <div>
                <dt>Cast</dt>
                <dd>{creditLine("actor")}</dd>
              </div>
            ) : null}
            {creditLine("director") ? (
              <div>
                <dt>Director</dt>
                <dd>{creditLine("director")}</dd>
              </div>
            ) : null}
            {movie.original_language_code ? (
              <div>
                <dt>Language</dt>
                <dd>{movie.original_language_code.toUpperCase()}</dd>
              </div>
            ) : null}
            {movie.country_code ? (
              <div>
                <dt>Country</dt>
                <dd>{movie.country_code}</dd>
              </div>
            ) : null}
            <div>
              <dt>Runtime</dt>
              <dd>{runtimeLabel(movie.runtime_minutes)}</dd>
            </div>
            <div>
              <dt>Release</dt>
              <dd>{releaseYear(movie.release_date)}</dd>
            </div>
          </dl>
        </aside>
      </section>
      <FilmKnowledgeGraphView graph={knowledge} />
      {featureFlags.community ? (
        <CommunityPanel
          movieId={movie.id}
          authenticated={authenticated}
          initialCommunity={community}
        />
      ) : null}
      <section className="related">
        <p className="eyebrow">More like this</p>
        <h2>Continue exploring</h2>
        <div className="card-rail">
          {related
            .filter((item) => item.id !== movie.id)
            .slice(0, 4)
            .map((item) => (
              <ContentCard title={item} kind="movie" key={item.id} />
            ))}
          {related.length === 1 && (
            <p className="empty-inline">
              More related films will appear as the catalog grows.
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
