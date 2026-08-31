"use server";

import { revalidatePath } from "next/cache";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { ExploreCriteria, ExploreEntry } from "@/app/lib/explore";

function value(form: FormData, key: string) {
  return String(form.get(key) ?? "").trim();
}

function optional(form: FormData, key: string) {
  return value(form, key) || null;
}

function criteria(form: FormData): ExploreCriteria {
  const country = optional(form, "country_code");
  const language = optional(form, "original_language_code");
  return {
    content_type: value(form, "content_type") as ExploreCriteria["content_type"],
    query: optional(form, "query"),
    genre: optional(form, "genre"),
    studio: optional(form, "studio"),
    country_code: country?.toUpperCase() ?? null,
    original_language_code: language?.toLowerCase() ?? null,
    maturity_rating: optional(form, "maturity_rating"),
    release_period: value(form, "release_period") as ExploreCriteria["release_period"],
    duration: value(form, "duration") as ExploreCriteria["duration"],
    airing: value(form, "airing") as ExploreCriteria["airing"],
  };
}

function refreshExplore() {
  revalidatePath("/studio/explore");
  revalidatePath("/");
}

function payload(form: FormData, position: number, enabled: boolean) {
  return {
    label: value(form, "label"),
    description: value(form, "description"),
    icon: value(form, "icon") || "↗",
    position,
    enabled,
    criteria: criteria(form),
  };
}

export async function createExploreEntry(form: FormData) {
  const entries = await adminCatalogFetch<ExploreEntry[]>("/admin/explore");
  const position = entries.reduce((highest, entry) => Math.max(highest, entry.position), -1) + 1;
  await adminCatalogFetch("/admin/explore", {
    method: "POST",
    body: JSON.stringify(payload(form, position, true)),
  });
  refreshExplore();
}

export async function updateExploreEntry(entryId: string, form: FormData) {
  const entries = await adminCatalogFetch<ExploreEntry[]>("/admin/explore");
  const entry = entries.find((candidate) => candidate.id === entryId);
  if (!entry) return;
  await adminCatalogFetch(`/admin/explore/${entryId}`, {
    method: "PUT",
    body: JSON.stringify(payload(form, entry.position, entry.enabled ?? true)),
  });
  refreshExplore();
}

export async function toggleExploreEntry(entryId: string, enabled: boolean) {
  const entries = await adminCatalogFetch<ExploreEntry[]>("/admin/explore");
  const entry = entries.find((candidate) => candidate.id === entryId);
  if (!entry) return;
  await adminCatalogFetch(`/admin/explore/${entryId}`, {
    method: "PUT",
    body: JSON.stringify({
      label: entry.label,
      description: entry.description,
      icon: entry.icon,
      position: entry.position,
      enabled,
      criteria: entry.criteria,
    }),
  });
  refreshExplore();
}

export async function deleteExploreEntry(entryId: string) {
  await adminCatalogFetch(`/admin/explore/${entryId}`, { method: "DELETE" });
  refreshExplore();
}

export async function moveExploreEntry(entryId: string, delta: number) {
  const entries = await adminCatalogFetch<ExploreEntry[]>("/admin/explore");
  const ids = entries.map((entry) => entry.id);
  const index = ids.indexOf(entryId);
  const target = index + delta;
  if (index < 0 || target < 0 || target >= ids.length) return;
  [ids[index], ids[target]] = [ids[target], ids[index]];
  await adminCatalogFetch("/admin/explore/order", {
    method: "PUT",
    body: JSON.stringify({ ids }),
  });
  refreshExplore();
}

export async function attachExploreCard(entryId: string, form: FormData) {
  const entries = await adminCatalogFetch<ExploreEntry[]>("/admin/explore");
  const entry = entries.find((candidate) => candidate.id === entryId);
  if (!entry) return;

  const [kind, titleId] = value(form, "title").split(":", 2);
  if (!titleId || (kind !== "movie" && kind !== "series")) return;

  const position = (entry.cards ?? []).reduce(
    (highest, card) => Math.max(highest, card.position),
    -1,
  ) + 1;
  await adminCatalogFetch(`/admin/explore/${entryId}/cards`, {
    method: "POST",
    body: JSON.stringify({
      movie_id: kind === "movie" ? titleId : null,
      series_id: kind === "series" ? titleId : null,
      position,
    }),
  });
  refreshExplore();
}

export async function moveExploreCard(entryId: string, cardId: string, delta: number) {
  const entries = await adminCatalogFetch<ExploreEntry[]>("/admin/explore");
  const cards = [...(entries.find((entry) => entry.id === entryId)?.cards ?? [])]
    .sort((left, right) => left.position - right.position);
  const ids = cards.map((card) => card.id);
  const index = ids.indexOf(cardId);
  const target = index + delta;
  if (index < 0 || target < 0 || target >= ids.length) return;
  [ids[index], ids[target]] = [ids[target], ids[index]];
  await adminCatalogFetch(`/admin/explore/${entryId}/cards/order`, {
    method: "PUT",
    body: JSON.stringify({ ids }),
  });
  refreshExplore();
}

export async function removeExploreCard(cardId: string) {
  await adminCatalogFetch(`/admin/explore/cards/${cardId}`, { method: "DELETE" });
  refreshExplore();
}
