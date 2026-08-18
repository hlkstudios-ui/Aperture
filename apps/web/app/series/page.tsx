import { ContentCard } from "@/app/components/content-card";
import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch, Series } from "@/app/lib/catalog";

export const metadata = { title: "Series" };

export default async function SeriesPage(){
  const series = await catalogFetch<Series[]>("/catalog/series?limit=100");
  return <main className="catalog-page"><SiteHeader/><header className="library-heading"><p className="eyebrow">Episodic stories</p><h1>Series</h1><p>Stay awhile. The world keeps unfolding.</p></header>{series.length ? <section className="catalog-grid" aria-label="Published series">{series.map(item=><ContentCard title={item} kind="series" key={item.id}/>)}</section> : <section className="catalog-state compact"><h2>No series are published yet.</h2><p>Check back when the first episode arrives.</p></section>}</main>;
}
