import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { ResponsivePoster } from "@/app/components/responsive-poster";
import type { ExploreCardTitle, ExploreCriteria, ExploreEntry } from "@/app/lib/explore";
import { requireAdminSession } from "@/app/lib/admin-session";
import type { Movie, Series } from "@/app/lib/catalog";
import { StudioShell } from "@/app/studio/components/studio-shell";
import {
  attachExploreCard,
  createExploreEntry,
  deleteExploreEntry,
  moveExploreCard,
  moveExploreEntry,
  removeExploreCard,
  toggleExploreEntry,
  updateExploreEntry,
} from "./actions";
import { ExploreCardPicker, type ExploreTitleOption } from "./explore-card-picker";

const BUILT_IN_EXPLORE = [
  { icon: "↗", label: "Trending", detail: "Live seven-day movie and series momentum." },
  { icon: "↺", label: "Recent Searches", detail: "Private searches stored in the current browser." },
  { icon: "●", label: "Ongoing", detail: "Series that are currently airing." },
] as const;

function criteriaSummary(criteria: ExploreCriteria) {
  return [
    criteria.content_type !== "all" ? criteria.content_type : null,
    criteria.genre,
    criteria.studio,
    criteria.country_code,
    criteria.original_language_code?.toUpperCase(),
    criteria.maturity_rating,
    criteria.release_period !== "all" ? criteria.release_period : null,
    criteria.duration !== "all" ? criteria.duration : null,
    criteria.airing !== "all" ? criteria.airing : null,
    criteria.query ? `“${criteria.query}”` : null,
  ].filter(Boolean).join(" · ") || "All catalog titles";
}

function cardFacts(title: ExploreCardTitle) {
  const length = title.kind === "series"
    ? title.episode_count > 0
      ? `${title.episode_count} ${title.episode_count === 1 ? "episode" : "episodes"}`
      : title.season_count > 0
        ? `${title.season_count} ${title.season_count === 1 ? "season" : "seasons"}`
        : title.is_ongoing
          ? "Ongoing"
          : null
    : title.duration_minutes
      ? `${title.duration_minutes} min`
      : null;
  return [
    title.release_date?.slice(0, 4) ?? "TBA",
    title.maturity_rating,
    title.country_code,
    length,
  ].filter((fact): fact is string => Boolean(fact));
}

function CriteriaFields({ criteria }: { criteria?: ExploreCriteria }) {
  return <>
    <label>Content type<select name="content_type" defaultValue={criteria?.content_type ?? "all"}><option value="all">Movies + series</option><option value="movie">Movies</option><option value="series">Series</option><option value="ova">OVA</option></select></label>
    <label>Search phrase<input name="query" maxLength={100} defaultValue={criteria?.query ?? ""} placeholder="Optional title or summary text" /></label>
    <label>Genre<input name="genre" maxLength={100} defaultValue={criteria?.genre ?? ""} placeholder="Animation" /></label>
    <label>Studio<input name="studio" maxLength={120} defaultValue={criteria?.studio ?? ""} placeholder="Optional exact studio" /></label>
    <label>Country code<input name="country_code" minLength={2} maxLength={2} defaultValue={criteria?.country_code ?? ""} placeholder="JP" /></label>
    <label>Language code<input name="original_language_code" minLength={2} maxLength={10} defaultValue={criteria?.original_language_code ?? ""} placeholder="ja" /></label>
    <label>Maturity rating<input name="maturity_rating" maxLength={32} defaultValue={criteria?.maturity_rating ?? ""} placeholder="TV-14" /></label>
    <label>Release period<select name="release_period" defaultValue={criteria?.release_period ?? "all"}><option value="all">Any release</option><option value="2020s">2020s</option><option value="2010s">2010s</option><option value="classic">Before 2010</option></select></label>
    <label>Duration<select name="duration" defaultValue={criteria?.duration ?? "all"}><option value="all">Any duration</option><option value="short">Under 30m</option><option value="standard">30–90m</option><option value="long">Over 90m</option></select></label>
    <label>Airing state<select name="airing" defaultValue={criteria?.airing ?? "all"}><option value="all">Any state</option><option value="ongoing">Ongoing</option><option value="finished">Completed</option></select></label>
  </>;
}

