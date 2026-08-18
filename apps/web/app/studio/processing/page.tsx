import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { ProcessingMonitor, type ProcessingJob } from "./processing-monitor";

export default async function ProcessingPage() {
  const [admin, jobs, movies, series] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<ProcessingJob[]>("/admin/processing"),
    adminCatalogFetch<Array<{ id: string; title: string }>>("/admin/catalog/movies"),
    adminCatalogFetch<Array<{ title: string; seasons: Array<{ number: number; episodes: Array<{ id: string; number: number; title: string }> }> }>>("/admin/catalog/series"),
  ]);
  return <StudioShell admin={admin} active="processing" eyebrow="Media pipeline" title="Processing queue">
    <p className="editor-intro">Source assets move through probe, rendition, packaging, derived-image, and output-validation stages. This view refreshes while work is active.</p>
    <ProcessingMonitor initialJobs={jobs} targets={[
      ...movies.map((movie) => ({ value: `movie:${movie.id}`, label: `Movie · ${movie.title}` })),
      ...series.flatMap((show) => show.seasons.flatMap((season) => season.episodes.map((episode) => ({ value: `episode:${episode.id}`, label: `${show.title} · S${season.number} E${episode.number} · ${episode.title}` })))),
    ]} />
  </StudioShell>;
}
