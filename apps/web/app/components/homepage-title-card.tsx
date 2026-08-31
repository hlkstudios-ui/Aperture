import { CatalogCard } from "@/app/components/catalog-card";
import type { HomepageTitle } from "@/app/lib/homepage";

function releaseYear(value:string|null|undefined){return value?new Date(value).getUTCFullYear().toString():"Coming soon"}
function runtimeLabel(minutes:number){const hours=Math.floor(minutes/60);const remainder=minutes%60;return hours?`${hours}h ${remainder}m`:`${minutes}m`}

export function HomepageTitleCard({title,position}:{title:HomepageTitle;position?:number}) {
  const duration=title.kind==="movie"
    ? title.runtime_minutes?runtimeLabel(title.runtime_minutes):null
    : title.season_count?`${title.season_count} ${title.season_count===1?"season":"seasons"}`:null;
  return <CatalogCard density="compact" item={{
    href:`/${title.kind==="movie"?"movies":"series"}/${title.slug}`,
    title:title.title,
    kind:title.kind,
    posterUrl:title.poster_url,
    description:title.short_description,
    primaryMeta:releaseYear(title.release_date??null),
    secondaryMeta:[duration,title.maturity_rating].filter(Boolean).join(" · "),
    genres:title.genres?.map(genre=>genre.name)??[],
    position,
  }}/>;
}
