"use client";

import Link from "next/link";
import { FormEvent, useRef, useState } from "react";

import type { Movie, NamedRecord } from "@/app/lib/catalog";

type Dimension = { dimension: string; status: "matched" | "neutral" | "unavailable"; explanation: string };
type Result = {
  movie: Movie;
  taste_match_score: number;
  reason: string;
  constraints_satisfied: boolean;
  match_dimensions: Dimension[];
};

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

export function PrescriptionLab({ genres }: { genres: NamedRecord[] }) {
  const [result, setResult] = useState<Result | null>(null);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  async function run(form: HTMLFormElement, excludedIds: string[]) {
    setLoading(true);
    setError("");
    const data = new FormData(form);
    const value = (key: string) => String(data.get(key) ?? "").trim();
    const payload = {
      time_available_minutes: value("time") ? Number(value("time")) : null,
      mood: value("mood") || null,
      pacing: value("pacing") || null,
      intensity: value("intensity") || null,
      preferred_genre_slugs: data.getAll("preferred_genres"),
      unwanted_genre_slugs: data.getAll("unwanted_genres"),
      unwanted_characteristics: value("unwanted")
        .split(",")
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
      language: value("language") || null,
      release_era_start: value("era_start") ? Number(value("era_start")) : null,
      release_era_end: value("era_end") ? Number(value("era_end")) : null,
      watch_state: value("watch_state") || "unwatched",
      exclude_movie_ids: excludedIds,
    };
    const response = await fetch(`${apiOrigin}/recommendations/movie-prescription`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = (await response.json().catch(() => null)) as Result | { detail?: string } | null;
    if (!response.ok || !body || !("movie" in body)) {
      setError((body && "detail" in body && body.detail) || "No movie could satisfy that prescription.");
      setLoading(false);
      return;
    }
    setResult(body);
    setLoading(false);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run(event.currentTarget, excluded);
  }

  function another() {
    if (!result || !formRef.current) return;
    const nextExcluded = [...excluded, result.movie.id];
    setExcluded(nextExcluded);
    void run(formRef.current, nextExcluded);
  }

  return (
    <div className="prescription-workspace">
      <form className="prescription-form" onSubmit={submit} ref={formRef}>
        <div className="prescription-fields">
          <label>Time available (minutes)<input name="time" type="number" min="20" max="600" placeholder="120" /></label>
          <label>Mood<select name="mood"><option value="">Any mood</option><option>uplifting</option><option>dark</option><option>comforting</option><option>tense</option><option>reflective</option><option>adventurous</option></select></label>
          <label>Pacing<select name="pacing"><option value="">Any pace</option><option>slow</option><option>balanced</option><option>fast</option></select></label>
          <label>Intensity<select name="intensity"><option value="">Any intensity</option><option>gentle</option><option>moderate</option><option>intense</option></select></label>
          <label>Preferred genres<select name="preferred_genres" multiple>{genres.map((genre) => <option value={genre.slug} key={genre.id}>{genre.name}</option>)}</select></label>
          <label>Genres to avoid<select name="unwanted_genres" multiple>{genres.map((genre) => <option value={genre.slug} key={genre.id}>{genre.name}</option>)}</select></label>
          <label>Characteristics to avoid<input name="unwanted" placeholder="gore, bleak" /></label>
          <label>Original language<input name="language" placeholder="en" maxLength={16} /></label>
          <label>Release era starts<input name="era_start" type="number" min="1880" max="2100" placeholder="1990" /></label>
          <label>Release era ends<input name="era_end" type="number" min="1880" max="2100" placeholder="2026" /></label>
          <label>Viewing history<select name="watch_state" defaultValue="unwatched"><option value="unwatched">A new watch</option><option value="watched">A rewatch</option><option value="either">Either</option></select></label>
        </div>
        <p className="form-hint">Use Command/Ctrl to select more than one genre. Unspecified dimensions remain neutral rather than being guessed.</p>
        <button className="primary" disabled={loading}>{loading ? "Finding one fit…" : "Prescribe one movie"}</button>
        {error ? <p className="prescription-error" role="alert">{error}</p> : null}
      </form>
      {result ? <section className="prescription-result" aria-live="polite">
        <p className="eyebrow">One best fit · {result.taste_match_score}% match</p>
        <h2>{result.movie.title}</h2>
        <p>{result.reason}</p>
        <div className="prescription-actions"><Link className="primary action-link" href={`/movies/${result.movie.slug}`}>View &amp; play</Link><button className="secondary" type="button" onClick={another} disabled={loading}>{loading ? "Finding another…" : "Another recommendation"}</button></div>
        <dl>{result.match_dimensions.map((item) => <div key={item.dimension}><dt>{item.dimension.replace("_", " ")}<span className={`match-state ${item.status}`}>{item.status}</span></dt><dd>{item.explanation}</dd></div>)}</dl>
      </section> : <section className="prescription-empty"><p className="eyebrow">One perfect movie</p><h2>Set the boundaries that matter tonight.</h2><p>The result will distinguish matched catalog evidence from dimensions the metadata cannot establish.</p></section>}
    </div>
  );
}
