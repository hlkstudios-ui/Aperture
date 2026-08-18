import Link from "next/link";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { Movie, Series } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import {
  setMovieStatusAction,
  setSeriesStatusAction,
} from "@/app/studio/actions";
import { StudioShell } from "@/app/studio/components/studio-shell";

type ContentRow = {
  id: string;
  title: string;
  slug: string;
  status: string;
  kind: "Movie" | "Series";
  updated_at: string;
};
export const metadata = { title: "Content · Studio" };
export default async function ContentLibrary({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; type?: string; status?: string }>;
}) {
  const admin = await requireAdminSession();
  const params = await searchParams;
  const [movies, series] = await Promise.all([
    adminCatalogFetch<Movie[]>("/admin/catalog/movies"),
    adminCatalogFetch<Series[]>("/admin/catalog/series"),
  ]);
  const rows: ContentRow[] = [
    ...movies.map((item) => ({ ...item, kind: "Movie" as const })),
    ...series.map((item) => ({ ...item, kind: "Series" as const })),
  ]
    .filter(
      (item) =>
        (!params.q ||
          item.title.toLowerCase().includes(params.q.toLowerCase())) &&
        (!params.type ||
          params.type === "all" ||
          item.kind.toLowerCase() === params.type) &&
        (!params.status ||
          params.status === "all" ||
          item.status === params.status),
    )
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return (
    <StudioShell
      admin={admin}
      active="content"
      eyebrow="Catalog operations"
      title="Content library"
      actions={
        <Link className="studio-primary action-link" href="/studio/movies/new">
          New title
        </Link>
      }
    >
      <form className="library-filters">
        <label>
          Search
          <input name="q" defaultValue={params.q} placeholder="Title or slug" />
        </label>
        <label>
          Type
          <select name="type" defaultValue={params.type ?? "all"}>
            <option value="all">All types</option>
            <option value="movie">Movies</option>
            <option value="series">Series</option>
          </select>
        </label>
        <label>
          Status
          <select name="status" defaultValue={params.status ?? "all"}>
            <option value="all">All statuses</option>
            <option value="draft">Draft</option>
            <option value="ready">Ready</option>
            <option value="published">Published</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <button type="submit">Apply filters</button>
      </form>
      <div className="content-table-wrap">
        <table className="content-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Type</th>
              <th>Status</th>
              <th>Updated</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => {
              const base =
                item.kind === "Movie"
                  ? `/studio/movies/${item.id}`
                  : `/studio/series/${item.id}`;
              const statusAction =
                item.kind === "Movie"
                  ? setMovieStatusAction.bind(
                      null,
                      item.id,
                      item.status === "published" ? "draft" : "published",
                    )
                  : setSeriesStatusAction.bind(
                      null,
                      item.id,
                      item.status === "published" ? "draft" : "published",
                    );
              return (
                <tr key={`${item.kind}-${item.id}`}>
                  <td>
                    <strong>{item.title}</strong>
                    <small>/{item.slug}</small>
                  </td>
                  <td>{item.kind}</td>
                  <td>
                    <span className={`catalog-badge ${item.status}`}>
                      {item.status}
                    </span>
                  </td>
                  <td>
                    {new Date(item.updated_at).toLocaleDateString("en-CA")}
                  </td>
                  <td>
                    <div className="row-actions">
                      <Link href={base}>Edit</Link>
                      <Link href={`${base}/preview`}>Preview</Link>
                      <form action={statusAction}>
                        <button type="submit">
                          {item.status === "published"
                            ? "Unpublish"
                            : "Publish"}
                        </button>
                      </form>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!rows.length && (
          <div className="studio-empty">
            <h2>No matching content</h2>
            <p>Adjust the filters or create a new title.</p>
          </div>
        )}
      </div>
    </StudioShell>
  );
}
