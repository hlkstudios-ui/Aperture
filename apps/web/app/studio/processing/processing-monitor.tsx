"use client";

import { type FormEvent, useEffect, useState } from "react";
import { API_GATEWAY_PREFIX } from "@/app/lib/api-gateway";

const apiOrigin = API_GATEWAY_PREFIX;
export type ProcessingJob = {
  id: string; asset_id: string; original_filename: string;
  state: "queued" | "probing" | "processing" | "validating" | "ready" | "failed";
  progress_percent: number; source_metadata: Record<string, string | number | null>;
  rendition_status: Array<{ height: number; width: number; state: string }>;
  audio_tracks: Array<{ codec: string; language: string; channels: number | null }>;
  subtitle_tracks: Array<{ codec: string; language: string; state: string }>;
  duration_seconds: number | null; manifest_key: string | null;
  thumbnail_key: string | null; sprite_key: string | null; error_message: string | null;
  attempts: number; updated_at: string;
  playback_source_id: string | null;
};
type Target = { value: string; label: string };

async function fetchJobs() {
  const response = await fetch(`${apiOrigin}/admin/processing`, { credentials: "include", cache: "no-store" });
  if (!response.ok) throw new Error("Processing status is unavailable");
  return response.json() as Promise<ProcessingJob[]>;
}

export function ProcessingMonitor({ initialJobs, targets }: { initialJobs: ProcessingJob[]; targets: Target[] }) {
  const [jobs, setJobs] = useState(initialJobs);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!jobs.some((job) => !["ready", "failed"].includes(job.state))) return;
    const timer = window.setInterval(() => fetchJobs().then(setJobs).catch((reason) => setError(reason.message)), 1500);
    return () => window.clearInterval(timer);
  }, [jobs]);

  async function retry(jobId: string) {
    setError("");
    const response = await fetch(`${apiOrigin}/admin/processing/${jobId}/retry`, { method: "POST", credentials: "include" });
    if (!response.ok) { const body = await response.json().catch(() => null); setError(body?.detail ?? "Retry failed"); return; }
    const retried = await response.json() as ProcessingJob;
    setJobs((current) => current.map((job) => job.id === retried.id ? retried : job));
  }

  async function assign(event: FormEvent<HTMLFormElement>, jobId: string) {
    event.preventDefault(); setError("");
    const data = new FormData(event.currentTarget);
    const [kind, id] = String(data.get("target")).split(":");
    const optional = (name: string) => data.get(name) ? Number(data.get(name)) : null;
    const response = await fetch(`${apiOrigin}/admin/playback/sources`, {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ processing_job_id: jobId, [`${kind}_id`]: id,
        intro_start_seconds: optional("intro_start"), intro_end_seconds: optional("intro_end"),
        recap_start_seconds: optional("recap_start"), recap_end_seconds: optional("recap_end"),
        credits_start_seconds: optional("credits_start") }),
    });
    if (!response.ok) { const body = await response.json().catch(() => null); setError(Array.isArray(body?.detail) ? body.detail.map((item: { msg: string }) => item.msg).join(". ") : body?.detail ?? "Assignment failed"); return; }
    const source = await response.json();
    setJobs((current) => current.map((job) => job.id === jobId ? { ...job, playback_source_id: source.id } : job));
  }

  if (jobs.length === 0) return <section className="studio-empty studio-editor-section"><h2>The queue is clear.</h2><p>Complete a source upload, then queue it for processing from Uploads.</p></section>;
  return <div className="processing-list" aria-live="polite">
    {error && <p className="studio-form-error" role="alert">{error}</p>}
    {jobs.map((job) => <article className="processing-card" key={job.id}>
      <header><div><p className="eyebrow">Attempt {job.attempts || 1}</p><h2>{job.original_filename}</h2></div><span className={`catalog-badge ${job.state}`}>{job.state}</span></header>
      <div className="processing-meter"><div><span>{job.state === "ready" ? "Pipeline complete" : job.state === "failed" ? "Pipeline stopped" : `Stage: ${job.state}`}</span><strong>{job.progress_percent}%</strong></div><progress max="100" value={job.progress_percent} /></div>
      {job.error_message && <div className="processing-error"><strong>Processing error</strong><p>{job.error_message}</p><button className="studio-secondary" type="button" onClick={() => retry(job.id)}>Retry job</button></div>}
      {Object.keys(job.source_metadata).length > 0 && <dl className="processing-metadata"><div><dt>Source</dt><dd>{job.source_metadata.width}×{job.source_metadata.height} · {job.source_metadata.video_codec}</dd></div><div><dt>Duration</dt><dd>{job.duration_seconds?.toFixed(2)} seconds</dd></div><div><dt>Audio</dt><dd>{job.audio_tracks.length ? job.audio_tracks.map((track) => `${track.language} ${track.codec}`).join(", ") : "No audio"}</dd></div><div><dt>Subtitles</dt><dd>{job.subtitle_tracks.length || "None supplied"}</dd></div></dl>}
      {job.rendition_status.length > 0 && <div className="rendition-row">{job.rendition_status.map((item) => <span key={item.height}><strong>{item.height}p</strong><small>{item.state}</small></span>)}</div>}
      {job.state === "ready" && <div className="output-summary"><span>Adaptive manifest validated</span><code>{job.manifest_key}</code><small>Thumbnail and preview sprite ready</small></div>}
      {job.state === "ready" && (job.playback_source_id ? <p className="assignment-ready">Assigned for customer playback</p> : <form className="assignment-form" onSubmit={(event) => assign(event, job.id)}><label>Playback title<select name="target" required defaultValue=""><option value="" disabled>Select a movie or episode</option>{targets.map((target) => <option key={target.value} value={target.value}>{target.label}</option>)}</select></label><div><label>Intro start<input name="intro_start" type="number" min="0" step="0.1" /></label><label>Intro end<input name="intro_end" type="number" min="0" step="0.1" /></label><label>Recap start<input name="recap_start" type="number" min="0" step="0.1" /></label><label>Recap end<input name="recap_end" type="number" min="0" step="0.1" /></label><label>Credits start<input name="credits_start" type="number" min="0" step="0.1" /></label></div><button className="studio-primary" type="submit">Assign playback</button></form>)}
    </article>)}
  </div>;
}
