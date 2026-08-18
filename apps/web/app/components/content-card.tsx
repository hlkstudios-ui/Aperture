import Link from "next/link";
import { Movie, Series, releaseYear, runtimeLabel } from "@/app/lib/catalog";
import { ResponsivePoster } from "@/app/components/responsive-poster";

export function ContentCard({
  title,
  kind,
}: {
  title: Movie | Series;
  kind: "movie" | "series";
}) {
  const href = `/${kind === "movie" ? "movies" : "series"}/${title.slug}`;
  const series = kind === "series" ? title as Series : null;
  const episodeCount = series?.seasons.reduce((total, season) => total + season.episodes.length, 0) ?? 0;
  const meta =
    kind === "movie"
      ? runtimeLabel((title as Movie).runtime_minutes)
      : `${series?.seasons.length ?? 0} ${(series?.seasons.length ?? 0) === 1 ? "season" : "seasons"}`;
  return (
    <article className={`content-card card-tone-${title.title.length % 4}`}>
      <Link href={href} aria-label={`View ${title.title}`}>
        <div className="card-art" aria-hidden="true">
          {title.poster_url ? <ResponsivePoster src={title.poster_url} sizes="(max-width: 650px) 50vw, 250px" /> : <span>{title.title.slice(0, 1)}</span>}
        </div>
        <div className="card-copy">
          <p className="card-kind">{kind}</p>
          <h3>{title.title}</h3>
          <p>
            {releaseYear(title.release_date)} <span>·</span> {meta}{" "}
            {title.maturity_rating && (
              <>
                <span>·</span> {title.maturity_rating}
              </>
            )}
          </p>
          {series ? <p className="card-facts">{episodeCount} {episodeCount === 1 ? "episode" : "episodes"}{series.is_ongoing !== null ? <> <span>·</span> {series.is_ongoing ? "Ongoing" : "Completed"}</> : null}</p> : null}
          {title.genres.length ? <p className="card-genres">{title.genres.slice(0, 3).map((genre) => genre.name).join(" · ")}</p> : null}
        </div>
      </Link>
    </article>
  );
}
