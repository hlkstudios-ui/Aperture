import Link from "next/link";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { Movie, Series } from "@/app/lib/catalog";
import type { HomepageDraft } from "@/app/lib/homepage";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import {
  createRail, deleteRail, moveItem, moveRail, pinTitle, publishHomepage,
  setHero, toggleRail, unpinTitle, updateRail,
} from "./actions";

function localUtc(value: string | null) {
  return value ? value.slice(0, 16) : "";
}

export default async function HomepageManagerPage() {
  const [admin, draft, movies, series] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<HomepageDraft>("/admin/homepage"),
    adminCatalogFetch<Movie[]>("/admin/catalog/movies"),
    adminCatalogFetch<Series[]>("/admin/catalog/series"),
  ]);
  const titleOptions = [
    ...movies.map((title) => ({ key: `movie:${title.id}`, label: `Movie · ${title.title}` })),
    ...series.map((title) => ({ key: `series:${title.id}`, label: `Series · ${title.title}` })),
  ];
  const names = new Map(titleOptions.map((option) => [option.key.split(":")[1], option.label]));
  const hero = draft.hero_movie_id ? `movie:${draft.hero_movie_id}` : draft.hero_series_id ? `series:${draft.hero_series_id}` : "";
  return (
    <StudioShell admin={admin} active="homepage" eyebrow="Editorial programming" title="Homepage manager"
      actions={<div className="studio-actions"><Link className="secondary action-link" href="/studio/homepage/preview">Preview draft</Link><form action={publishHomepage}><button className="primary">Publish homepage</button></form></div>}>
      <p className="editor-intro">Compose a private draft, preview it, then publish one atomic snapshot. All scheduling fields below are entered and stored as UTC.</p>
      <section className="editor-panel homepage-editor">
        <div className="rail-heading"><div><p className="eyebrow">Featured title</p><h2>Hero</h2></div><span className="catalog-badge">{draft.published_at ? `Live · ${new Date(draft.published_at).toLocaleString()}` : "Not published"}</span></div>
        <form action={setHero} className="inline-form"><label>Hero title<select name="hero" defaultValue={hero} required><option value="">Choose a title</option>{titleOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label><button className="secondary">Set hero</button></form>
      </section>
      <section className="editor-panel homepage-editor">
        <p className="eyebrow">Layout draft</p><h2>Create rail</h2>
        <form action={createRail} className="homepage-rail-form">
          <label>Rail name<input name="title" required maxLength={120} /></label>
          <label>Eyebrow<input name="eyebrow" maxLength={80} /></label>
          <label>Source<select name="source" defaultValue="pinned"><option value="pinned">Pinned only</option><option value="latest_movies">Latest movies</option><option value="latest_series">Latest series</option><option value="mixed">Latest movies + series</option></select></label>
          <label>Optional query<input name="query" maxLength={100} /></label>
          <label>Starts at (UTC)<input type="datetime-local" name="starts_at" /></label>
          <label>Ends at (UTC)<input type="datetime-local" name="ends_at" /></label>
          <button className="primary">Create rail</button>
        </form>
      </section>
      <section className="homepage-rail-stack" aria-label="Draft homepage rails">
        {draft.rails.length === 0 ? <div className="empty-panel"><h2>No rails yet</h2><p>Create the first editorial rail above.</p></div> : draft.rails.map((rail, index) => (
          <article className="editor-panel homepage-rail-editor" key={rail.id}>
            <div className="rail-heading"><div><p className="eyebrow">Position {index + 1} · {rail.enabled ? "Enabled" : "Disabled"}</p><h2>{rail.title}</h2></div><div className="compact-actions"><form action={moveRail.bind(null, rail.id, -1)}><button disabled={index === 0} aria-label={`Move ${rail.title} up`}>↑</button></form><form action={moveRail.bind(null, rail.id, 1)}><button disabled={index === draft.rails.length - 1} aria-label={`Move ${rail.title} down`}>↓</button></form><form action={toggleRail.bind(null, rail.id, !rail.enabled)}><button>{rail.enabled ? "Disable" : "Enable"}</button></form><form action={deleteRail.bind(null, rail.id)}><button className="danger">Delete</button></form></div></div>
            <details><summary>Edit rail and schedule</summary><form action={updateRail.bind(null, rail.id)} className="homepage-rail-form"><label>Rail name<input name="title" defaultValue={rail.title} required /></label><label>Eyebrow<input name="eyebrow" defaultValue={rail.eyebrow ?? ""} /></label><label>Source<select name="source" defaultValue={rail.source}><option value="pinned">Pinned only</option><option value="latest_movies">Latest movies</option><option value="latest_series">Latest series</option><option value="mixed">Latest movies + series</option></select></label><label>Optional query<input name="query" defaultValue={rail.query ?? ""} /></label><label>Starts at (UTC)<input type="datetime-local" name="starts_at" defaultValue={localUtc(rail.starts_at)} /></label><label>Ends at (UTC)<input type="datetime-local" name="ends_at" defaultValue={localUtc(rail.ends_at)} /></label><button className="secondary">Save rail</button></form></details>
            <form action={pinTitle.bind(null, rail.id)} className="inline-form"><label>Pin title<select name="title" required defaultValue=""><option value="">Choose content</option>{titleOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label><button className="secondary">Pin</button></form>
            <ol className="homepage-items">{rail.items.map((item, itemIndex) => <li key={item.id}><span><small>#{itemIndex + 1}</small>{names.get(item.movie_id ?? item.series_id ?? "") ?? "Missing title"}</span><div className="compact-actions"><form action={moveItem.bind(null, rail.id, item.id, -1)}><button disabled={itemIndex === 0} aria-label="Move pinned title up">↑</button></form><form action={moveItem.bind(null, rail.id, item.id, 1)}><button disabled={itemIndex === rail.items.length - 1} aria-label="Move pinned title down">↓</button></form><form action={unpinTitle.bind(null, item.id)}><button>Remove</button></form></div></li>)}</ol>
          </article>
        ))}
      </section>
    </StudioShell>
  );
}
