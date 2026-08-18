import Link from "next/link";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { Series } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
export default async function SeriesPreview({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [admin, series] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<Series>(`/admin/catalog/series/${id}`),
  ]);
  return (
    <StudioShell
      admin={admin}
      active="series"
      eyebrow="Private catalog preview"
      title={series.title}
      actions={
        <Link
          className="studio-secondary action-link"
          href={`/studio/series/${id}`}
        >
          Back to editor
        </Link>
      }
    >
      <article className="studio-preview">
        <div className="preview-art series" aria-hidden="true">
          {series.title[0]}
        </div>
        <div>
          <span className={`catalog-badge ${series.status}`}>
            {series.status}
          </span>
          <h2>{series.title}</h2>
          <p className="preview-short">{series.short_description}</p>
          <p>{series.synopsis}</p>
          {series.seasons.map((season) => (
            <section className="preview-season" key={season.id}>
              <h3>Season {season.number}</h3>
              {season.episodes.map((episode) => (
                <p key={episode.id}>
                  {episode.number}. {episode.title} · {episode.runtime_minutes}m
                </p>
              ))}
            </section>
          ))}
        </div>
      </article>
    </StudioShell>
  );
}
