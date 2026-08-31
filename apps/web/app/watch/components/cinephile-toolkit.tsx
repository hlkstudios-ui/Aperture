"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { API_GATEWAY_PREFIX } from "@/app/lib/api-gateway";

const apiOrigin = API_GATEWAY_PREFIX;
type Toolkit = {
  title: string; effective_cutoff: number; safety_state: string;
  stills: Array<{ id: string; alt_text: string; width: number | null; height: number | null; timestamp_seconds: number; image_url: string }>;
  music_timeline: Array<{ title: string; composer: string | null; performer: string | null; start_seconds: number; end_seconds: number }>;
  filmmaking: Array<{ category: string; note: string; reveal_seconds: number }>;
  credits: Array<{ person_id: string; person_name: string; person_slug: string; role: string; character_name: string | null; company_name: string | null }>;
  editions: Array<{ id: string; name: string; runtime_minutes: number | null; notes: string | null; is_default: boolean; available: boolean; intended_presentation: boolean; aspect_ratio: string | null; frame_rate: number | null; presentation_format: string | null; capture_format: string | null; audio_format: string | null; original_language_code: string | null; restoration_info: string | null; source_info: string | null; audio_tracks: Array<Record<string, unknown>>; subtitle_tracks: Array<Record<string, unknown>> }>;
  edition_comparison_unlocked: boolean;
  edition_comparisons: Array<{ id: string; source_edition_id: string; target_edition_id: string; kind: string; description: string; reveal_seconds: number | null }>;
  rewatch: { viewings_started: number; completed_viewings: number; rewatches_started: number; latest_completed_at: string | null; enabled: boolean; active: boolean; saved_scenes: Array<{ id: string; title: string; timestamp_seconds: number }>; personal_notes: Array<{ id: string; body: string; timestamp_seconds: number }>; spoiler_aware_insights_available: boolean };
};

function at(value: number) {
  return `${Math.floor(value / 60)}:${Math.floor(value % 60).toString().padStart(2, "0")}`;
}

export function CinephileToolkit({ sourceId, timestamp }: { sourceId: string; timestamp: number }) {
  const [data, setData] = useState<Toolkit | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    fetch(`${apiOrigin}/cinephile/sources/${sourceId}?timestamp=${Math.max(0, timestamp)}`, { credentials: "include" })
      .then((response) => { if (!response.ok) throw new Error(); return response.json() as Promise<Toolkit>; })
      .then((value) => { if (active) setData(value); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [sourceId, timestamp]);
  if (failed) return <section><p className="eyebrow">Cinephile toolkit</p><p role="alert">Deep title details are temporarily unavailable.</p></section>;
  if (!data) return <section><p className="eyebrow">Cinephile toolkit</p><p role="status">Assembling permitted title details…</p></section>;
  return <section className="cinephile-toolkit"><p className="eyebrow">Cinephile toolkit</p><h3>Explore what is known by {at(data.effective_cutoff)}</h3>
    <div><h4>Permitted still gallery</h4>{data.stills.length ? <div className="still-gallery">{data.stills.map((still) => <figure key={still.id}><Image unoptimized src={`${apiOrigin}${still.image_url}`} alt={still.alt_text} width={still.width ?? 640} height={still.height ?? 360} /><figcaption>{at(still.timestamp_seconds)} · Licensed for this private gallery</figcaption></figure>)}</div> : <p>No rights-cleared still is available at this timestamp.</p>}</div>
    <div><h4>Music timeline</h4>{data.music_timeline.length ? <ol>{data.music_timeline.map((cue) => <li key={`${cue.title}-${cue.start_seconds}`}><span><strong>{cue.title}</strong> · {at(cue.start_seconds)}–{at(cue.end_seconds)}{cue.composer ? ` · ${cue.composer}` : ""}{cue.performer ? ` · performed by ${cue.performer}` : ""}</span></li>)}</ol> : <p>No licensed music metadata is available yet.</p>}</div>
    <div><h4>Filmmaking explorer</h4>{data.filmmaking.length ? data.filmmaking.map((item) => <article key={`${item.category}-${item.reveal_seconds}`}><strong>{item.category.replaceAll("_", " ")}</strong><p>{item.note}</p><small>Known at {at(item.reveal_seconds)}</small></article>) : <p>Verified filmmaking details remain unknown.</p>}</div>
    <details><summary>Credits explorer · {data.credits.length}</summary><ul>{data.credits.map((credit) => <li key={`${credit.person_id}-${credit.role}`}><span><strong>{credit.person_name}</strong> · {credit.role}{credit.character_name ? ` as ${credit.character_name}` : ""}{credit.company_name ? ` · ${credit.company_name}` : ""}</span></li>)}</ul></details>
    <div><h4>Edition vault & original presentation</h4>{data.editions.length ? data.editions.map((edition) => <article key={edition.id} className={edition.intended_presentation ? "intended-edition" : ""}><strong>{edition.name}{edition.is_default ? " · default" : ""}{edition.intended_presentation ? " · intended presentation" : ""}</strong><p>{edition.runtime_minutes ? `${edition.runtime_minutes} minutes. ` : "Runtime unavailable. "}{edition.available ? "Available on this service. " : "Licensed media currently unavailable. "}{edition.notes ?? "No verified edition note."}</p>{edition.aspect_ratio || edition.frame_rate || edition.presentation_format ? <dl><div><dt>Aspect ratio</dt><dd>{edition.aspect_ratio ?? "Unknown"}</dd></div><div><dt>Frame rate</dt><dd>{edition.frame_rate ? `${edition.frame_rate} fps` : "Unknown"}</dd></div><div><dt>Presentation</dt><dd>{edition.presentation_format ?? "Unknown"}</dd></div><div><dt>Capture</dt><dd>{edition.capture_format ?? "Unknown"}</dd></div><div><dt>Audio</dt><dd>{edition.audio_format ?? "Unknown"}</dd></div><div><dt>Original language</dt><dd>{edition.original_language_code?.toUpperCase() ?? "Unknown"}</dd></div></dl> : null}{edition.restoration_info ? <p>Restoration: {edition.restoration_info}</p> : null}{edition.source_info ? <small>Source: {edition.source_info}</small> : null}</article>) : <p>No alternate licensed edition is attached.</p>}
    {data.edition_comparison_unlocked ? data.edition_comparisons.length ? <ul className="edition-comparison">{data.edition_comparisons.map((comparison) => <li key={comparison.id}><span><strong>{comparison.kind.replaceAll("_", " ")}</strong> · {comparison.description}</span></li>)}</ul> : <p>No verified differences are recorded.</p> : <p className="locked-comparison">Verified editorial comparisons unlock after this profile completes the title.</p>}</div>
    <div><h4>Rewatch intelligence</h4>{!data.rewatch.enabled ? <p>Turned off for this profile.</p> : <><p>{data.rewatch.viewings_started ? `${data.rewatch.completed_viewings} completed viewing(s), including ${data.rewatch.rewatches_started} rewatch(es).` : "Your viewing history for this title begins when progress is saved."}</p>{data.rewatch.active ? <><p>{data.rewatch.latest_completed_at ? `Previously completed ${new Date(data.rewatch.latest_completed_at).toLocaleDateString()}.` : "Previous completion recorded."}</p>{data.rewatch.saved_scenes.map((item) => <p key={item.id}><strong>{item.title}</strong> · saved at {at(item.timestamp_seconds)}</p>)}{data.rewatch.personal_notes.map((item) => <p key={item.id}>{item.body} <small>at {at(item.timestamp_seconds)}</small></p>)}</> : null}</>}</div>
  </section>;
}
