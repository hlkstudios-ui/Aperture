"use client";

import { useEffect, useState } from "react";
import { hasClientTitle, rememberTitle } from "@/app/lib/client-state";

export function TitleStateActions({ id, kind, title, slug, posterUrl }: { id: string; kind: "movie" | "series"; title: string; slug: string; posterUrl: string | null }) {
  const [liked, setLiked] = useState(false);
  const [saved, setSaved] = useState(false);
  const item = { id, kind, title, href: `/${kind === "movie" ? "movies" : "series"}/${slug}`, poster_url: posterUrl };
  useEffect(() => {
    const timer = window.setTimeout(() => {
      rememberTitle("viewed", item);
      setLiked(hasClientTitle("liked", id, kind));
      setSaved(hasClientTitle("saved", id, kind));
    }, 0);
    return () => window.clearTimeout(timer);
  // The title identity is stable for the lifetime of this detail page.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, kind]);
  return <div className="title-state-actions" aria-label="Personal title controls">
    <button type="button" className={liked ? "active" : ""} aria-pressed={liked} onClick={() => { const next = !liked; setLiked(next); rememberTitle("liked", item, next); }}>{liked ? "♥ Liked" : "♡ Like"}</button>
    <button type="button" className={saved ? "active" : ""} aria-pressed={saved} onClick={() => { const next = !saved; setSaved(next); rememberTitle("saved", item, next); }}>{saved ? "✓ Saved" : "＋ Save"}</button>
  </div>;
}
