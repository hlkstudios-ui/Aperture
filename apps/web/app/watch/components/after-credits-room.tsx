"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { API_GATEWAY_PREFIX } from "@/app/lib/api-gateway";
import { useDialogFocus } from "./use-dialog-focus";

type Room = {
  title: string;
  unlocked: boolean;
  completed_at: string | null;
  modules: Array<{ id: string; kind: string; title: string; body: string; source_label: string }>;
  people: Array<{ name: string; slug: string; role: string }>;
  recommended_next: Array<{ kind: string; title: string; href: string; reason: string }>;
  community_available: boolean;
};

const apiOrigin = API_GATEWAY_PREFIX;

export function AfterCreditsRoom({ sourceId, open, onClose }: { sourceId: string; open: boolean; onClose: () => void }) {
  const dialogRef = useDialogFocus(open, onClose);
  const [room, setRoom] = useState<Room | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!open) return;
    fetch(`${apiOrigin}/cinephile/sources/${sourceId}/after-credits`, { credentials: "include" })
      .then((response) => { if (!response.ok) throw new Error("room unavailable"); return response.json() as Promise<Room>; })
      .then((value) => { setRoom(value); setFailed(false); }).catch(() => setFailed(true));
  }, [open, sourceId]);
  if (!open) return null;
  return <aside ref={dialogRef} className="after-credits-room" role="dialog" aria-modal="true" aria-label="After-Credits Room" aria-live="polite">
    <header><div><p className="eyebrow">Completion unlocked</p><h2>After-Credits Room</h2></div><button onClick={onClose} aria-label="Close After-Credits Room">×</button></header>
    {failed ? <p role="alert">The room is temporarily unavailable.</p> : !room ? <p role="status">Opening the room…</p> : !room.unlocked ? <p>Finish this title to unlock sourced spoiler discussion and deeper context.</p> : <div className="after-credits-scroll">
      <p>Go deeper into <strong>{room.title}</strong>.</p>
      {room.modules.map((module) => <article key={module.id}><small>{module.kind.replaceAll("_", " ")}</small><h3>{module.title}</h3><p>{module.body}</p><footer>Source: {module.source_label}</footer></article>)}
      {!room.modules.length && <p>No licensed deeper-content module is attached yet.</p>}
      {!!room.people.length && <section><h3>Explore the filmmakers</h3>{room.people.map((person) => <Link key={`${person.slug}-${person.role}`} href={`/people/${person.slug}`}>{person.name} · {person.role}</Link>)}</section>}
      {!!room.recommended_next.length && <section><h3>Continue watching</h3>{room.recommended_next.map((item) => <Link key={item.href} href={item.href}>{item.title}<small>{item.reason}</small></Link>)}</section>}
      {!room.community_available && <small>Ratings and community discussion remain unavailable until moderation and abuse controls are enabled.</small>}
    </div>}
  </aside>;
}
