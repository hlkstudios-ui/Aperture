"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { trackAnalytics } from "@/app/lib/analytics-client";
import { RelationshipGraph, type RelationshipGraphData } from "./relationship-graph";
import { CinephileToolkit } from "./cinephile-toolkit";
import { useDialogFocus } from "./use-dialog-focus";

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";
type Fact = { id: string; kind: string; scene_id: string | null; reveal_seconds: number; payload: Record<string, unknown> };
type Context = {
  current_scene: { id: string; ordinal: number; title: string; start_seconds: number; end_seconds: number } | null;
  safety_state: string; equality_policy: string; completion_unlock: boolean; facts: Fact[];
  bookmarks: Array<{ id: string; scene_id: string | null; timestamp_seconds: number; title: string }>;
  notes: Array<{ id: string; scene_id: string | null; timestamp_seconds: number; body: string }>;
};
type AskResult = { answer: string; intent: string; confidence: string; uncertainty: string | null; strategy: string; evidence: Array<{ kind: string; reveal_seconds: number }> };
type WhoResult = {
  characters: Array<{ character_id: string; character_name: string; actor_name: string | null; prior_appearance_seconds: number[]; summary: string }>;
  known_relationships: string[]; confidence: "supported" | "unavailable"; uncertainty: string | null;
};
type MissedResult = {
  start_seconds: number; end_seconds: number; recap: string; confidence: "supported" | "unavailable";
  uncertainty: string | null; evidence: Array<{ kind: string; reveal_seconds: number }>;
};

function at(value: number) { return `${Math.floor(value / 60)}:${Math.floor(value % 60).toString().padStart(2, "0")}`; }

