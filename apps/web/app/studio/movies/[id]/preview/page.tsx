import Link from "next/link";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { Movie } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
export default async function MoviePreview({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [admin, movie] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<Movie>(`/admin/catalog/movies/${id}`),
  ]);
  return (
    <StudioShell
      admin={admin}
      active="movies"
      eyebrow="Private catalog preview"
      title={movie.title}
      actions={
        <Link
          className="studio-secondary action-link"
          href={`/studio/movies/${id}`}
        >
          Back to editor
        </Link>
      }
    >
      <article className="studio-preview">
        <div className="preview-art" aria-hidden="true">
          {movie.title[0]}
        </div>
        <div>
          <span className={`catalog-badge ${movie.status}`}>
            {movie.status}
          </span>
          <p className="eyebrow">
            {movie.genres.map((item) => item.name).join(" · ") ||
              "Unclassified"}
          </p>
          <h2>{movie.title}</h2>
          <p className="preview-short">{movie.short_description}</p>
          <p>{movie.synopsis}</p>
          <dl>
            <div>
              <dt>Runtime</dt>
              <dd>{movie.runtime_minutes} minutes</dd>
            </div>
            <div>
              <dt>Certification</dt>
              <dd>{movie.maturity_rating || "Not set"}</dd>
            </div>
            <div>
              <dt>Public visibility</dt>
              <dd>
                {movie.status === "published"
                  ? "Visible in customer catalog"
                  : "Private to Studio"}
              </dd>
            </div>
          </dl>
        </div>
      </article>
    </StudioShell>
  );
}