export default async function ExploreManagerPage() {
  const [admin, entries, movies, series] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<ExploreEntry[]>("/admin/explore"),
    adminCatalogFetch<Movie[]>("/admin/catalog/movies"),
    adminCatalogFetch<Series[]>("/admin/catalog/series"),
  ]);
  const titleOptions: ExploreTitleOption[] = [
    ...movies.map((title) => ({
      value: `movie:${title.id}`,
      label: `Movie - ${title.title} - ${title.release_date?.slice(0, 4) ?? "TBA"} - ${title.status}`,
    })),
    ...series.map((title) => ({
      value: `series:${title.id}`,
      label: `Series - ${title.title} - ${title.release_date?.slice(0, 4) ?? "TBA"} - ${title.status}`,
    })),
  ].sort((left, right) => left.label.localeCompare(right.label));
  return <StudioShell admin={admin} active="explore" eyebrow="Storefront discovery" title="Explore manager">
    <p className="editor-intro">Add reusable catalog filters to the Explore menu. Every built-in and Studio-created view automatically inherits the same contained scroll and soft blurred boundary.</p>
    <section className="editor-panel explore-built-ins">
      <div className="rail-heading"><div><p className="eyebrow">Always available</p><h2>Built-in experiences</h2></div><span className="catalog-badge">Universal blur enabled</span></div>
      <div className="explore-built-in-grid">{BUILT_IN_EXPLORE.map((entry) => <article key={entry.label}><span aria-hidden="true">{entry.icon}</span><div><strong>{entry.label}</strong><p>{entry.detail}</p></div></article>)}</div>
    </section>
    <section className="editor-panel homepage-editor">
      <p className="eyebrow">New storefront view</p><h2>Add Explore filter</h2>
      <form action={createExploreEntry} className="homepage-rail-form explore-entry-form">
        <label>Menu label<input name="label" required maxLength={64} placeholder="Anime premieres" /></label>
        <label>Short description<input name="description" maxLength={180} placeholder="Fresh animation arriving this season." /></label>
        <label>Icon<input name="icon" maxLength={16} defaultValue="↗" /></label>
        <CriteriaFields />
        <button className="primary">Add to Explore</button>
      </form>
    </section>
    <section className="homepage-rail-stack" aria-label="Configured Explore filters">
      {entries.length === 0 ? <div className="empty-panel"><h2>No custom filters yet</h2><p>Create one above and it will appear in the public Explore menu immediately.</p></div> : entries.map((entry, index) => {
        const cards = [...(entry.cards ?? [])].sort((left, right) => left.position - right.position);
        const pinnedKeys = new Set(cards.map((card) => card.movie_id ? `movie:${card.movie_id}` : `series:${card.series_id}`));
        const availableOptions = titleOptions.filter((option) => !pinnedKeys.has(option.value));
        const cardsHeadingId = `explore-cards-${entry.id}`;
        return <article className="editor-panel homepage-rail-editor explore-entry-editor" key={entry.id}>
          <div className="rail-heading">
            <div><p className="eyebrow">Position {index + 1} · {entry.enabled ? "Visible" : "Hidden"}</p><h2><span aria-hidden="true">{entry.icon}</span> {entry.label}</h2><p>{entry.description || "No description"}</p><small>{criteriaSummary(entry.criteria)}</small></div>
            <div className="compact-actions"><form action={moveExploreEntry.bind(null, entry.id, -1)}><button disabled={index === 0} aria-label={`Move ${entry.label} up`}>↑</button></form><form action={moveExploreEntry.bind(null, entry.id, 1)}><button disabled={index === entries.length - 1} aria-label={`Move ${entry.label} down`}>↓</button></form><form action={toggleExploreEntry.bind(null, entry.id, !entry.enabled)}><button>{entry.enabled ? "Hide" : "Show"}</button></form><form action={deleteExploreEntry.bind(null, entry.id)}><button className="danger">Delete</button></form></div>
          </div>
          <details><summary>Edit filter</summary><form action={updateExploreEntry.bind(null, entry.id)} className="homepage-rail-form explore-entry-form"><label>Menu label<input name="label" required maxLength={64} defaultValue={entry.label} /></label><label>Short description<input name="description" maxLength={180} defaultValue={entry.description} /></label><label>Icon<input name="icon" maxLength={16} defaultValue={entry.icon} /></label><CriteriaFields criteria={entry.criteria} /><button className="secondary">Save filter</button></form></details>
          <section className="explore-card-manager" aria-labelledby={cardsHeadingId}>
            <div className="explore-card-manager-heading">
              <div><p className="eyebrow">Editorial lead cards</p><h3 id={cardsHeadingId}>Pinned cards</h3></div>
              <span className="catalog-badge">{cards.length} pinned</span>
            </div>
            <p className="explore-card-help">These cards appear first in this exact order. The saved criteria above then fills the rest of the feed automatically, skipping titles already pinned here.</p>
            <ExploreCardPicker
              key={`${entry.id}:${cards.length}`}
              options={availableOptions}
              attachAction={attachExploreCard.bind(null, entry.id)}
            />
            {cards.length ? <ol className="explore-pinned-cards">{cards.map((card, cardIndex) => {
              const title = card.title;
              const facts = cardFacts(title);
              return <li className="explore-pinned-card" key={card.id}>
                <div className="explore-pinned-card-preview">
                  <div className={`explore-pinned-card-art ${title.poster_url ? "" : "missing"}`}>
                    {title.poster_url ? <ResponsivePoster src={title.poster_url} sizes="(max-width: 620px) 72px, 96px" alt={`${title.title} poster`} /> : <span aria-hidden="true">{title.title.slice(0, 1).toUpperCase()}</span>}
                    <b aria-hidden="true">{String(cardIndex + 1).padStart(2, "0")}</b>
                  </div>
                  <div className="explore-pinned-card-copy">
                    <small className="explore-pinned-card-kicker">{title.kind === "movie" ? "Movie" : "Series"} · Pinned first</small>
                    <strong>{title.title}</strong>
                    <p>{title.short_description || "No catalog summary is available yet."}</p>
                    <div className="explore-pinned-card-meta">{facts.map((fact) => <span key={fact}>{fact}</span>)}{title.genres.length ? <span>{title.genres.slice(0, 2).join(" · ")}</span> : null}</div>
                  </div>
                </div>
                <div className="compact-actions explore-pinned-card-actions">
                  <form action={moveExploreCard.bind(null, entry.id, card.id, -1)}><button disabled={cardIndex === 0} aria-label={`Move ${title.title} up`}>↑</button></form>
                  <form action={moveExploreCard.bind(null, entry.id, card.id, 1)}><button disabled={cardIndex === cards.length - 1} aria-label={`Move ${title.title} down`}>↓</button></form>
                  <form action={removeExploreCard.bind(null, card.id)}><button aria-label={`Remove ${title.title} from ${entry.label}`}>Remove</button></form>
                </div>
              </li>;
            })}</ol> : <p className="studio-empty-inline">No pinned cards yet. Criteria matches will fill the view until you add an editorial lead card.</p>}
          </section>
        </article>;
      })}
    </section>
  </StudioShell>;
}
