"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { importTmdbMovie, searchTmdbMovies, type TmdbSearchState } from "./tmdb-actions";

const initialState: TmdbSearchState = { error: "" };

export function TmdbMovieSearch({ initialQuery = "" }: { initialQuery?: string }) {
  const [state, action, pending] = useActionState(searchTmdbMovies, initialState);
  const [query, setQuery] = useState(initialQuery);
  const formRef = useRef<HTMLFormElement>(null);
  const normalizedQuery = query.trim();
  const resultsAreCurrent = state.query === normalizedQuery;
  useEffect(() => {
    if (normalizedQuery.length < 2) return;
    const timeout = window.setTimeout(() => formRef.current?.requestSubmit(), 420);
    return () => window.clearTimeout(timeout);
  }, [normalizedQuery]);
  return <section className="tmdb-importer" aria-labelledby="tmdb-import-title">
    <div className="tmdb-import-heading"><div><p className="eyebrow">Aperture Movie API</p><h2 id="tmdb-import-title">Find the film. Import the record.</h2><p>Search the licensed catalog, verify the result, then create a private Aperture draft with its metadata and artwork.</p></div><span>Metadata only</span></div>
    <form action={action} className="tmdb-search-form" role="search" ref={formRef}>
      <label htmlFor="tmdb-query">Movie title</label>
      <div><input id="tmdb-query" name="query" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Start typing a movie title…" minLength={2} required autoFocus autoComplete="off" aria-describedby="tmdb-search-help" /><button className="primary" disabled={pending || normalizedQuery.length < 2}>{pending ? "Searching…" : "Search catalog"}</button></div>
      <small id="tmdb-search-help">Results appear automatically as you type. Misspelled popular titles are corrected when possible.</small>
    </form>
    <div className="tmdb-search-feedback" aria-live="polite" aria-atomic="true">
      {pending ? <p><i aria-hidden="true" /> Searching the licensed catalog for “{normalizedQuery}”…</p> : null}
      {!pending && state.error && resultsAreCurrent ? <p className="studio-form-error" role="alert">{state.error}</p> : null}
      {!pending && state.results && resultsAreCurrent ? <div className="tmdb-search-summary"><strong>{state.results.length}</strong> results shown <span>· {state.total?.toLocaleString()} catalog matches</span></div> : null}
    </div>
    {!pending && resultsAreCurrent && state.results?.length === 0 ? <p className="studio-empty-copy">No movies matched “{state.query}”. Try the original title or release year.</p> : null}
    <div className={`tmdb-result-grid ${pending ? "is-searching" : ""}`} aria-busy={pending}>
      {(resultsAreCurrent ? state.results : undefined)?.map((movie, index) => <article key={movie.id} className="tmdb-result-card">
        <div className="tmdb-result-poster">{movie.poster_url ? <Image src={movie.poster_url} alt={`Poster for ${movie.title}`} width={342} height={513} /> : <span>No poster available</span>}<b aria-hidden="true">{String(index + 1).padStart(2, "0")}</b></div>
        <div className="tmdb-result-copy"><div className="tmdb-result-meta"><span>{movie.release_date?.slice(0,4) ?? "Year unknown"}</span><span>{(movie.original_language_code ?? "—").toUpperCase()}</span><span>Aperture</span></div><h3>{movie.title}</h3>{movie.original_title && movie.original_title !== movie.title ? <small>Original title · {movie.original_title}</small> : null}<p>{movie.short_description}</p><form action={importTmdbMovie}><input type="hidden" name="tmdb_id" value={movie.id} /><button className="secondary" type="submit"><span>Choose this film</span><b aria-hidden="true">→</b></button></form></div>
      </article>)}
    </div>
  </section>;
}
