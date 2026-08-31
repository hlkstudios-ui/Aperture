"use server";

import { revalidatePath } from "next/cache";
import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";

export type SourceFormState = { error: string; success?: string };

export async function attachCdnSource(
  _: SourceFormState,
  form: FormData,
): Promise<SourceFormState> {
  const target = String(form.get("target") ?? "");
  const [kind, id] = target.split(":");
  if (!id || !["movie", "episode"].includes(kind)) {
    return { error: "Choose a movie or episode." };
  }
  if (form.get("rights_confirmed") !== "on") {
    return { error: "Confirm that you own or are licensed to distribute this video." };
  }
  const territories = String(form.get("allowed_territories") ?? "")
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter(Boolean);
  const date = (name: string) => {
    const value = String(form.get(name) ?? "").trim();
    return value ? `${value}:00Z` : null;
  };
  try {
    await adminCatalogFetch("/admin/playback/sources", {
      method: "POST",
      body: JSON.stringify({
        movie_id: kind === "movie" ? id : null,
        episode_id: kind === "episode" ? id : null,
        external_manifest_url: String(form.get("external_manifest_url") ?? "").trim(),
        external_format: null,
        duration_seconds: null,
        rights_basis: "Operator attests that this source is owned or licensed for streaming distribution.",
        rights_reference: `studio-attestation:${kind}:${id}`,
        rights_start_at: date("rights_start_at"),
        rights_end_at: date("rights_end_at"),
        allowed_territories: territories,
        is_active: true,
      }),
    });
  } catch (error) {
    return {
      error: error instanceof CatalogActionError
        ? error.detail
        : "The media source could not be saved.",
    };
  }
  revalidatePath("/studio/sources");
  return { error: "", success: "Licensed CDN source attached." };
}
