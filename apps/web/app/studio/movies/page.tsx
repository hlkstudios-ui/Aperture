import Link from "next/link";

import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { Movie } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { setMovieStatusAction } from "@/app/studio/actions";
import { StudioShell } from "@/app/studio/components/studio-shell";

export const metadata = { title: "Movies · Studio" };

export default async function MoviesIndex() {
  const [admin, movies] = await Promise.all([requireAdminSession(), adminCatalogFetch<Movie[]>("/admin/catalog/movies")]);
  const ordered = movies.toSorted((left, right) => right.updated_at.localeCompare(left.updated_at));
  return <StudioShell admin={admin} active="movies" eyebrow="Feature catalog" title="Movies" actions={<Link className="studio-primary action-link" href="/studio/movies/new">New movie</Link>}>
    <div className="editor-intro"><p>Shape feature metadata, artwork, playback assignments, and release status from one production ledger.</p></div>
    <div className="content-table-wrap"><table className="content-table title-manager-table"><thead><tr><th>Movie</th><th>Status</th><th>Updated</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>
      {ordered.map((item) => { const base = `/studio/movies/${item.id}`; const action = setMovieStatusAction.bind(null, item.id, item.status === "published" ? "draft" : "published"); return <tr key={item.id}><td><strong>{item.title}</strong><small>/{item.slug}</small></td><td><span className={`catalog-badge ${item.status}`}>{item.status}</span></td><td>{new Date(item.updated_at).toLocaleDateString("en-CA")}</td><td><div className="row-actions"><Link href={base}>Edit</Link><Link href={`${base}/preview`}>Preview</Link><form action={action}><button type="submit">{item.status === "published" ? "Unpublish" : "Publish"}</button></form></div></td></tr>; })}
    </tbody></table>{!ordered.length && <div className="studio-empty"><h2>No movies yet</h2><p>Create the first feature and prepare it for release.</p><Link className="studio-primary action-link" href="/studio/movies/new">Create a movie</Link></div>}</div>
  </StudioShell>;
}
