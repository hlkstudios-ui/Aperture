"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Collection } from "@/app/lib/curation";

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

export function MyListButton({ movieId, authenticated }: { movieId: string; authenticated: boolean }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "saving" | "saved" | "login" | "error">("idle");
  const add = async () => {
    if (!authenticated) { router.push("/login?next=my-list"); return; }
    setState("saving");
    try {
      const response = await fetch(`${apiOrigin}/curation/my-lists`, { credentials: "include" });
      if (response.status === 401) { setState("login"); return; }
      if (!response.ok) throw new Error("list unavailable");
      const lists = await response.json() as Collection[];
      const list = lists.find((item) => item.title === "My List");
      if (list?.items.some((item) => item.kind === "movie" && item.title_id === movieId)) { setState("saved"); return; }
      const items = [...(list?.items ?? []).map((item) => item.kind === "movie" ? { movie_id: item.title_id } : { series_id: item.title_id }), { movie_id: movieId }];
      const saved = await fetch(`${apiOrigin}/curation/my-lists${list ? `/${list.id}` : ""}`, {
        method: list ? "PUT" : "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: list?.title ?? "My List", description: list?.description ?? "Titles saved for this profile.", items }),
      });
      if (!saved.ok) throw new Error("save failed");
      setState("saved");
    } catch { setState("error"); }
  };
  return <button className="secondary action-link" type="button" disabled={state === "saving" || state === "saved"} onClick={() => void add()}>{state === "saving" ? "Saving…" : state === "saved" ? "✓ In My List" : state === "login" ? "Sign in to save" : state === "error" ? "Try My List again" : "＋ My List"}</button>;
}
