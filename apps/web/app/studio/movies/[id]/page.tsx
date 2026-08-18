import Link from "next/link";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { Movie, NamedRecord } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { setMovieStatusAction } from "@/app/studio/actions";
import { ArtworkForm } from "@/app/studio/components/artwork-form";
import {
  EditionTerritories,
  type EditionRights,
} from "@/app/studio/components/edition-territories";
import { MovieForm } from "@/app/studio/components/movie-form";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { SchedulingForm } from "@/app/studio/components/scheduling-form";

type Artwork = {
  id: string;
  movie_id: string | null;
  kind: string;
  storage_key: string;
  alt_text: string;
  width: number | null;
  height: number | null;
};
export default async function EditMovie({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ created?: string }>;
}) {
  const { id } = await params;
  const [{ created }, admin, movie, genres, themes, tags, artwork, editions] =
    await Promise.all([
      searchParams,
      requireAdminSession(),
      adminCatalogFetch<Movie>(`/admin/catalog/movies/${id}`),
      adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/genres"),
      adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/themes"),
      adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/tags"),
      adminCatalogFetch<Artwork[]>("/admin/catalog/artwork"),
      adminCatalogFetch<EditionRights[]>("/admin/catalog/editions"),
    ]);
  const attached = artwork.filter((item) => item.movie_id === id);
  const movieEditions = editions.filter((item) => item.movie_id === id);
  const nextStatus = movie.status === "published" ? "draft" : "published";
  return (
    <StudioShell
      admin={admin}
      active="movies"
      eyebrow="Movie editor"
      title={movie.title}
      actions={
        <div className="editor-header-actions">
          <span className={`catalog-badge ${movie.status}`}>
            {movie.status}
          </span>
          <Link
            className="studio-secondary action-link"
            href={`/studio/movies/${id}/preview`}
          >
            Preview
          </Link>
          <form action={setMovieStatusAction.bind(null, id, nextStatus)}>
            <button className="studio-primary" type="submit">
              {movie.status === "published" ? "Unpublish" : "Publish"}
            </button>
          </form>
        </div>
      }
    >
      {created && (
        <p className="studio-notice" role="status">
          Draft created in PostgreSQL. Review its metadata before publishing.
        </p>
      )}
      <MovieForm movie={movie} genres={genres} themes={themes} tags={tags} />
      <SchedulingForm kind="movies" id={id} schedule={movie} />
      <EditionTerritories editions={movieEditions} />
      <section className="studio-editor-section">
        <div className="form-section-heading">
          <div>
            <p className="eyebrow">Artwork</p>
            <h2>Visual identity</h2>
          </div>
          <span>{attached.length} references</span>
        </div>
        {attached.length > 0 && (
          <ul className="artwork-list">
            {attached.map((item) => (
              <li key={item.id}>
                <strong>{item.kind}</strong>
                <span>{item.storage_key}</span>
                <small>
                  {item.width && item.height
                    ? `${item.width} × ${item.height}`
                    : "Dimensions pending"}
                </small>
              </li>
            ))}
          </ul>
        )}
        <ArtworkForm movieId={id} />
      </section>
    </StudioShell>
  );
}
