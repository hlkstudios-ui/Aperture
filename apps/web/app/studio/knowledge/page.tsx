import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { Movie } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import {
  createTitleRelationshipAction,
  deleteTitleRelationshipAction,
} from "@/app/studio/actions";
import { StudioShell } from "@/app/studio/components/studio-shell";

type Relationship = {
  id: string;
  source_movie_id: string;
  target_movie_id: string;
  kind: string;
  description: string | null;
  source_note: string;
  manually_verified: boolean;
};

const kinds = [
  "sequel", "prequel", "remake", "remade_as", "adaptation", "source_material",
  "influenced_by", "influenced", "companion",
];

export default async function KnowledgeStudioPage() {
  const admin = await requireAdminSession();
  const [movies, relationships] = await Promise.all([
    adminCatalogFetch<Movie[]>("/admin/catalog/movies"),
    adminCatalogFetch<Relationship[]>("/admin/catalog/title-relationships"),
  ]);
  const names = new Map(movies.map((movie) => [movie.id, movie.title]));
  return <StudioShell admin={admin} active="knowledge" eyebrow="Verified editorial facts" title="Film knowledge relationships">
    <section className="editor-card knowledge-editor"><h2>Add a directed relationship</h2>
      <p>Public graphs expose only manually verified records. Source notes remain private to Studio.</p>
      <form action={createTitleRelationshipAction} className="knowledge-form">
        <label>From movie<select name="source_movie_id" required>{movies.map((movie) => <option key={movie.id} value={movie.id}>{movie.title}</option>)}</select></label>
        <label>Relationship<select name="kind" required>{kinds.map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}</select></label>
        <label>To movie<select name="target_movie_id" required>{movies.map((movie) => <option key={movie.id} value={movie.id}>{movie.title}</option>)}</select></label>
        <label className="wide">Public context<textarea name="description" placeholder="Concise verified context for customers" /></label>
        <label className="wide">Private source note<textarea name="source_note" required placeholder="Citation, archive record, or administrator verification basis" /></label>
        <label className="check"><input type="checkbox" name="manually_verified" /> Publish as manually verified</label>
        <button className="studio-primary" type="submit">Add relationship</button>
      </form>
    </section>
    <section className="editor-card"><h2>Relationship ledger</h2>
      <div className="relationship-ledger">{relationships.map((item) => <article key={item.id}>
        <div><small>{item.manually_verified ? "Verified" : "Draft"}</small><strong>{names.get(item.source_movie_id)} · {item.kind.replaceAll("_", " ")} · {names.get(item.target_movie_id)}</strong><p>{item.description ?? "No public context."}</p><footer>Source: {item.source_note}</footer></div>
        <form action={deleteTitleRelationshipAction.bind(null, item.id)}><button type="submit">Delete</button></form>
      </article>)}</div>
      {!relationships.length && <p>No explicit title relationships are recorded.</p>}
    </section>
  </StudioShell>;
}
