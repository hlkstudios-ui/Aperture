"use server";

import { revalidatePath } from "next/cache";

import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";
import type { ViewerPlan } from "./monetization-types";

export type ViewerPlanActionState = {
  sequence: number;
  error: string;
  notice: string;
};

type TextResult = { value: string; error: string };

const codePattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const controlCharacters = /[\u0000-\u001f\u007f-\u009f]/;
const resolutions = new Set(["720p", "1080p", "4K"]);
const intervals = new Set(["month", "year"]);
const supportedCurrencies = new Set(["AUD", "CAD", "EUR", "GBP", "USD"]);
const maximumPriceCents = 100_000_000n;

function nextState(previous: ViewerPlanActionState): number {
  return previous.sequence + 1;
}

function failed(previous: ViewerPlanActionState, error: string): ViewerPlanActionState {
  return { sequence: nextState(previous), error, notice: "" };
}

function entry(form: FormData, key: string): string | null {
  const value = form.get(key);
  return typeof value === "string" ? value : null;
}

function cleanCopy(
  form: FormData,
  key: string,
  label: string,
  maximum: number,
): TextResult {
  const raw = entry(form, key);
  if (raw === null) return { value: "", error: `${label} could not be read.` };
  const value = raw.normalize("NFC").trim().replace(/\s+/g, " ");
  if (!value) return { value, error: `${label} is required.` };
  if (value.length > maximum) return { value, error: `${label} must be ${maximum} characters or fewer.` };
  if (controlCharacters.test(value)) return { value, error: `${label} contains unsupported characters.` };
  return { value, error: "" };
}

function planCode(form: FormData): TextResult {
  const raw = entry(form, "code");
  if (raw === null) return { value: "", error: "Plan code could not be read." };
  const value = raw
    .normalize("NFKC")
    .trim()
    .toLocaleLowerCase("en-US")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  if (!value || value.length > 64 || !codePattern.test(value)) {
    return {
      value,
      error: "Plan code must use letters, numbers, and single hyphens, with 64 characters or fewer.",
    };
  }
  return { value, error: "" };
}

function priceCents(form: FormData): { value: number | null; error: string } {
  const raw = entry(form, "price");
  const value = raw?.trim() ?? "";
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value);
  if (!match) return { value: null, error: "Price must be a positive amount with no more than two decimal places." };
  const cents = BigInt(match[1]) * 100n + BigInt((match[2] ?? "").padEnd(2, "0") || "0");
  if (cents <= 0n || cents > maximumPriceCents) {
    return { value: null, error: "Price must be between 0.01 and 1,000,000.00." };
  }
  return { value: Number(cents), error: "" };
}

function currencyCode(form: FormData): TextResult {
  const value = (entry(form, "currency") ?? "").trim().toLocaleUpperCase("en-US");
  return supportedCurrencies.has(value)
    ? { value, error: "" }
    : { value, error: "Currency must be AUD, CAD, EUR, GBP, or USD. These initial currencies use two decimal places." };
}

function streamCount(form: FormData): { value: number | null; error: string } {
  const raw = (entry(form, "max_streams") ?? "").trim();
  if (!/^\d{1,3}$/.test(raw)) {
    return { value: null, error: "Simultaneous streams must be a whole number from 1 to 100." };
  }
  const value = Number(raw);
  return value >= 1 && value <= 100
    ? { value, error: "" }
    : { value: null, error: "Simultaneous streams must be a whole number from 1 to 100." };
}

function refreshPlanViews(): void {
  revalidatePath("/studio/monetization");
  revalidatePath("/account");
}

function apiError(error: unknown): string {
  return error instanceof CatalogActionError
    ? error.detail
    : "The viewer plan could not be saved. Try again.";
}

export async function createViewerPlanAction(
  previous: ViewerPlanActionState,
  form: FormData,
): Promise<ViewerPlanActionState> {
  const code = planCode(form);
  const name = cleanCopy(form, "name", "Plan name", 120);
  const description = cleanCopy(form, "description", "Description", 500);
  const price = priceCents(form);
  const currency = currencyCode(form);
  const interval = (entry(form, "interval") ?? "").trim();
  const streams = streamCount(form);
  const resolution = (entry(form, "max_resolution") ?? "").trim();
  const error = [
    code.error,
    name.error,
    description.error,
    price.error,
    currency.error,
    intervals.has(interval) ? "" : "Billing interval must be monthly or yearly.",
    streams.error,
    resolutions.has(resolution) ? "" : "Maximum resolution must be 720p, 1080p, or 4K.",
  ].find(Boolean) ?? "";
  if (error || price.value === null || streams.value === null) return failed(previous, error);

  try {
    const created = await adminCatalogFetch<ViewerPlan>("/admin/viewer-plans", {
      method: "POST",
      body: JSON.stringify({
        code: code.value,
        name: name.value,
        description: description.value,
        price_cents: price.value,
        currency: currency.value,
        interval,
        max_streams: streams.value,
        max_resolution: resolution,
      }),
    });
    refreshPlanViews();
    return {
      sequence: nextState(previous),
      error: "",
      notice: `${created.name} was created as an active viewer plan. Free access remains unchanged, and paid checkout is not enabled in this release.`,
    };
  } catch (reason) {
    return failed(previous, apiError(reason));
  }
}

export async function archiveViewerPlanAction(
  previous: ViewerPlanActionState,
  form: FormData,
): Promise<ViewerPlanActionState> {
  const id = (entry(form, "plan_id") ?? "").trim();
  const confirmation = (entry(form, "confirmation") ?? "").trim();
  if (!uuidPattern.test(id)) {
    return failed(previous, "The viewer plan record is incomplete. Reload the page and try again.");
  }
  if (confirmation.length > 64 || !codePattern.test(confirmation)) {
    return failed(previous, "Type the displayed plan code exactly to confirm archival.");
  }
  try {
    const archived = await adminCatalogFetch<ViewerPlan>(
      `/admin/viewer-plans/${encodeURIComponent(id)}/archive`,
      {
        method: "POST",
        body: JSON.stringify({ confirmation_code: confirmation }),
      },
    );
    refreshPlanViews();
    return {
      sequence: nextState(previous),
      error: "",
      notice: `${archived.name} was archived. Existing subscription records were not rewritten.`,
    };
  } catch (reason) {
    return failed(previous, apiError(reason));
  }
}
