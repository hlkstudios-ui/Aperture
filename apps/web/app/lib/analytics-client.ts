"use client";

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";
export type AnalyticsEventName = "impression" | "detail_open" | "play_start" | "progress" | "pause" | "seek" | "completion" | "search" | "search_click" | "my_list" | "rating" | "scenelens_open" | "ask_movie" | "playback_startup" | "playback_buffer" | "playback_error" | "quality_change";

export async function trackAnalytics(event: {
  event_type: AnalyticsEventName;
  movie_id?: string | null;
  episode_id?: string | null;
  position_seconds?: number;
  duration_seconds?: number;
  query?: string;
  result_count?: number;
  value?: number;
  properties?: Record<string, unknown>;
}) {
  try {
    await fetch(`${apiOrigin}/analytics/events`, {
      method: "POST", credentials: "include", keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: [{ ...event, client_event_id: crypto.randomUUID(), occurred_at: new Date().toISOString() }] }),
    });
  } catch {
    // Analytics must never break the customer journey.
  }
}
