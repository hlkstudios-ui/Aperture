import Link from "next/link";
import { SiteHeader } from "@/app/components/site-header";
import { getSiteBrand } from "@/app/lib/site-brand-server";
import { catalogFetch } from "@/app/lib/catalog";
import { Collection } from "@/app/lib/curation";

export default async function CollectionsPage() {
  const brand = await getSiteBrand();
  const collections = await catalogFetch<Collection[]>("/curation/collections");
  return <main className="catalog-page"><SiteHeader /><section className="catalog-intro">
    <p className="eyebrow">Programmed by {brand.short_name}</p><h1>Collections</h1>
    <p>Films connected by craft, history, place, people, and feeling.</p>
  </section><section className="curation-grid">{collections.map((item) =>
    <Link href={`/collections/${item.slug}`} key={item.id} className="curation-card">
      <small>{item.kind.replaceAll("_", " ")}</small><h2>{item.title}</h2><p>{item.description}</p>
      <span>{item.items.length} available titles →</span>
    </Link>)}</section></main>;
}
