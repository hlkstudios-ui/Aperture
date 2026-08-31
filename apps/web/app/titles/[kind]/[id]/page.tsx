import Link from "next/link";
import { notFound } from "next/navigation";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch } from "@/app/lib/catalog";

type DiscoveredTitle = {
  kind: "movie" | "series";
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
};

export default async function DiscoveredTitlePage({
  params,
}: {
  params: Promise<{ kind: string; id: string }>;
}) {
  const { kind, id } = await params;
  if (!/^(movie|series)$/.test(kind) || !/^amt_[A-Za-z0-9_-]{12,180}$/.test(id)) {
    notFound();
  }
  let title: DiscoveredTitle;
  try {
    title = await catalogFetch<DiscoveredTitle>(`/catalog/titles/${encodeURIComponent(id)}`);
  } catch {
    notFound();
  }
  if (title.kind !== kind) notFound();
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
            {title.release_date ? <span>{title.release_date.slice(0, 4)}</span> : null}
            {title.maturity_rating ? <span>{title.maturity_rating}</span> : null}
            {title.country_code ? <span>{title.country_code}</span> : null}
            {title.original_language_code ? (
              <span>{title.original_language_code.toUpperCase()}</span>
            ) : null}
            {title.genres.map((genre) => <span key={genre}>{genre}</span>)}
          </div>
          <p>{title.short_description}</p>
          {title.studios.length ? <p>Studios · {title.studios.join(" · ")}</p> : null}
          <Link className="secondary action-link" href="/browse">Return to Browse</Link>
        </div>
      </section>
    </main>
  );
}
