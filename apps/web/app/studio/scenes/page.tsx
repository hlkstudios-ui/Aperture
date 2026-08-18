import { requireAdminSession } from "@/app/lib/admin-session";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { StudioShell } from "@/app/studio/components/studio-shell";
import {
  addScene,
  addSource,
  createVersion,
  publishVersion,
  queueEnrichment,
  updateScene,
  validateVersion,
  createPermittedStill,
} from "./actions";

type Source = { id: string; kind: string; label: string; license_basis: string };
type Scene = { id: string; source_id: string; ordinal: number; title: string; summary: string; start_seconds: number; end_seconds: number; confidence: number; manually_verified: boolean };
type Detail = {
  version: { id: string; playback_source_id: string; number: number; state: string; notes: string | null };
  playback_label: string;
  duration_seconds: number;
  available_evidence: Array<{ kind: string; label: string; source_uri: string; language?: string | null }>;
  sources: Source[];
  scenes: Scene[];
  validation_errors: string[];
  jobs: Array<{ id: string; state: string; stage: string; progress_percent: number; attempts: number; error_message: string | null }>;
};
type SearchResult = { scene: Scene; version_id: string; version_state: string; playback_label: string };
type PlaybackSource = { id: string; movie_id: string | null; episode_id: string | null; processing_job_id: string };
type ProcessingJob = { id: string; playback_source_id: string | null; thumbnail_key: string | null };

