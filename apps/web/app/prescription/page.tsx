import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch, type NamedRecord } from "@/app/lib/catalog";
import { tasteDnaFetch } from "@/app/lib/recommendations";
import { PrescriptionLab } from "./prescription-lab";
import { featureFlags } from "@/app/lib/feature-flags";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function PrescriptionPage() {
  if (!featureFlags.experimentalRecommendations) notFound();
  const [dna, genres] = await Promise.all([
    tasteDnaFetch(),
    catalogFetch<NamedRecord[]>("/catalog/metadata/genres"),
  ]);
  return <main className="catalog-page prescription-page"><SiteHeader />
    <header className="library-heading"><p className="eyebrow">Intentional discovery</p><h1>Movie Prescription</h1><p>Trade endless browsing for one transparent, constraint-aware choice.</p></header>
    <section className="taste-dna-panel" aria-labelledby="taste-dna-title"><div><p className="eyebrow">Persisted viewing only · {dna.confidence} confidence</p><h2 id="taste-dna-title">Taste DNA</h2><p>{dna.watched_titles ? `${dna.watched_titles} observed title${dna.watched_titles === 1 ? "" : "s"}; ${dna.completed_titles} completed.` : "No viewing history yet. Insights will emerge from this profile's actual progress."}</p></div><div className="taste-insights">{dna.insights.length ? dna.insights.map((insight) => <span key={insight}>{insight}</span>) : <span>Cold-start state: no behavior is inferred.</span>}</div>{dna.genres.length ? <div className="taste-affinities">{dna.genres.map((genre) => <span key={genre.key}>{genre.label}<small>{genre.weight} observed weight</small></span>)}</div> : null}</section>
    <PrescriptionLab genres={genres} />
  </main>;
}
