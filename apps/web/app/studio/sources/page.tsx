import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { SourceForm } from "./source-form";

type Source = { id: string; movie_id: string | null; episode_id: string | null; external_format: string | null; external_manifest_url: string | null; is_active: boolean; rights_end_at: string | null; allowed_territories: string[] };
type Movie = { id: string; title: string };
type Show = { title: string; seasons: Array<{ number: number; episodes: Array<{ id: string; number: number; title: string }> }> };

function host(url: string | null) {
  if (!url) return "Aperture managed media";
  try { return new URL(url).host; } catch { return "External CDN"; }
}

export default async function MediaSourcesPage({ searchParams }: { searchParams: Promise<{ target?: string; imported?: string }> }) {
  const query = await searchParams;
  const [admin, sources, movies, series] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<Source[]>("/admin/playback/sources"),
    adminCatalogFetch<Movie[]>("/admin/catalog/movies"),
    adminCatalogFetch<Show[]>("/admin/catalog/series"),
  ]);
  const targets = [
    ...movies.map((movie) => ({ value: `movie:${movie.id}`, label: `Movie · ${movie.title}` })),
    ...series.flatMap((show) => show.seasons.flatMap((season) => season.episodes.map((episode) => ({ value: `episode:${episode.id}`, label: `${show.title} · S${season.number} E${episode.number} · ${episode.title}` })))),
  ];
  return <StudioShell admin={admin} active="media sources" eyebrow="Licensed delivery fabric" title="Media sources">
    {query.imported ? <p className="studio-notice" role="status">Movie metadata and artwork imported through Aperture Movie API. Paste the video CDN link to finish.</p> : null}
    <section className="studio-source-hero"><div><p className="eyebrow">Search → attach → verify → publish</p><h2>Connect your catalog to the screen.</h2><p>Attach an authorized CDN stream to a movie or an individual episode. Licensed metadata arrives through Aperture Movie API; playback always comes from a source you control or are licensed to distribute.</p></div><dl><div><dt>Sources</dt><dd>{sources.length}</dd></div><div><dt>Live</dt><dd>{sources.filter((source) => source.is_active).length}</dd></div><div><dt>Unlinked catalog</dt><dd>{Math.max(0, targets.length - sources.length)}</dd></div></dl></section>
    <section className="studio-source-layout"><div className="studio-panel"><p className="eyebrow">Final step</p><h2>Paste the video CDN link</h2><SourceForm targets={targets} initialTarget={query.target ?? ""} /></div><aside className="studio-panel studio-source-policy"><p className="eyebrow">Distribution guardrails</p><h2>Built for legitimate operators</h2><ol><li><strong>Metadata is not media.</strong><span>Catalog metadata identifies a title; it does not grant streaming rights.</span></li><li><strong>Playback stays private.</strong><span>Raw links never appear in public catalog payloads and require an entitled viewer session.</span></li><li><strong>Rights expire automatically.</strong><span>Dates and territories are enforced again when playback begins.</span></li><li><strong>Your CDN must allow playback.</strong><span>Configure HTTPS, CORS, byte ranges, and HLS segment access for your storefront domain.</span></li></ol></aside></section>
    <section className="studio-panel"><div className="studio-section-heading"><div><p className="eyebrow">Source registry</p><h2>Delivery inventory</h2></div><span>{sources.length} records</span></div>{sources.length ? <div className="studio-source-table">{sources.map((source) => <article key={source.id}><div><strong>{source.movie_id ? "Movie" : "Episode"}</strong><span>{host(source.external_manifest_url)}</span></div><span className={source.is_active ? "source-live" : "source-draft"}>{source.is_active ? "Live" : "Draft"}</span><span>{source.external_format?.toUpperCase() ?? "MANAGED"}</span><span>{source.allowed_territories.length ? source.allowed_territories.join(", ") : "Global"}</span></article>)}</div> : <p className="studio-empty-copy">No sources attached yet. Your first licensed stream will appear here.</p>}</section>
  </StudioShell>;
}
