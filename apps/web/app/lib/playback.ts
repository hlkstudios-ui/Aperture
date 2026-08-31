import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { requireCustomerSession } from "@/app/lib/customer-session";
import { forwardedGeoHeaders } from "@/app/lib/geo-headers";
import { browserPlaybackUrl } from "@/app/lib/api-gateway";

export type PlaybackConfig = {
  source_id: string; movie_id: string | null; episode_id: string | null; edition_id: string | null;
  original_language_code: string | null;
  preferred_audio_language: string | null;
  preferred_subtitle_language: string | null;
  preferred_secondary_subtitle_language: string | null;
  subtitles_enabled: boolean;
  caption_size: "small" | "medium" | "large";
  caption_background: "transparent" | "shadow" | "solid";
  caption_position: "bottom" | "top";
  title: string; subtitle: string | null; manifest_url: string;
  duration_seconds: number;
  qualities: Array<{ height: number; width: number; bandwidth: number; state: string }>;
  audio_tracks: Array<{ index: number; codec: string; language: string; title: string | null; channels: number | null }>;
  subtitle_tracks: Array<{ index: number; codec: string; language: string; title: string | null; url: string }>;
  intro: [number, number] | null; recap: [number, number] | null;
  credits_start_seconds: number | null; next_episode_id: string | null;
  progress: { position_seconds: number; duration_seconds: number; percentage: number; completed: boolean } | null;
};

export type PlaybackUnavailable = { error: "stream_limit" | "coordination"; message: string };

export async function playbackFetch(path: string): Promise<PlaybackConfig | PlaybackUnavailable | null> {
  await requireCustomerSession();
  const store = await cookies();
  const session = store.get("aperture_session");
  if (!session) redirect("/login");
  const origin = process.env.API_ORIGIN ?? "http://localhost:8000";
  const response = await fetch(`${origin}${path}`, {
    headers: {
      cookie: `${session.name}=${session.value}`,
      ...(await forwardedGeoHeaders()),
    },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/login?error=session-expired");
  if (response.status === 404) return null;
  if (response.status === 409) return { error: "stream_limit", message: "This account is already streaming on the maximum number of devices." };
  if (response.status === 503) return { error: "coordination", message: "Playback coordination is temporarily unavailable." };
  if (!response.ok) throw new Error(`Playback configuration failed (${response.status})`);
  const config = await response.json() as PlaybackConfig;
  return {
    ...config,
    manifest_url: browserPlaybackUrl(config.manifest_url, origin),
    subtitle_tracks: config.subtitle_tracks.map((track) => ({
      ...track,
      url: browserPlaybackUrl(track.url, origin),
    })),
  };
}

export function isPlaybackUnavailable(value: PlaybackConfig | PlaybackUnavailable): value is PlaybackUnavailable {
  return "error" in value;
}
