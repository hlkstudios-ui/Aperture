"use client";

import { useActionState, useMemo, useState } from "react";
import { attachCdnSource, type SourceFormState } from "./actions";

type Target = { value: string; label: string };

export function SourceForm({ targets, initialTarget = "" }: { targets: Target[]; initialTarget?: string }) {
  const [state, action, pending] = useActionState<SourceFormState, FormData>(attachCdnSource, { error: "" });
  const [query, setQuery] = useState("");
  const visibleTargets = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    const filtered = normalized ? targets.filter((target) => target.label.toLocaleLowerCase().includes(normalized)) : targets;
    const selected = targets.find((target) => target.value === initialTarget);
    return [...new Map([...(selected ? [selected] : []), ...filtered.slice(0, 80)].map((item) => [item.value, item])).values()];
  }, [initialTarget, query, targets]);
  return <form action={action} className="studio-source-form">
    {!initialTarget ? <div className="studio-field-span"><label htmlFor="source-search">Search movies and series</label><input id="source-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Start typing a title…" /></div> : null}
    <div className="studio-field-span"><label htmlFor="source-target">Selected title</label><select id="source-target" name="target" required defaultValue={initialTarget}><option value="" disabled>Choose a catalog record</option>{visibleTargets.map((target) => <option key={target.value} value={target.value}>{target.label}</option>)}</select><small>{initialTarget ? "Selected automatically from your TMDB import." : "Choose an imported movie or episode."}</small></div>
    <div className="studio-field-span"><label htmlFor="cdn-url">Video CDN URL</label><input id="cdn-url" name="external_manifest_url" type="url" inputMode="url" placeholder="https://media.example.com/title/master.m3u8" required autoFocus={Boolean(initialTarget)} /><small>Paste an HTTPS HLS .m3u8 or MP4 link. Aperture detects the format automatically.</small></div>
    <details className="studio-field-span source-advanced"><summary>Optional availability controls</summary><div><label htmlFor="rights-start">Rights start (UTC)</label><input id="rights-start" name="rights_start_at" type="datetime-local" /></div><div><label htmlFor="rights-end">Rights end (UTC)</label><input id="rights-end" name="rights_end_at" type="datetime-local" /></div><div className="studio-field-span"><label htmlFor="source-territories">Allowed territories</label><input id="source-territories" name="allowed_territories" placeholder="CA, US, GB (blank means global)" /></div></details>
    <label className="studio-source-activation"><input name="rights_confirmed" type="checkbox" required /> I confirm that I own or am licensed to stream this video <small>This attestation is recorded in the Studio audit trail. TMDB metadata does not grant playback rights.</small></label>
    <div className="studio-field-span studio-source-submit"><button className="primary" disabled={pending} type="submit">{pending ? "Preparing playback…" : "Attach video and make playable"}</button></div>
    {state.error ? <p role="alert" className="form-error studio-field-span">{state.error}</p> : null}
    {state.success ? <p role="status" className="form-success studio-field-span">{state.success}</p> : null}
  </form>;
}
