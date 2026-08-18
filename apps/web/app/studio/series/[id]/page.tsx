import Link from "next/link";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { Series } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { setSeriesStatusAction } from "@/app/studio/actions";
import {
  BulkEpisodeForm,
  EpisodeForm,
  SeasonForm,
  SeriesTerritoriesForm,
} from "@/app/studio/components/series-forms";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { SchedulingForm } from "@/app/studio/components/scheduling-form";
export default async function EditSeries({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ created?: string }>;
}) {
  const { id } = await params;
  const [{ created }, admin, series] = await Promise.all([
    searchParams,
    requireAdminSession(),
    adminCatalogFetch<Series>(`/admin/catalog/series/${id}`),
  ]);
  const next = Math.max(0, ...series.seasons.map((item) => item.number)) + 1;
  return (
    <StudioShell
      admin={admin}
      active="series"
      eyebrow="Series editor"
      title={series.title}
      actions={
        <div className="editor-header-actions">
          <span className={`catalog-badge ${series.status}`}>
            {series.status}
          </span>
          <Link
            className="studio-secondary action-link"
            href={`/studio/series/${id}/preview`}
          >
            Preview
          </Link>
          <form
            action={setSeriesStatusAction.bind(
              null,
              id,
              series.status === "published" ? "draft" : "published",
            )}
          >
            <button className="studio-primary" type="submit">
              {series.status === "published" ? "Unpublish" : "Publish"}
            </button>
          </form>
        </div>
      }
    >
      {created && (
        <p className="studio-notice" role="status">
          Draft series created. Build its hierarchy before publishing.
        </p>
      )}
      <section className="hierarchy-summary">
        <div>
          <p className="eyebrow">Series metadata</p>
          <h2>{series.short_description}</h2>
          <p>{series.synopsis}</p>
        </div>
        <dl>
          <div>
            <dt>Seasons</dt>
            <dd>{series.seasons.length}</dd>
          </div>
          <div>
            <dt>Episodes</dt>
            <dd>
              {series.seasons.reduce(
                (sum, item) => sum + item.episodes.length,
                0,
              )}
            </dd>
          </div>
        </dl>
      </section>
      <SchedulingForm kind="series" id={id} schedule={series} />
      <SeriesTerritoriesForm
        seriesId={id}
        territories={series.allowed_territories}
      />
      <div className="editor-columns">
        <section className="studio-editor-section">
          <div className="form-section-heading">
            <div>
              <p className="eyebrow">Step 2</p>
              <h2>Create a season</h2>
            </div>
          </div>
          <SeasonForm seriesId={id} nextNumber={next} />
        </section>
        <section className="studio-editor-section">
          <div className="form-section-heading">
            <div>
              <p className="eyebrow">Step 3</p>
              <h2>Create an episode</h2>
            </div>
          </div>
          {series.seasons.length ? (
            <EpisodeForm seriesId={id} seasons={series.seasons} />
          ) : (
            <p className="studio-empty-inline">
              Create a season before adding episodes.
            </p>
          )}
        </section>
      </div>
      <section className="studio-editor-section">
        <div className="form-section-heading">
          <div>
            <p className="eyebrow">Bulk flow</p>
            <h2>Ordered episode batch</h2>
          </div>
          <span>Explicit row mapping</span>
        </div>
        {series.seasons.length ? (
          <BulkEpisodeForm seriesId={id} seasons={series.seasons} />
        ) : (
          <p className="studio-empty-inline">
            A season is required for batch creation.
          </p>
        )}
      </section>
      <section className="studio-editor-section">
        <div className="form-section-heading">
          <div>
            <p className="eyebrow">Hierarchy</p>
            <h2>Season & episode order</h2>
          </div>
        </div>
        {series.seasons.map((season) => (
          <article className="season-record" key={season.id}>
            <h3>
              Season {season.number} {season.title && `· ${season.title}`}
            </h3>
            <ol>
              {season.episodes.map((episode) => (
                <li key={episode.id}>
                  <span>{episode.number.toString().padStart(2, "0")}</span>
                  <strong>{episode.title}</strong>
                  <small>{episode.status}</small>
                </li>
              ))}
            </ol>
          </article>
        ))}
      </section>
    </StudioShell>
  );
}
