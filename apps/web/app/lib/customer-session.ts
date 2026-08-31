import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

export type ViewerProfile = {
  id: string;
  name: string;
  avatar_key: string | null;
  maturity_level: "kids" | "teen" | "adult";
  language: string;
  is_kids: boolean;
  preference: {
    autoplay_next: boolean;
    autoplay_previews: boolean;
    preferred_audio_language: string | null;
    preferred_subtitle_language: string | null;
    preferred_secondary_subtitle_language: string | null;
    subtitles_enabled: boolean;
    timezone: string;
    caption_size: "small" | "medium" | "large";
    caption_background: "transparent" | "shadow" | "solid";
    caption_position: "bottom" | "top";
    cinephile_mode: boolean;
    rewatch_intelligence_enabled: boolean;
    analytics_enabled: boolean;
    consent_updated_at: string | null;
    homepage_mode: "curated" | "no_algorithm";
  };
};

export type ViewerAccount = {
  id: string;
  email: string;
  profiles: ViewerProfile[];
  active_profile_id: string | null;
};

export const requireCustomerSession = cache(async (): Promise<ViewerAccount> => {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("aperture_session");
  if (!sessionCookie) redirect("/login");
  const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";
  let response: Response;
  try {
    response = await fetch(`${apiOrigin}/auth/me`, {
      headers: { cookie: `${sessionCookie.name}=${sessionCookie.value}` },
      cache: "no-store",
    });
  } catch {
    redirect("/login?error=service-unavailable");
  }
  if (!response.ok) redirect("/login?error=session-expired");
  return response.json() as Promise<ViewerAccount>;
});