export default async function SceneStudioPage({ searchParams }: { searchParams: Promise<{ message?: string; q?: string }> }) {
  const params = await searchParams;
  const [admin, versions, playbackSources, assignedSources, processingJobs, searchResults] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<Detail[]>("/admin/scenes"),
    adminCatalogFetch<Array<{ id: string; label: string; duration_seconds: number }>>("/admin/scenes/playback-sources"),
    adminCatalogFetch<PlaybackSource[]>("/admin/playback/sources"),
    adminCatalogFetch<ProcessingJob[]>("/admin/processing"),
    params.q && params.q.length >= 2 ? adminCatalogFetch<SearchResult[]>(`/admin/scenes/search?q=${encodeURIComponent(params.q)}`) : Promise.resolve([]),
  ]);
  const sourceById = new Map(assignedSources.map((source) => [source.id, source]));
  const jobBySource = new Map(processingJobs.map((job) => [job.playback_source_id, job]));
  const stillCandidates = versions.flatMap((detail) => {
    const source = sourceById.get(detail.version.playback_source_id);
    const thumbnail = jobBySource.get(detail.version.playback_source_id)?.thumbnail_key;
    if (!source?.movie_id || !thumbnail || detail.version.state !== "published") return [];
    return detail.scenes.map((scene) => ({ scene, movieId: source.movie_id!, storageKey: thumbnail, label: `${detail.playback_label} · #${scene.ordinal} ${scene.title}` }));
  });
  return <StudioShell admin={admin} active="scene data" eyebrow="Structured intelligence" title="Scene data">
    {params.message ? <p className="studio-notice">{params.message}</p> : null}
    <section className="editor-panel scene-search-panel"><p className="eyebrow">Indexed evidence</p><h2>Search ingested scenes</h2><form method="get" className="scene-search-form"><label>Scene query<input name="q" minLength={2} maxLength={100} defaultValue={params.q ?? ""} placeholder="Search dialogue, summaries, or titles" /></label><button className="secondary">Search</button></form>{params.q ? searchResults.length ? <ol className="scene-search-results">{searchResults.map((result) => <li key={result.scene.id}><strong>{result.playback_label} · {result.scene.title}</strong><span>{result.scene.start_seconds}s–{result.scene.end_seconds}s · {result.version_state}</span><p>{result.scene.summary}</p></li>)}</ol> : <p className="field-help">No indexed scene evidence matched this query.</p> : null}</section>
    <section className="editor-panel scene-foundation-intro"><p className="eyebrow">Foundation before features</p><h2>Create an immutable evidence version</h2><p>Every scene fact must retain a source, license basis, time boundary, and confidence. No chatbot or customer answer surface is enabled here.</p><form action={createVersion} className="scene-version-form"><label>Playback title<select name="playback_source_id" required defaultValue=""><option value="">Choose assigned playback</option>{playbackSources.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.duration_seconds}s</option>)}</select></label><label>Version notes<input name="notes" placeholder="Scope and review context" /></label><button className="primary">Create evidence version</button></form></section>
    <section className="editor-panel"><p className="eyebrow">Rights-controlled frame gallery</p><h2>Permit a generated still</h2><p>Select a scene from published evidence, set the exact spoiler reveal timestamp, document the legal basis, and provide accessible alt text. The protected customer gallery will not reveal it earlier.</p><form action={createPermittedStill} className="permitted-still-form"><label>Movie scene<select name="candidate" required defaultValue=""><option value="">Choose a published scene with a generated still</option>{stillCandidates.map((item) => <option key={item.scene.id} value={`${item.scene.id}|${item.movieId}|${item.storageKey}`}>{item.label}</option>)}</select></label><label>Reveal timestamp (seconds)<input name="timestamp_seconds" type="number" min="0" step="0.01" required /></label><label>Alt text<input name="alt_text" maxLength={500} required /></label><label className="wide">Rights / permission basis<textarea name="rights_basis" maxLength={5000} required /></label><button className="primary" disabled={!stillCandidates.length}>Permit still for protected gallery</button></form>{!stillCandidates.length && <p className="field-help">A published movie scene and generated processing thumbnail are required.</p>}</section>
    <div className="scene-version-stack">{versions.length ? versions.map((item) => {
      const editable = item.version.state === "draft" || item.version.state === "review";
      return <article className="editor-panel scene-version-card" key={item.version.id}>
        <header><div><p className="eyebrow">Version {item.version.number} · {item.duration_seconds}s source</p><h2>{item.playback_label}</h2><p>{item.version.notes ?? "No version note"}</p></div><span className={`catalog-badge ${item.version.state}`}>{item.version.state}</span></header>
        <div className="scene-version-actions"><form action={queueEnrichment.bind(null, item.version.id)}><button disabled={!editable || item.jobs.some((job) => ["queued", "running"].includes(job.state))}>Queue enrichment</button></form><form action={validateVersion.bind(null, item.version.id)}><button disabled={!editable}>Validate</button></form><form action={publishVersion.bind(null, item.version.id)}><button className="primary" disabled={item.version.state !== "validated"}>Publish version</button></form></div>
        {item.jobs.length ? <ul className="scene-job-list">{item.jobs.map((job) => <li key={job.id}><span className={`catalog-badge ${job.state}`}>{job.state}</span><strong>{job.stage.replaceAll("_", " ")}</strong><small>{job.progress_percent}% · attempt {job.attempts}{job.error_message ? ` · ${job.error_message}` : ""}</small></li>)}</ul> : null}
        {item.validation_errors.length ? <ul className="scene-validation-errors">{item.validation_errors.map((error) => <li key={error}>{error}</li>)}</ul> : <p className="scene-valid">Structural validation is clean.</p>}
        {editable ? <div className="scene-editor-columns"><form action={addSource.bind(null, item.version.id)} className="studio-form"><p className="eyebrow">Provenance</p><h3>Add evidence source</h3><label>Kind<select name="kind"><option value="manual">Manual</option><option value="subtitle">Subtitle</option><option value="transcript">Transcript</option><option value="chapter">Chapter</option><option value="production">Production</option><option value="external">External</option></select></label><label>Label<input name="label" required /></label><label>Source URI<input name="source_uri" list={`evidence-${item.version.id}`} /></label><datalist id={`evidence-${item.version.id}`}>{item.available_evidence.map((evidence) => <option key={evidence.source_uri} value={evidence.source_uri}>{evidence.label}{evidence.language ? ` · ${evidence.language}` : ""}</option>)}</datalist>{item.available_evidence.length ? <p className="field-help">Choose an extracted track above and document its lawful basis before enrichment.</p> : <p className="field-help">No extracted subtitle evidence is available for this playback source.</p>}<label>License basis<textarea name="license_basis" required /></label><button className="secondary">Add provenance</button></form>
          <form action={addScene.bind(null, item.version.id)} className="studio-form"><p className="eyebrow">Manual correction</p><h3>Add scene</h3><label>Evidence source<select name="source_id" required>{item.sources.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}</select></label><div className="inline-fields"><label>Ordinal<input name="ordinal" type="number" min="1" defaultValue={item.scenes.length + 1} required /></label><label>Start seconds<input name="start_seconds" type="number" min="0" step="0.01" required /></label><label>End seconds<input name="end_seconds" type="number" min="0.01" step="0.01" required /></label><label>Confidence<input name="confidence" type="number" min="0" max="1" step="0.01" defaultValue="1" required /></label></div><label>Title<input name="title" required /></label><label>Summary<textarea name="summary" required /></label><label className="check"><input name="manually_verified" type="checkbox" /> Manually verified</label><button className="secondary" disabled={!item.sources.length}>Add scene</button></form></div> : null}
        <ol className="scene-record-list">{item.scenes.map((scene) => <li key={scene.id}><div><strong>#{scene.ordinal} · {scene.title}</strong><span>{scene.start_seconds}s–{scene.end_seconds}s · {Math.round(scene.confidence * 100)}% confidence · {scene.manually_verified ? "verified" : "unverified"}</span><p>{scene.summary}</p></div>{editable ? <details><summary>Edit</summary><form action={updateScene.bind(null, item.version.id, scene.id)} className="studio-form"><div className="inline-fields"><label>Ordinal<input name="ordinal" type="number" defaultValue={scene.ordinal} /></label><label>Start<input name="start_seconds" type="number" step=".01" defaultValue={scene.start_seconds} /></label><label>End<input name="end_seconds" type="number" step=".01" defaultValue={scene.end_seconds} /></label><label>Confidence<input name="confidence" type="number" step=".01" min="0" max="1" defaultValue={scene.confidence} /></label></div><label>Title<input name="title" defaultValue={scene.title} /></label><label>Summary<textarea name="summary" defaultValue={scene.summary} /></label><label className="check"><input name="manually_verified" type="checkbox" defaultChecked={scene.manually_verified} /> Manually verified</label><button>Save correction</button></form></details> : null}</li>)}</ol>
      </article>;
    }) : <section className="empty-panel"><h2>No scene versions yet</h2><p>Create one only for a title with assigned, ready playback.</p></section>}</div>
  </StudioShell>;
}
