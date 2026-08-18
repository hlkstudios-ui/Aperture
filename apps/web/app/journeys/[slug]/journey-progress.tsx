"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Journey } from "@/app/lib/curation";

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

export function JourneyProgress({ initial }: { initial: Journey }) {
  const [journey, setJourney] = useState(initial);
  const [authenticated, setAuthenticated] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  useEffect(() => {
    fetch(`${apiOrigin}/curation/journeys/${encodeURIComponent(initial.slug)}/progress`, { credentials: "include" })
      .then((response) => { if (!response.ok) throw new Error("private progress unavailable"); return response.json() as Promise<Journey>; })
      .then((value) => { setJourney(value); setAuthenticated(true); })
      .catch(() => undefined);
  }, [initial.slug]);
  const toggle = async (itemId: string, completed: boolean) => {
    setSaving(itemId);
    try {
      const response = await fetch(`${apiOrigin}/curation/journeys/${encodeURIComponent(journey.slug)}/progress`, {
        method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ journey_item_id: itemId, completed }),
      });
      if (response.ok) setJourney(await response.json() as Journey);
    } finally { setSaving(null); }
  };
  return <>
    <section className="journey-progress-summary" aria-live="polite"><strong>{journey.completed ? "Journey complete" : `${journey.completed_items} of ${journey.total_items} complete`}</strong><span>{authenticated ? "Progress is private to this profile." : "Sign in to track this journey."}</span><progress max={journey.total_items || 1} value={journey.completed_items} /></section>
    {journey.chapters.map((chapter) => <section className="journey-chapter" key={chapter.position}>
      <p className="eyebrow">Chapter {chapter.position + 1}</p><h2>{chapter.title}</h2>
      {chapter.introduction && <p className="journey-essay">{chapter.introduction}</p>}
      <ol className="curated-title-list">{chapter.items.map((item) => <li key={item.item_id} className={item.completed ? "completed" : ""}><div className="journey-title-row"><Link href={`/${item.kind === "movie" ? "movies" : "series"}/${item.slug}`}><span className="curated-order">{String(item.position + 1).padStart(2, "0")}</span><span><strong>{item.title}</strong><small>{item.note ?? item.short_description}</small></span></Link>{authenticated && <button disabled={saving === item.item_id} onClick={() => void toggle(item.item_id, !item.completed)}>{item.completed ? "Completed ✓" : "Mark complete"}</button>}</div></li>)}</ol>
    </section>)}
  </>;
}
