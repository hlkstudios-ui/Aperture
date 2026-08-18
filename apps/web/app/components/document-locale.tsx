"use client";

import { useEffect } from "react";

const rtlLanguages = new Set(["ar", "fa", "he", "ur"]);

type Viewer = {
  active_profile_id: string | null;
  profiles: Array<{ id: string; language: string }>;
};

export function DocumentLocale() {
  useEffect(() => {
    let active = true;
    fetch("/api/document-locale", { credentials: "same-origin" })
      .then((response) => response.ok ? response.json() as Promise<Viewer> : null)
      .then((viewer) => {
        if (!active || !viewer) return;
        const profile = viewer.profiles.find((item) => item.id === viewer.active_profile_id);
        const language = profile?.language || "en";
        const base = language.split("-")[0].toLowerCase();
        document.documentElement.lang = language;
        document.documentElement.dir = rtlLanguages.has(base) ? "rtl" : "ltr";
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);
  return null;
}