export function SceneLens({ sourceId, movieId, episodeId, duration, timestamp, open, onClose, askEnabled }: { sourceId: string; movieId: string | null; episodeId: string | null; duration: number; timestamp: number; open: boolean; onClose: () => void; askEnabled: boolean }) {
  const dialogRef = useDialogFocus(open, onClose);
  const [context, setContext] = useState<Context | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("loading");
  const [askResult, setAskResult] = useState<AskResult | null>(null);
  const [asking, setAsking] = useState(false);
  const [whoResult, setWhoResult] = useState<WhoResult | null>(null);
  const [missedResult, setMissedResult] = useState<MissedResult | null>(null);
  const [momentLoading, setMomentLoading] = useState<"who" | "missed" | null>(null);
  const [graph, setGraph] = useState<RelationshipGraphData | null>(null);
  const [graphState, setGraphState] = useState<"loading" | "ready" | "error">("loading");
  const load = useCallback(async () => {
    try {
      const response = await fetch(`${apiOrigin}/scene-intelligence/sources/${sourceId}/context?timestamp=${Math.max(0, timestamp)}`, { credentials: "include" });
      if (!response.ok) throw new Error();
      setContext(await response.json() as Context); setState("idle");
    } catch { setState("error"); }
  }, [sourceId, timestamp]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    fetch(`${apiOrigin}/scene-intelligence/sources/${sourceId}/context?timestamp=${Math.max(0, timestamp)}`, { credentials: "include" })
      .then((response) => { if (!response.ok) throw new Error(); return response.json() as Promise<Context>; })
      .then((data) => { if (active) { setContext(data); setState("idle"); } })
      .catch(() => { if (active) setState("error"); });
    return () => { active = false; };
  }, [open, sourceId, timestamp]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    fetch(`${apiOrigin}/scene-intelligence/sources/${sourceId}/relationship-graph?timestamp=${Math.max(0, timestamp)}`, { credentials: "include" })
      .then((response) => { if (!response.ok) throw new Error(); return response.json() as Promise<RelationshipGraphData>; })
      .then((data) => { if (active) { setGraph(data); setGraphState("ready"); } })
      .catch(() => { if (active) setGraphState("error"); });
    return () => { active = false; };
  }, [open, sourceId, timestamp]);
  const sceneId = context?.current_scene?.id ?? null;
  const sceneFacts = useMemo(() => context?.facts.filter((fact) => !fact.scene_id || fact.scene_id === sceneId) ?? [], [context, sceneId]);
  async function create(path: "bookmarks" | "notes", payload: object) {
    const response = await fetch(`${apiOrigin}/scene-intelligence/sources/${sourceId}/${path}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (response.ok) await load();
  }
  async function remove(path: "bookmarks" | "notes", id: string) {
    const response = await fetch(`${apiOrigin}/scene-intelligence/${path}/${id}`, { method: "DELETE", credentials: "include" });
    if (response.ok) await load();
  }
  async function ask(question: string) {
    setAsking(true); setAskResult(null);
    try {
      const response = await fetch(`${apiOrigin}/scene-intelligence/sources/${sourceId}/ask`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, timestamp_seconds: timestamp, mode: "protected" }) });
      if (!response.ok) throw new Error();
      setAskResult(await response.json() as AskResult);
    } catch { setAskResult({ answer: "Ask This Movie is temporarily unavailable.", intent: "unavailable", confidence: "unavailable", uncertainty: "The request could not be completed.", strategy: "structured_templates_v1", evidence: [] }); }
    finally { setAsking(false); }
    void trackAnalytics({ event_type: "ask_movie", movie_id: movieId, episode_id: episodeId, position_seconds: timestamp, duration_seconds: duration });
  }
  async function identifyCharacters() {
    setMomentLoading("who"); setWhoResult(null);
    try {
      const response = await fetch(`${apiOrigin}/scene-intelligence/sources/${sourceId}/who-was-that?timestamp=${Math.max(0, timestamp)}`, { credentials: "include" });
      if (!response.ok) throw new Error();
      setWhoResult(await response.json() as WhoResult);
    } catch { setWhoResult({ characters: [], known_relationships: [], confidence: "unavailable", uncertainty: "Character identification could not be completed." }); }
    finally { setMomentLoading(null); }
  }
  async function recapInterval(seconds: number) {
    const end = Math.max(0, timestamp); const start = Math.max(0, end - seconds);
    setMomentLoading("missed"); setMissedResult(null);
    try {
      const response = await fetch(`${apiOrigin}/scene-intelligence/sources/${sourceId}/what-did-i-miss`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ start_seconds: start, end_seconds: end, current_timestamp: end }) });
      if (!response.ok) throw new Error();
      setMissedResult(await response.json() as MissedResult);
    } catch { setMissedResult({ start_seconds: start, end_seconds: end, recap: "What Did I Miss is temporarily unavailable.", confidence: "unavailable", uncertainty: "The watched interval could not be checked.", evidence: [] }); }
    finally { setMomentLoading(null); }
  }
  if (!open) return null;
  const summary = sceneFacts.find((fact) => fact.kind === "scene");
  const characters = sceneFacts.filter((fact) => fact.kind === "character");
  const music = sceneFacts.filter((fact) => fact.kind === "music_cue");
  const notes = sceneFacts.filter((fact) => fact.kind === "production_note");
  return <aside ref={dialogRef} className="scene-lens" role="dialog" aria-modal="true" aria-label="SceneLens" aria-live="polite">
    <header><div><p className="eyebrow">Spoiler-safe at {at(timestamp)}</p><h2>SceneLens</h2></div><button aria-label="Close SceneLens" onClick={onClose}>×</button></header>
    {state === "loading" ? <p role="status">Reading approved scene evidence…</p> : state === "error" ? <p role="alert">SceneLens is temporarily unavailable. Playback can continue.</p> : context ? <div className="scene-lens-scroll">
      <section><p className="eyebrow">Current scene</p><h3>{context.current_scene ? `#${context.current_scene.ordinal} · ${context.current_scene.title}` : "Scene metadata unavailable"}</h3><p>{summary ? String(summary.payload.summary) : "The scene summary remains hidden until its approved reveal boundary."}</p></section>
      <section><p className="eyebrow">Characters & actors</p>{characters.length ? characters.map((fact) => <article key={fact.id}><h3>{String(fact.payload.character_name)}</h3><p>{fact.payload.actor_name ? `Played by ${String(fact.payload.actor_name)}. ` : "Actor metadata unavailable. "}{String(fact.payload.summary)}</p>{Array.isArray(fact.payload.prior_appearance_seconds) && fact.payload.prior_appearance_seconds.length ? <small>Prior appearances: {fact.payload.prior_appearance_seconds.map((value) => at(Number(value))).join(", ")}</small> : <small>No earlier approved appearance.</small>}</article>) : <p>No approved character evidence is available at this moment.</p>}</section>
      <section><p className="eyebrow">Dynamic relationship graph</p><h3>What is known by {at(timestamp)}</h3>{graphState === "loading" ? <p role="status">Building the approved relationship view…</p> : graphState === "error" ? <p role="alert">The relationship graph is temporarily unavailable.</p> : graph ? <RelationshipGraph data={graph} /> : null}</section>
      <CinephileToolkit sourceId={sourceId} timestamp={timestamp} />
      {music.length ? <section><p className="eyebrow">Music</p>{music.map((fact) => <p key={fact.id}><strong>{String(fact.payload.title)}</strong>{fact.payload.composer ? ` · ${String(fact.payload.composer)}` : ""}</p>)}</section> : null}
      {notes.length ? <section><p className="eyebrow">Production & details</p>{notes.map((fact) => <article key={fact.id}><strong>{String(fact.payload.category).replaceAll("_", " ")}</strong><p>{String(fact.payload.note)}</p></article>)}</section> : null}
      <section className="moment-tools"><p className="eyebrow">Moment tools</p><h3>Catch up without looking ahead</h3><div><button disabled={momentLoading !== null} onClick={() => void identifyCharacters()}>{momentLoading === "who" ? "Checking characters…" : "Who Was That?"}</button><button disabled={momentLoading !== null || timestamp <= 0} onClick={() => void recapInterval(30)}>{momentLoading === "missed" ? "Checking interval…" : "What Did I Miss? · last 30s"}</button></div>
      {whoResult ? <article className={`ask-answer ${whoResult.confidence}`} aria-live="polite"><strong>{whoResult.confidence === "supported" ? "People in this scene" : "Not enough approved character evidence"}</strong>{whoResult.characters.map((character) => <div key={character.character_id}><h3>{character.character_name}</h3><p>{character.actor_name ? `Played by ${character.actor_name}. ` : "Actor metadata unavailable. "}{character.summary}</p><small>{character.prior_appearance_seconds.length ? `Prior appearances: ${character.prior_appearance_seconds.map(at).join(", ")}` : "No earlier approved appearance."}</small></div>)}{whoResult.known_relationships.length ? <p>Known relationships: {whoResult.known_relationships.join("; ")}.</p> : null}{whoResult.uncertainty ? <small>{whoResult.uncertainty}</small> : null}</article> : null}
      {missedResult ? <article className={`ask-answer ${missedResult.confidence}`} aria-live="polite"><strong>{missedResult.confidence === "supported" ? `Recap · ${at(missedResult.start_seconds)}–${at(missedResult.end_seconds)}` : "No completed-scene recap yet"}</strong><p>{missedResult.recap}</p>{missedResult.uncertainty ? <small>{missedResult.uncertainty}</small> : null}</article> : null}</section>
      {askEnabled ? <section className="ask-movie"><p className="eyebrow">Ask This Movie</p><h3>Ask only what the evidence can answer</h3><form onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); void ask(String(data.get("question"))); }}><label>Your question<input name="question" required minLength={2} maxLength={500} placeholder="Who is this person? What just happened?" /></label><button disabled={asking}>{asking ? "Checking evidence…" : "Ask"}</button></form>{askResult ? <article className={`ask-answer ${askResult.confidence}`} aria-live="polite"><strong>{askResult.confidence === "unavailable" ? "Not enough approved evidence" : "Evidence-grounded answer"}</strong><p>{askResult.answer}</p>{askResult.uncertainty ? <small>{askResult.uncertainty}</small> : null}{askResult.evidence.length ? <small>Supported by {askResult.evidence.map((item) => `${item.kind} at ${at(item.reveal_seconds)}`).join(", ")}.</small> : null}</article> : null}</section> : null}
      <section><p className="eyebrow">Your private memory</p><form onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); void create("bookmarks", { scene_id: sceneId, timestamp_seconds: timestamp, title: data.get("title") }); event.currentTarget.reset(); }}><label>Bookmark title<input name="title" required maxLength={180} placeholder="Name this moment" /></label><button>Bookmark scene</button></form><ul>{context.bookmarks.map((item) => <li key={item.id}><span>{item.title} · {at(item.timestamp_seconds)}</span><button aria-label={`Delete bookmark ${item.title}`} onClick={() => void remove("bookmarks", item.id)}>Delete</button></li>)}</ul>
      <form onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); void create("notes", { scene_id: sceneId, timestamp_seconds: timestamp, body: data.get("body") }); event.currentTarget.reset(); }}><label>Personal note<textarea name="body" required maxLength={5000} placeholder="Private to this profile" /></label><button>Save note</button></form><ul>{context.notes.map((item) => <li key={item.id}><span>{item.body} · {at(item.timestamp_seconds)}</span><button aria-label="Delete note" onClick={() => void remove("notes", item.id)}>Delete</button></li>)}</ul></section>
      <footer>Protected retrieval uses approved facts at or before this timestamp. Equality policy: {context.equality_policy}.</footer>
    </div> : null}
  </aside>;
}
