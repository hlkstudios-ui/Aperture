import Link from "next/link";
import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch } from "@/app/lib/catalog";
import { Journey } from "@/app/lib/curation";

export default async function JourneysPage() {
  const journeys = await catalogFetch<Journey[]>("/curation/journeys");
  return <main className="catalog-page"><SiteHeader /><section className="catalog-intro">
    <p className="eyebrow">Guided viewing</p><h1>Film Journeys</h1><p>Follow an idea across chapters and films.</p>
  </section><section className="curation-grid">{journeys.map((item) =>
    <Link href={`/journeys/${item.slug}`} key={item.id} className="curation-card">
      <small>{item.chapters.length} chapters</small><h2>{item.title}</h2><p>{item.description}</p>
      <span>{item.total_items} available titles →</span>
    </Link>)}</section></main>;
}
