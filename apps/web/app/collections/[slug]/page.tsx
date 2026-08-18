import { notFound } from "next/navigation";
import { CuratedTitleList } from "@/app/components/curated-title-list";
import { SiteHeader } from "@/app/components/site-header";
import { collectionFetch } from "@/app/lib/curation";

export default async function CollectionPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let collection;
  try { collection = await collectionFetch(`/curation/collections/${encodeURIComponent(slug)}`); }
  catch (error) { if ((error as Error & { status?: number }).status === 404) notFound(); throw error; }
  return <main className="catalog-page"><SiteHeader /><section className="catalog-intro">
    <p className="eyebrow">{collection.kind.replaceAll("_", " ")}</p><h1>{collection.title}</h1>
    <p>{collection.description}</p></section><CuratedTitleList items={collection.items} /></main>;
}
