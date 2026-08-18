"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { customerAccountFetch, AccountActionError } from "@/app/lib/account";

export type SecurityState = { error: string; success?: string };
export async function startCheckout(planCode: string) {
  const result = await customerAccountFetch<{ checkout_url: string }>("/account/checkout", {
    method: "POST",
    body: JSON.stringify({ plan_code: planCode }),
  });
  redirect(result.checkout_url);
}
export async function openBillingPortal() {
  const result = await customerAccountFetch<{ portal_url: string }>("/account/billing-portal", {
    method: "POST",
  });
  redirect(result.portal_url);
}
export async function revokeSession(sessionId: string) {
  await customerAccountFetch(`/account/sessions/${sessionId}`, { method: "DELETE" });
  revalidatePath("/account");
}
export async function revokeOtherSessions() {
  await customerAccountFetch("/account/sessions/revoke-others", { method: "POST" });
  revalidatePath("/account");
}
export async function setRewatchIntelligence(
  profileId: string,
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
  },
  enabled: boolean,
) {
  await customerAccountFetch(`/profiles/${profileId}`, {
    method: "PATCH",
    body: JSON.stringify({
      preference: { ...preference, rewatch_intelligence_enabled: enabled },
    }),
  });
  revalidatePath("/account");
}
export async function setPrivacyPreferences(profileId: string, form: FormData) {
  await customerAccountFetch(`/profiles/${profileId}/privacy`, {
    method: "PUT",
    body: JSON.stringify({
      analytics_enabled: form.get("analytics_enabled") === "on",
      homepage_mode: String(form.get("homepage_mode") ?? "no_algorithm"),
    }),
  });
  revalidatePath("/account");
  revalidatePath("/");
  revalidatePath("/discover");
}
export async function setLanguagePreferences(
  profileId: string,
  preference: Parameters<typeof setRewatchIntelligence>[1],
  form: FormData,
) {
  const language = String(form.get("language") ?? "en");
  const subtitlesEnabled = form.get("subtitles_enabled") === "on";
  await customerAccountFetch(`/profiles/${profileId}`, {
    method: "PATCH",
    body: JSON.stringify({
      language,
      preference: {
        ...preference,
        preferred_audio_language: String(form.get("preferred_audio_language") || language),
        preferred_subtitle_language: String(form.get("preferred_subtitle_language") || language),
        preferred_secondary_subtitle_language: String(form.get("preferred_secondary_subtitle_language") || "") || null,
        subtitles_enabled: subtitlesEnabled,
        timezone: String(form.get("timezone") || "UTC"),
        caption_size: String(form.get("caption_size") || "medium"),
        caption_background: String(form.get("caption_background") || "shadow"),
        caption_position: String(form.get("caption_position") || "bottom"),
      },
    }),
  });
  revalidatePath("/account");
}
export async function changePassword(_: SecurityState, form: FormData): Promise<SecurityState> {
  try {
    await customerAccountFetch("/account/password", {
      method: "POST",
      body: JSON.stringify({
        current_password: String(form.get("current_password") ?? ""),
        new_password: String(form.get("new_password") ?? ""),
      }),
    });
  } catch (error) {
    return { error: error instanceof AccountActionError ? error.message : "Password change failed" };
  }
  revalidatePath("/account");
  return { error: "", success: "Password changed. Other sessions were signed out." };
}
