import type { ReactNode } from "react";
import Link from "next/link";
import { CatalogDescriptionPreview } from "@/app/components/catalog-description-preview";
import { ResponsivePoster } from "@/app/components/responsive-poster";

export type CatalogCardModel = { href:string; title:string; kind:"movie"|"series"; posterUrl?:string|null; description?:string|null; primaryMeta?:ReactNode; secondaryMeta?:ReactNode; genres?:string[]; position?:number };

export function CatalogCard({item,density="detailed"}:{item:CatalogCardModel;density?:"compact"|"detailed"}) {
  return <article className={`content-card catalog-card catalog-card--${density} card-tone-${item.title.length%4}`}>
    <Link href={item.href} aria-label={`View ${item.title}`} aria-description={item.description??undefined}>
      <span className="card-art" aria-hidden="true">
        {item.posterUrl?<ResponsivePoster src={item.posterUrl} sizes={density==="compact"?"(max-width: 700px) 170px, 240px":"(max-width: 650px) 50vw, 250px"}/>:item.title.slice(0,1)}
        {item.position?<i className="marathon-order">{String(item.position).padStart(2,"0")}</i>:null}
        <span className="catalog-card__art-shade" />
      </span>
      <span className="card-copy">
        <span className="catalog-card__identity"><span>{item.kind==="movie"?"Film":"Series"}</span>{item.primaryMeta?<small>{item.primaryMeta}</small>:null}</span>
        <span className="catalog-card__heading"><strong className="catalog-card__title">{item.title}</strong><b aria-hidden="true">↗</b></span>
        {density==="detailed"&&item.description?<CatalogDescriptionPreview title={item.title} description={item.description}/>:null}
        {(item.genres?.length||item.secondaryMeta)?<span className="catalog-card__details">
          {item.genres?.length?<small className="card-genres">{item.genres.slice(0,2).join(" · ")}</small>:<span />}
          {item.secondaryMeta?<small className="card-facts">{item.secondaryMeta}</small>:null}
        </span>:null}
      </span>
    </Link>
  </article>;
}
