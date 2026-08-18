"use client";

import { rememberClientSearch } from "@/app/lib/client-state";

export function PersistentSearchForm({ query }: { query: string }) {
  return <form role="search" onSubmit={(event) => { const data = new FormData(event.currentTarget); rememberClientSearch(String(data.get("q") ?? "")); }}>
    <label className="sr-only" htmlFor="catalog-search">Search titles, people, genres, and tags</label>
    <input id="catalog-search" name="q" defaultValue={query} placeholder="Title, person, genre, or tag" />
    <button className="primary" type="submit">Search</button>
  </form>;
}
