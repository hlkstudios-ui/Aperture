import { notFound } from "next/navigation";
import { SiteHeader } from "@/app/components/site-header";
import { journeyFetch } from "@/app/lib/curation";
import { JourneyProgress } from "./journey-progress";

export default async function JourneyPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let journey;
  try { journey = await journeyFetch(`/curation/journeys/${encodeURIComponent(slug)}`); }
  catch (error) { if ((error as Error & { status?: number }).status === 404) notFound(); throw error; }
  return <main className="catalog-page"><SiteHeader /><section className="catalog-intro">
    <p className="eyebrow">Film journey · {journey.total_items} titles</p><h1>{journey.title}</h1><p>{journey.description}</p>
  </section><JourneyProgress initial={journey} /></main>;
}
