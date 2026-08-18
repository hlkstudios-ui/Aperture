"use client";

import { useEffect, useRef } from "react";
import { trackAnalytics } from "@/app/lib/analytics-client";

export function SearchAnalytics({ query, resultCount, enabled }: { query: string; resultCount: number; enabled: boolean }) {
  const sent = useRef(false);
  useEffect(() => {
    if (!enabled || !query || sent.current) return;
    sent.current = true;
    void trackAnalytics({ event_type: "search", query, result_count: resultCount, properties: { surface: "search_page" } });
  }, [enabled, query, resultCount]);
  return null;
}
