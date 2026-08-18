import Link from "next/link";
import type { HomepageTitle } from "@/app/lib/homepage";
import { ResponsivePoster } from "@/app/components/responsive-poster";

export function HomepageTitleCard({ title, position }: { title: HomepageTitle; position?: number }) {
  return (
    <Link className="content-card" href={`/${title.kind === "movie" ? "movies" : "series"}/${title.slug}`}>
      <span className="card-art" aria-hidden="true">{title.poster_url ? <ResponsivePoster src={title.poster_url} sizes="(max-width: 700px) 170px, 240px" /> : title.title[0]}{position ? <i className="marathon-order">{String(position).padStart(2, "0")}</i> : null}</span>
      <span className="card-copy">
        <strong>{title.title}</strong>
        <small>{title.kind === "movie" ? "Film" : "Series"}{title.maturity_rating ? ` · ${title.maturity_rating}` : ""}</small>
      </span>
    </Link>
  );
}
