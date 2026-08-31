import Link from "next/link";
import { notFound } from "next/navigation";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import { SiteHeader } from "@/app/components/site-header";
import { getSiteBrand } from "@/app/lib/site-brand-server";

const apiOrigin =
  process.env.API_ORIGIN ??
  "http://localhost:8000";
type ExternalTitle = {
  title: string;
  original_title: string | null;
  short_description: string;
  release_date: string | null;
  maturity_rating: string | null;
  poster_url: string | null;
  country_code: string | null;
  original_language_code: string | null;
  genres: string[];
  studios: string[];
  availability: string;
};

export default async function ExternalTmdbTitlePage({
  params,
}: {
  params: Promise<{ kind: string; id: string }>;
}) {
  const { kind, id } = await params;
  if (!/^(movie|series)$/.test(kind) || !/^\d+$/.test(id)) notFound();
  const response = await fetch(
    `${apiOrigin}/catalog/external/tmdb/${kind}/${id}`,
    { next: { revalidate: 3600 } },
  );
  if (!response.ok) notFound();
  const title: ExternalTitle = await response.json();
  const brand = await getSiteBrand();
  return (
    <main className="external-title-shell">
      <SiteHeader />
      <section className="external-title-hero">
        <div className="external-title-poster">
          {title.poster_url ? (
            <ResponsivePoster
              src={title.poster_url}
              sizes="(max-width: 760px) 70vw, 500px"
              alt={`${title.title} poster`}
              loading="eager"
              fetchPriority="high"
            />
          ) : null}
        </div>
        <div className="external-title-copy">
          <h1>{title.title}</h1>
          {title.original_title ? <p>{title.original_title}</p> : null}
          <div className="external-title-facts">
            {title.release_date ? (
              <span>{title.release_date.slice(0, 4)}</span>
            ) : null}
            {title.maturity_rating ? (
              <span>{title.maturity_rating}</span>
            ) : null}
            {title.country_code ? <span>{title.country_code}</span> : null}
            {title.original_language_code ? (
              <span>{title.original_language_code.toUpperCase()}</span>
            ) : null}
            {title.genres.map((genre) => (
              <span key={genre}>{genre}</span>
            ))}
          </div>
          <p>{title.short_description}</p>
          {title.studios.length ? (
            <p>Studios · {title.studios.join(" · ")}</p>
          ) : null}
          <div className="external-title-note">
            This title was found in the global discovery catalog. Playback
            availability has not yet been confirmed for {brand.business_name}.
          </div>
          <Link className="secondary action-link" href="/search">
            Return to search
          </Link>
        </div>
      </section>
    </main>
  );
}
