"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { adminCatalogFetch } from "@/app/lib/admin-catalog";

function number(data: FormData, key: string) {
  return Number(data.get(key));
}

export async function createVersion(data: FormData) {
  await adminCatalogFetch("/admin/scenes", {
    method: "POST",
    body: JSON.stringify({
      playback_source_id: data.get("playback_source_id"),
      notes: data.get("notes") || null,
    }),
  });
  revalidatePath("/studio/scenes");
  redirect("/studio/scenes?message=Version%20created");
}

export async function addSource(versionId: string, data: FormData) {
  await adminCatalogFetch(`/admin/scenes/${versionId}/sources`, {
    method: "POST",
    body: JSON.stringify({
      kind: data.get("kind"),
      label: data.get("label"),
      source_uri: data.get("source_uri") || null,
      license_basis: data.get("license_basis"),
    }),
  });
  revalidatePath("/studio/scenes");
}

export async function addScene(versionId: string, data: FormData) {
  await adminCatalogFetch(`/admin/scenes/${versionId}/scenes`, {
    method: "POST",
    body: JSON.stringify({
      source_id: data.get("source_id"),
      ordinal: number(data, "ordinal"),
      title: data.get("title"),
      summary: data.get("summary"),
      start_seconds: number(data, "start_seconds"),
      end_seconds: number(data, "end_seconds"),
      confidence: number(data, "confidence"),
      manually_verified: data.get("manually_verified") === "on",
    }),
  });
  revalidatePath("/studio/scenes");
}

export async function updateScene(versionId: string, sceneId: string, data: FormData) {
  await adminCatalogFetch(`/admin/scenes/${versionId}/scenes/${sceneId}`, {
    method: "PATCH",
    body: JSON.stringify({
      ordinal: number(data, "ordinal"),
      title: data.get("title"),
      summary: data.get("summary"),
      start_seconds: number(data, "start_seconds"),
      end_seconds: number(data, "end_seconds"),
      confidence: number(data, "confidence"),
      manually_verified: data.get("manually_verified") === "on",
    }),
  });
  revalidatePath("/studio/scenes");
}

async function transition(versionId: string, action: "jobs" | "validate" | "publish") {
  await adminCatalogFetch(`/admin/scenes/${versionId}/${action}`, { method: "POST" });
  revalidatePath("/studio/scenes");
}

export async function queueEnrichment(versionId: string) {
  await transition(versionId, "jobs");
}
export async function validateVersion(versionId: string) {
  await transition(versionId, "validate");
}
export async function publishVersion(versionId: string) {
  await transition(versionId, "publish");
}

export async function createPermittedStill(data: FormData) {
  const [sceneId, movieId, storageKey] = String(data.get("candidate") ?? "").split("|");
  if (!sceneId || !movieId || !storageKey) throw new Error("Choose a movie scene with a generated still");
  await adminCatalogFetch("/admin/catalog/artwork", {
    method: "POST",
    body: JSON.stringify({
      movie_id: movieId,
      kind: "still",
      scene_id: sceneId,
      timestamp_seconds: number(data, "timestamp_seconds"),
      storage_key: storageKey,
      alt_text: data.get("alt_text"),
      rights_basis: data.get("rights_basis"),
      permitted_for_gallery: true,
    }),
  });
  revalidatePath("/studio/scenes");
}
