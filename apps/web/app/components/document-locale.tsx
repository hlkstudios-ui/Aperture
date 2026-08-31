"use client";

import { useEffect } from "react";

const rtlLanguages = new Set(["ar", "fa", "he", "ur"]);
const localeCacheKey = "aperture:document-locale";
const localeCacheMs = 5 * 60 * 1000;

type Viewer = {
  active_profile_id: string | null;
  profiles: Array<{ id: string; language: string }>;
};

export function DocumentLocale({ defaultLocale = "en" }: { defaultLocale?: string }) {
  useEffect(() => {
    let active = true;
    const apply = (language: string) => {
      const base = language.split("-")[0].toLowerCase();
      document.documentElement.lang = language;
      document.documentElement.dir = rtlLanguages.has(base) ? "rtl" : "ltr";
    };
    try {
      const cached = JSON.parse(sessionStorage.getItem(localeCacheKey) ?? "null") as {
        language?: string; savedAt?: number;
      } | null;
      if (cached?.language && Date.now() - (cached.savedAt ?? 0) < localeCacheMs) {
        apply(cached.language);
        return () => { active = false; };
      }
    } catch { /* denied or malformed storage falls through to the API */ }
    fetch("/api/document-locale", { credentials: "same-origin" })
      .then((response) => response.ok ? response.json() as Promise<Viewer> : null)
      .then((viewer) => {
        if (!active || !viewer) return;
        const profile = viewer.profiles.find((item) => item.id === viewer.active_profile_id);
        const language = profile?.language || defaultLocale;
        apply(language);
        try {
          sessionStorage.setItem(localeCacheKey, JSON.stringify({ language, savedAt: Date.now() }));
        } catch { /* locale still applies when storage is unavailable */ }
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [defaultLocale]);
  return null;
}
