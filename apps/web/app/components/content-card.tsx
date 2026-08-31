import { CatalogCard } from "@/app/components/catalog-card";
import { Movie, Series, releaseYear, runtimeLabel } from "@/app/lib/catalog";

export function ContentCard({title,kind}:{title:Movie|Series;kind:"movie"|"series"}) {
  const series=kind==="series"?title as Series:null;
  const episodeCount=series?.seasons.reduce((total,season)=>total+season.episodes.length,0)??0;
  const meta=kind==="movie"?runtimeLabel((title as Movie).runtime_minutes):`${series?.seasons.length??0} ${(series?.seasons.length??0)===1?"season":"seasons"}`;
  const primaryMeta=releaseYear(title.release_date);
  const secondaryMeta=series
    ? [meta, `${episodeCount} ${episodeCount===1?"episode":"episodes"}`, title.maturity_rating].filter(Boolean).join(" · ")
    : [meta,title.maturity_rating].filter(Boolean).join(" · ");
  return <CatalogCard item={{href:`/${kind==="movie"?"movies":"series"}/${title.slug}`,title:title.title,kind,posterUrl:title.poster_url,description:title.short_description,primaryMeta,secondaryMeta,genres:title.genres.map(genre=>genre.name)}}/>;
}
