import Link from "next/link";
import { ContentCard } from "@/app/components/content-card";
import { HomepageTitleCard } from "@/app/components/homepage-title-card";
import { HeroSlideshow, type HeroSlide } from "@/app/components/hero-slideshow";
import { CatalogFilterBrowser, type FilterTitle } from "@/app/components/catalog-filter-browser";
import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch, Movie, Series } from "@/app/lib/catalog";
import { homepageFetch, profileHomepageFetch, type PublicHomepage } from "@/app/lib/homepage";
import { setHomepageMode } from "@/app/homepage-actions";
import { optimizedBackdrop, optimizedPoster } from "@/app/lib/images";

export default async function Home() {
  let movies: Movie[] = [];
  let series: Series[] = [];
  let homepage: PublicHomepage = { hero: null, rails: [], published_at: null, mode: "curated", strategy: "published_editorial_snapshot" };
  let profileScoped = false;
  let failed = false;
  try {
    const [publicHomepage, profileHomepage, catalogMovies, catalogSeries] = await Promise.all([
      homepageFetch(),
      profileHomepageFetch(),
      catalogFetch<Movie[]>("/catalog/movies?limit=30"),
      catalogFetch<Series[]>("/catalog/series?limit=30"),
    ]);
    movies = catalogMovies;
    series = catalogSeries;
    homepage = publicHomepage;
    if (profileHomepage) {
      homepage = profileHomepage;
      profileScoped = true;
    }
  } catch {
    failed = true;
  }
  const feature = homepage.hero ?? movies[0];
  const heroSlides: HeroSlide[] = [
    ...movies.slice(0, 5).map((movie) => ({ ...movie, backdrop_url: optimizedBackdrop(movie.backdrop_url), kind: "movie" as const, runtime_minutes: movie.runtime_minutes })),
    ...series.filter((item) => item.is_ongoing).slice(0, 5).map((item) => ({ ...item, backdrop_url: optimizedBackdrop(item.backdrop_url), kind: "series" as const, runtime_minutes: null })),
  ]
    .sort((left, right) => (right.release_date ?? "").localeCompare(left.release_date ?? ""))
    .slice(0, 10);
  if (!heroSlides.length && feature) {
    heroSlides.push({
      id: feature.id,
      kind: "kind" in feature ? feature.kind : "movie",
      title: feature.title,
      slug: feature.slug,
      short_description: feature.short_description,
      maturity_rating: feature.maturity_rating,
      runtime_minutes: feature.runtime_minutes ?? null,
      backdrop_url: feature.backdrop_url,
      metadata_provider: feature.metadata_provider,
      release_date: null,
      original_title: null,
      country_code: null,
      genres: [],
    });
  }
  const filterTitles: FilterTitle[] = [
    ...movies.map((movie) => ({
      id: movie.id, kind: "movie" as const, title: movie.title, slug: movie.slug,
      short_description: movie.short_description, poster_url: optimizedPoster(movie.poster_url),
      release_date: movie.release_date, maturity_rating: movie.maturity_rating,
      country_code: movie.country_code, content_format: movie.content_format,
      original_language_code: movie.original_language_code, is_ongoing: null,
      studios: movie.studios, genres: movie.genres.map((genre) => genre.name),
      duration_minutes: movie.runtime_minutes,
      season_count: 0, episode_count: 0, audio_languages: [], subtitle_languages: [],
    })),
    ...series.map((item) => {
      const runtimes = item.seasons.flatMap((season) => season.episodes.map((episode) => episode.runtime_minutes));
      return {
        id: item.id, kind: "series" as const, title: item.title, slug: item.slug,
        short_description: item.short_description, poster_url: optimizedPoster(item.poster_url),
        release_date: item.release_date, maturity_rating: item.maturity_rating,
        country_code: item.country_code, content_format: item.content_format,
        original_language_code: item.original_language_code, is_ongoing: item.is_ongoing,
        studios: item.studios, genres: item.genres.map((genre) => genre.name),
        duration_minutes: runtimes.length ? Math.round(runtimes.reduce((sum, value) => sum + value, 0) / runtimes.length) : null,
        season_count: item.seasons.length,
        episode_count: item.seasons.reduce((sum, season) => sum + season.episodes.length, 0),
        audio_languages: [], subtitle_languages: [],
      };
    }),
  ];
  return (
    <main className="customer-shell">
      <SiteHeader />
      {failed ? (
        <section className="catalog-state">
          <p className="eyebrow">Catalog unavailable</p>
          <h1>The projector needs a moment.</h1>
          <p>
            We could not reach the catalog service. Refresh when the connection
            returns.
          </p>
        </section>
      ) : !feature ? (
        <section className="catalog-state">
          <p className="eyebrow">Aperture catalog</p>
          <h1>The first reel is on its way.</h1>
          <p>Published titles will appear here as soon as they are ready.</p>
        </section>
      ) : (
        <>
          <HeroSlideshow slides={heroSlides} />
          <CatalogFilterBrowser titles={filterTitles} />
          <section className="catalog-rails" aria-label="Catalog collections">
            {profileScoped ? <div className="homepage-mode-panel">
              <div><p className="eyebrow">Homepage strategy</p><h2>{homepage.mode === "no_algorithm" ? "No Algorithm" : "Curated"}</h2><p>{homepage.mode === "no_algorithm" ? "Transparent catalog indexes. No behavioral ranking or personalization." : "The published editorial homepage, programmed by Aperture Studio."}</p></div>
              <form action={setHomepageMode.bind(null, homepage.mode === "no_algorithm" ? "curated" : "no_algorithm")}><button className="secondary" type="submit">Switch to {homepage.mode === "no_algorithm" ? "Curated" : "No Algorithm"}</button></form>
            </div> : null}
            {homepage.rails.length ? homepage.rails.map((rail) => <div className="rail" key={rail.id}>
              <div className="rail-heading"><div><p className="eyebrow">{rail.eyebrow ?? "Aperture editorial"}</p><h2>{rail.title}</h2></div></div>
              <div className="card-rail">{rail.items.map((title, index) => <HomepageTitleCard title={title} position={index + 1} key={`${title.kind}:${title.id}`} />)}</div>
            </div>) : <><div className="rail">
              <div className="rail-heading">
                <div>
                  <p className="eyebrow">Feature films</p>
                  <h2>Stories for the long way home</h2>
                </div>
                <Link href="/movies">See all</Link>
              </div>
              <div className="card-rail">
                {movies.map((movie) => (
                  <ContentCard title={movie} kind="movie" key={movie.id} />
                ))}
              </div>
            </div>
            <div className="rail">
              <div className="rail-heading">
                <div>
                  <p className="eyebrow">Episodic</p>
                  <h2>Worlds worth returning to</h2>
                </div>
                <Link href="/series">See all</Link>
              </div>
              <div className="card-rail">
                {series.map((item) => (
                  <ContentCard title={item} kind="series" key={item.id} />
                ))}
              </div>
            </div>
            </>}
          </section>
        </>
      )}
    </main>
  );
}
