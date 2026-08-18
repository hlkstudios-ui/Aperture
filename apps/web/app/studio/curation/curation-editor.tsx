"use client";

import { useState, useTransition } from "react";
import {
  CollectionDraft,
  JourneyDraft,
  saveCollectionAction,
  saveJourneyAction,
} from "./actions";

type MovieOption = { id: string; title: string };
type CollectionRecord = CollectionDraft & { id: string };
type JourneyRecord = JourneyDraft & { id: string };
const collectionKinds = ["editorial", "franchise", "award", "director", "actor", "country", "decade", "genre", "movement", "seasonal", "themed"];

function OrderedMovies({ movies, ids, onChange }: { movies: MovieOption[]; ids: string[]; onChange: (ids: string[]) => void }) {
  const unused = movies.filter((movie) => !ids.includes(movie.id));
  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    const next = [...ids]; [next[index], next[target]] = [next[target], next[index]]; onChange(next);
  };
  return <div className="ordered-editor"><div className="ordered-add"><select defaultValue="" onChange={(event) => { if (event.target.value) onChange([...ids, event.target.value]); event.target.value = ""; }}><option value="">Add a movie…</option>{unused.map((movie) => <option key={movie.id} value={movie.id}>{movie.title}</option>)}</select></div>
    <ol>{ids.map((id, index) => <li key={id}><span>{movies.find((movie) => movie.id === id)?.title ?? "Unavailable title"}</span><div><button type="button" aria-label="Move up" onClick={() => move(index, -1)}>↑</button><button type="button" aria-label="Move down" onClick={() => move(index, 1)}>↓</button><button type="button" onClick={() => onChange(ids.filter((value) => value !== id))}>Remove</button></div></li>)}</ol></div>;
}

export function CurationEditor({ movies, initialCollections, initialJourneys }: { movies: MovieOption[]; initialCollections: CollectionRecord[]; initialJourneys: JourneyRecord[] }) {
  const blankCollection: CollectionDraft = { slug: "", title: "", description: "", kind: "editorial", status: "draft", movieIds: [] };
  const blankJourney: JourneyDraft = { slug: "", title: "", description: "", status: "draft", chapters: [{ title: "Chapter 1", introduction: "", movieIds: [] }] };
  const [collection, setCollection] = useState<CollectionDraft>(blankCollection);
  const [journey, setJourney] = useState<JourneyDraft>(blankJourney);
  const [message, setMessage] = useState("");
  const [pending, startTransition] = useTransition();
  const save = (kind: "collection" | "journey") => startTransition(async () => {
    setMessage("");
    try { if (kind === "collection") await saveCollectionAction(collection); else await saveJourneyAction(journey); setMessage(`${kind === "collection" ? "Collection" : "Journey"} saved.`); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Save failed."); }
  });
  const updateChapter = (index: number, patch: Partial<JourneyDraft["chapters"][number]>) => setJourney((current) => ({ ...current, chapters: current.chapters.map((chapter, chapterIndex) => chapterIndex === index ? { ...chapter, ...patch } : chapter) }));
  const moveChapter = (index: number, delta: number) => setJourney((current) => { const target = index + delta; if (target < 0 || target >= current.chapters.length) return current; const chapters = [...current.chapters]; [chapters[index], chapters[target]] = [chapters[target], chapters[index]]; return { ...current, chapters }; });
  return <div className="curation-studio-grid">
    <section className="editor-card"><h2>Collection editor</h2><label>Edit existing<select value={collection.id ?? ""} onChange={(event) => setCollection(initialCollections.find((item) => item.id === event.target.value) ?? blankCollection)}><option value="">New collection</option>{initialCollections.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
      <div className="curation-fields"><label>Title<input value={collection.title} onChange={(event) => setCollection({ ...collection, title: event.target.value })} /></label><label>Slug<input value={collection.slug} onChange={(event) => setCollection({ ...collection, slug: event.target.value })} /></label><label>Kind<select value={collection.kind} onChange={(event) => setCollection({ ...collection, kind: event.target.value })}>{collectionKinds.map((kind) => <option key={kind}>{kind}</option>)}</select></label><label>Status<select value={collection.status} onChange={(event) => setCollection({ ...collection, status: event.target.value })}><option>draft</option><option>published</option><option>archived</option></select></label><label className="wide">Description<textarea value={collection.description} onChange={(event) => setCollection({ ...collection, description: event.target.value })} /></label></div>
      <OrderedMovies movies={movies} ids={collection.movieIds} onChange={(movieIds) => setCollection({ ...collection, movieIds })} /><button className="studio-primary" disabled={pending || !collection.title || !collection.slug} onClick={() => save("collection")}>Save collection and order</button>
    </section>
    <section className="editor-card"><h2>Film Journey editor</h2><label>Edit existing<select value={journey.id ?? ""} onChange={(event) => setJourney(initialJourneys.find((item) => item.id === event.target.value) ?? blankJourney)}><option value="">New journey</option>{initialJourneys.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
      <div className="curation-fields"><label>Title<input value={journey.title} onChange={(event) => setJourney({ ...journey, title: event.target.value })} /></label><label>Slug<input value={journey.slug} onChange={(event) => setJourney({ ...journey, slug: event.target.value })} /></label><label>Status<select value={journey.status} onChange={(event) => setJourney({ ...journey, status: event.target.value })}><option>draft</option><option>published</option><option>archived</option></select></label><label className="wide">Description<textarea value={journey.description} onChange={(event) => setJourney({ ...journey, description: event.target.value })} /></label></div>
      {journey.chapters.map((chapter, index) => <article className="chapter-editor" key={index}><header><strong>Chapter {index + 1}</strong><div><button onClick={() => moveChapter(index, -1)}>↑</button><button onClick={() => moveChapter(index, 1)}>↓</button><button onClick={() => setJourney({ ...journey, chapters: journey.chapters.filter((_, itemIndex) => itemIndex !== index) })}>Remove</button></div></header><label>Chapter title<input value={chapter.title} onChange={(event) => updateChapter(index, { title: event.target.value })} /></label><label>Essay / introduction<textarea value={chapter.introduction} onChange={(event) => updateChapter(index, { introduction: event.target.value })} /></label><OrderedMovies movies={movies} ids={chapter.movieIds} onChange={(movieIds) => updateChapter(index, { movieIds })} /></article>)}
      <button type="button" onClick={() => setJourney({ ...journey, chapters: [...journey.chapters, { title: `Chapter ${journey.chapters.length + 1}`, introduction: "", movieIds: [] }] })}>Add chapter</button> <button className="studio-primary" disabled={pending || !journey.title || !journey.slug || !journey.chapters.length} onClick={() => save("journey")}>Save journey and order</button>
    </section>{message && <p className="curation-message" role="status">{message}</p>}
  </div>;
}
