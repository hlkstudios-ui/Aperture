import { ContentCard } from "@/app/components/content-card";
import { SiteHeader } from "@/app/components/site-header";
import { featureFlags } from "@/app/lib/feature-flags";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";
import {
  reasonLabels,
  recommendationFetch,
} from "@/app/lib/recommendations";

export default async function DiscoverPage() {
  if (!featureFlags.experimentalRecommendations) notFound();
  const recommendations = await recommendationFetch();
  return (
    <main className="catalog-page discover-page">
      <SiteHeader />
      <header className="library-heading">
        <p className="eyebrow">For your active profile</p>
        <h1>Discover</h1>
        <p>
          {!recommendations.personalized
            ? "No Algorithm is active. Results use only editorial programming and anonymous aggregate popularity, not this profile's activity."
            : recommendations.cold_start
            ? "An editorial and popularity-led starting point while your taste takes shape."
            : `Ranked from your preferences and viewing context. ${recommendations.watched_titles_excluded} watched title${recommendations.watched_titles_excluded === 1 ? "" : "s"} hidden.`}
        </p>
      </header>
      <section className="recommendation-disclosure" aria-label="How recommendations work">
        <strong>{recommendations.personalized ? "Explainable rules, not machine learning." : "Profile personalization is off."}</strong>
        <span>
          Every card states why it appears. Scores are deterministic combinations
          of editorial selection, catalog similarity, profile preferences, and
          recent aggregate popularity.
        </span>
      </section>
      {recommendations.items.length ? (
        <section className="recommendation-grid" aria-label="Recommended titles">
          {recommendations.items.map((item) => {
            const title = item.movie ?? item.series;
            if (!title) return null;
            return (
              <article className="recommendation-card" key={`${item.kind}:${title.id}`}>
                <ContentCard title={title} kind={item.kind} />
                <div className="recommendation-reasons">
                  <p>Why this appears</p>
                  <ul>
                    {item.reasons.map((reason) => (
                      <li key={reason}>{reasonLabels[reason]}</li>
                    ))}
                  </ul>
                </div>
              </article>
            );
          })}
        </section>
      ) : (
        <section className="catalog-state compact">
          <h2>No unwatched titles are available.</h2>
          <p>Newly published titles will appear here automatically.</p>
        </section>
      )}
    </main>
  );
}
