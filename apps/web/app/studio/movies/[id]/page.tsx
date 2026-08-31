import Link from "next/link";
import Image from "next/image";
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
  searchParams: Promise<{ created?: string; imported?: string }>;
}) {
  const { id } = await params;
  const [{ created, imported }, admin, movie, genres, themes, tags, artwork, editions] =
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
      {(created || imported) && (
        <p className="studio-notice" role="status">
          {imported ? "TMDB metadata imported as a private draft. Confirm rights and playback before publishing." : "Draft created in PostgreSQL. Review its metadata before publishing."}
        </p>
      )}
      <div className="movie-dossier">
        <section className="movie-dossier-hero">
          {movie.backdrop_url ? <Image className="movie-dossier-backdrop" src={movie.backdrop_url} alt="" fill priority sizes="(max-width: 800px) 100vw, 80vw" /> : null}
          <div className="movie-dossier-shade" aria-hidden="true" />
          <div className="movie-dossier-poster">{movie.poster_url ? <Image src={movie.poster_url} alt={`Poster for ${movie.title}`} width={342} height={513} priority /> : <span aria-hidden="true">{movie.title.slice(0, 1)}</span>}</div>
          <div className="movie-dossier-copy">
            <p className="eyebrow">{movie.metadata_provider === "tmdb" ? `TMDB · ${movie.external_id}` : "Original catalog record"}</p>
            <h2>{movie.title}</h2>
            {movie.original_title ? <p className="movie-original-title">Originally released as {movie.original_title}</p> : null}
            <p>{movie.short_description}</p>
            <div className="movie-dossier-facts"><span>{movie.release_date?.slice(0, 4) ?? "Unscheduled"}</span><span>{movie.runtime_minutes} min</span><span>{movie.maturity_rating ?? "Not rated"}</span><span>{movie.original_language_code?.toUpperCase() ?? "Language pending"}</span></div>
          </div>
          <div className="movie-dossier-state"><small>Release readiness</small><strong>{movie.status === "published" ? "On screen" : "In preparation"}</strong><div><i className="complete" />Metadata imported</div><div><i className={movie.rights_start_at || movie.rights_end_at ? "complete" : ""} />Rights window</div><div><i className={attached.length ? "complete" : ""} />Artwork references</div><div><i className={movieEditions.length ? "complete" : ""} />Presentation edition</div><Link href="/studio/sources">Attach playback source <b aria-hidden="true">→</b></Link></div>
        </section>
        <nav className="movie-workflow" aria-label="Movie production workflow"><a href="#movie-metadata"><b>01</b><span>Metadata<small>Identity and discovery</small></span></a><a href="#movie-rights"><b>02</b><span>Rights<small>Windows and territories</small></span></a><a href="#movie-editions"><b>03</b><span>Editions<small>Presentation versions</small></span></a><a href="#movie-artwork"><b>04</b><span>Artwork<small>Visual campaign</small></span></a><Link href="/studio/sources"><b>05</b><span>Playback<small>CDN delivery source</small></span></Link></nav>
        <div id="movie-metadata"><MovieForm movie={movie} genres={genres} themes={themes} tags={tags} /></div>
        <div id="movie-rights"><SchedulingForm kind="movies" id={id} schedule={movie} /></div>
        <div id="movie-editions"><EditionTerritories editions={movieEditions} /></div>
      <section className="studio-editor-section movie-artwork-section" id="movie-artwork">
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
      </div>
    </StudioShell>
  );
}
