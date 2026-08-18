"use server";

import { revalidatePath } from "next/cache";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { HomepageDraft } from "@/app/lib/homepage";

function value(form: FormData, key: string) {
  return String(form.get(key) ?? "").trim();
}
function utc(form: FormData, key: string) {
  const raw = value(form, key);
  return raw ? `${raw}:00Z` : null;
}
function refresh() {
  revalidatePath("/studio/homepage");
  revalidatePath("/");
}

export async function setHero(form: FormData) {
  const [kind, id] = value(form, "hero").split(":");
  await adminCatalogFetch("/admin/homepage/hero", {
    method: "PUT",
    body: JSON.stringify({ movie_id: kind === "movie" ? id : null, series_id: kind === "series" ? id : null }),
  });
  refresh();
}

export async function createRail(form: FormData) {
  const draft = await adminCatalogFetch<HomepageDraft>("/admin/homepage");
  await adminCatalogFetch("/admin/homepage/rails", {
    method: "POST",
    body: JSON.stringify({
      title: value(form, "title"), eyebrow: value(form, "eyebrow") || null,
      source: value(form, "source"), query: value(form, "query") || null,
      position: draft.rails.length, enabled: true,
      starts_at: utc(form, "starts_at"), ends_at: utc(form, "ends_at"),
    }),
  });
  refresh();
}

export async function toggleRail(railId: string, enabled: boolean) {
  const draft = await adminCatalogFetch<HomepageDraft>("/admin/homepage");
  const rail = draft.rails.find((item) => item.id === railId);
  if (!rail) return;
  await adminCatalogFetch(`/admin/homepage/rails/${railId}`, {
    method: "PUT", body: JSON.stringify({ ...rail, enabled, items: undefined, id: undefined }),
  });
  refresh();
}

export async function updateRail(railId: string, form: FormData) {
  const draft = await adminCatalogFetch<HomepageDraft>("/admin/homepage");
  const rail = draft.rails.find((item) => item.id === railId);
  if (!rail) return;
  await adminCatalogFetch(`/admin/homepage/rails/${railId}`, {
    method: "PUT",
    body: JSON.stringify({
      title: value(form, "title"), eyebrow: value(form, "eyebrow") || null,
      source: value(form, "source"), query: value(form, "query") || null,
      position: rail.position, enabled: rail.enabled,
      starts_at: utc(form, "starts_at"), ends_at: utc(form, "ends_at"),
    }),
  });
  refresh();
}

export async function deleteRail(railId: string) {
  await adminCatalogFetch(`/admin/homepage/rails/${railId}`, { method: "DELETE" });
  refresh();
}

export async function pinTitle(railId: string, form: FormData) {
  const draft = await adminCatalogFetch<HomepageDraft>("/admin/homepage");
  const rail = draft.rails.find((item) => item.id === railId);
  if (!rail) return;
  const [kind, id] = value(form, "title").split(":");
  await adminCatalogFetch(`/admin/homepage/rails/${railId}/items`, {
    method: "POST",
    body: JSON.stringify({ movie_id: kind === "movie" ? id : null, series_id: kind === "series" ? id : null, position: rail.items.length }),
  });
  refresh();
}

export async function unpinTitle(itemId: string) {
  await adminCatalogFetch(`/admin/homepage/items/${itemId}`, { method: "DELETE" });
  refresh();
}

export async function moveRail(railId: string, delta: number) {
  const draft = await adminCatalogFetch<HomepageDraft>("/admin/homepage");
  const ids = draft.rails.map((rail) => rail.id);
  const index = ids.indexOf(railId); const target = index + delta;
  if (index < 0 || target < 0 || target >= ids.length) return;
  [ids[index], ids[target]] = [ids[target], ids[index]];
  await adminCatalogFetch("/admin/homepage/rails-order", { method: "PUT", body: JSON.stringify({ ids }) });
  refresh();
}

export async function moveItem(railId: string, itemId: string, delta: number) {
  const draft = await adminCatalogFetch<HomepageDraft>("/admin/homepage");
  const ids = draft.rails.find((rail) => rail.id === railId)?.items.map((item) => item.id) ?? [];
  const index = ids.indexOf(itemId); const target = index + delta;
  if (index < 0 || target < 0 || target >= ids.length) return;
  [ids[index], ids[target]] = [ids[target], ids[index]];
  await adminCatalogFetch(`/admin/homepage/rails/${railId}/items-order`, { method: "PUT", body: JSON.stringify({ ids }) });
  refresh();
}

export async function publishHomepage() {
  await adminCatalogFetch("/admin/homepage/publish", { method: "POST" });
  refresh();
}
