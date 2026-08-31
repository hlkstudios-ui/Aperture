"use server";

import { cookies } from "next/headers";
import { revalidatePath, updateTag } from "next/cache";
import { redirect } from "next/navigation";

import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { studioEdgeHeaders } from "@/app/lib/studio-edge";
import { parseGeneratedLogoRecipe } from "@/app/lib/generated-logo";
import type {
  BrandCopyAssistInput,
  BrandCopySuggestion,
  BrandCopyTone,
  EditableSiteBrand,
  EditableSiteBrandPalette,
  LaunchSetupRecord,
  LaunchStep,
} from "./launch-setup-types";
import { brandCopyTones } from "./launch-setup-types";

export type LaunchSetupFormState = {
  sequence: number;
  error: string;
  notice: string;
  setup: LaunchSetupRecord | null;
};

export type LaunchLogoResult = {
  error: string;
  notice: string;
  setup: LaunchSetupRecord | null;
};

export type BrandCopyAssistResult = {
  error: string;
  suggestions: BrandCopySuggestion[];
};

const colorPattern = /^#[0-9a-f]{6}$/i;
const localePattern = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;
const acceptedLogoTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
const maxLogoBytes = 2 * 1024 * 1024;

function text(value: unknown) {
  return typeof value === "string" ? value.trim().replace(/\s+/g, " ") : "";
}

function editablePayload(value: unknown): EditableSiteBrand | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const palette = record.palette as Record<string, unknown> | undefined;
  const locale = record.locale as Record<string, unknown> | undefined;
  const rawLogoMark = record.logo_mark ?? null;
  const logoMark = rawLogoMark === null ? null : parseGeneratedLogoRecipe(rawLogoMark);
  if (!palette || !locale) return null;
  if (rawLogoMark !== null && !logoMark) return null;
  const colors: EditableSiteBrandPalette = {
    accent: text(palette.accent).toLowerCase(),
    accent_hover: text(palette.accent_hover).toLowerCase(),
    surface: text(palette.surface).toLowerCase(),
    surface_elevated: text(palette.surface_elevated).toLowerCase(),
    text: text(palette.text).toLowerCase(),
    text_muted: text(palette.text_muted).toLowerCase(),
  };
  return {
    business_name: text(record.business_name),
    short_name: text(record.short_name),
    tagline: text(record.tagline),
    description: text(record.description),
    logo_mark: logoMark,
    palette: colors,
    locale: {
      default_locale: text(locale.default_locale),
      home_market: text(locale.home_market).toUpperCase(),
      currency: text(locale.currency).toUpperCase(),
    },
  };
}

function stepNumber(value: FormDataEntryValue | null): LaunchStep | null {
  const step = Number(value);
  return Number.isInteger(step) && step >= 1 && step <= 5 ? step as LaunchStep : null;
}

function completedSteps(value: FormDataEntryValue | null): LaunchStep[] {
  try {
    const values = JSON.parse(String(value ?? "[]")) as unknown;
    if (!Array.isArray(values)) return [];
    const normalized = [...new Set(values.map(Number))]
      .filter((step) => Number.isInteger(step) && step >= 1 && step <= 5)
      .toSorted((left, right) => left - right);
    for (let index = 0; index < normalized.length; index += 1) {
      if (normalized[index] !== index + 1) return [];
    }
    return normalized as LaunchStep[];
  } catch {
    return [];
  }
}

function hexToRgb(value: string) {
  return [1, 3, 5].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16));
}

function luminance(value: string) {
  const channels = hexToRgb(value).map((channel) => {
    const normalized = channel / 255;
    return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

function contrast(first: string, second: string) {
  const values = [luminance(first), luminance(second)].toSorted((left, right) => right - left);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

function validationError(step: LaunchStep, brand: EditableSiteBrand, publish: boolean) {
  if ((step === 1 || publish) && (brand.business_name.length < 2 || brand.business_name.length > 60)) {
    return "Business name must be between 2 and 60 characters.";
  }
  if ((step === 1 || publish) && brand.tagline.length > 120) return "Tagline must be 120 characters or fewer.";
  if ((step === 1 || publish) && brand.description.length > 280) return "Description must be 280 characters or fewer.";
  if ((step === 2 || publish) && (brand.short_name.length < 2 || brand.short_name.length > 24)) {
    return "Compact name must be between 2 and 24 characters.";
  }
  if (step === 3 || publish) {
    if (Object.values(brand.palette).some((color) => !colorPattern.test(color))) {
      return "Every brand color must use the six-digit #RRGGBB format.";
    }
    const surfaces = [brand.palette.surface, brand.palette.surface_elevated];
    if (surfaces.some((surface) => contrast(brand.palette.text, surface) < 4.5
      || contrast(brand.palette.text_muted, surface) < 4.5
      || contrast(brand.palette.accent, surface) < 4.5
      || contrast(brand.palette.accent_hover, surface) < 4.5)) {
      return "The palette does not meet the required readable contrast levels.";
    }
    const commonButtonText = ["#000000", "#ffffff"].some((candidate) =>
      contrast(candidate, brand.palette.accent) >= 4.5
      && contrast(candidate, brand.palette.accent_hover) >= 4.5,
    );
    if (!commonButtonText) {
      return "Accent and hover accent need the same readable black or white button text.";
    }
  }
  if (step === 4 || publish) {
    if (!localePattern.test(brand.locale.default_locale)) return "Default language must be a valid locale.";
    if (!/^[A-Z]{2}$/.test(brand.locale.home_market)) return "Home market must be a two-letter country code.";
    if (!/^[A-Z]{3}$/.test(brand.locale.currency)) return "Currency must be a three-letter currency code.";
  }
  return "";
}

function configForStep(step: LaunchStep, brand: EditableSiteBrand, publish: boolean) {
  if (publish) {
    return {
      business_name: brand.business_name,
      short_name: brand.short_name,
      tagline: brand.tagline || null,
      description: brand.description || null,
      logo_mark: brand.logo_mark,
      palette: brand.palette,
      locale: brand.locale,
    };
  }
  if (step === 1) return {
    business_name: brand.business_name,
    tagline: brand.tagline || null,
    description: brand.description || null,
    ...(brand.short_name.length >= 2 && brand.short_name.length <= 24
      ? { short_name: brand.short_name }
      : {}),
  };
  if (step === 2) return { short_name: brand.short_name, logo_mark: brand.logo_mark };
  if (step === 3) return { palette: brand.palette };
  if (step === 4) return { locale: brand.locale };
  return {};
}

function actionError(error: unknown) {
  if (error instanceof CatalogActionError) {
    return error.detail.includes("revision")
      ? "This launch file changed in another tab. Reload the page, then apply your choice again."
      : error.detail;
  }
  return "The launch file could not be saved. Your choices remain on this screen.";
}

function optionalCopy(value: unknown, maximum: number) {
  const normalized = text(value);
  return normalized && normalized.length <= maximum ? normalized : null;
}

function assistPayload(value: unknown): BrandCopyAssistInput | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const businessName = text(record.business_name);
  const audience = optionalCopy(record.audience, 160);
  const additionalDirection = optionalCopy(record.additional_direction, 240);
  const tone = text(record.tone) as BrandCopyTone;
  if (businessName.length < 2 || businessName.length > 60) return null;
  if (!brandCopyTones.includes(tone)) return null;
  if (text(record.audience).length > 160 || text(record.additional_direction).length > 240) return null;
  return {
    business_name: businessName,
    short_name: optionalCopy(record.short_name, 24),
    existing_tagline: optionalCopy(record.existing_tagline, 120),
    existing_description: optionalCopy(record.existing_description, 280),
    audience,
    tone,
    additional_direction: additionalDirection,
  };
}

function validSuggestion(value: unknown): BrandCopySuggestion | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  const shortName = text(candidate.short_name);
  const tagline = text(candidate.tagline);
  const description = text(candidate.description);
  const toneDirection = text(candidate.tone_direction);
  if (shortName.length < 2 || shortName.length > 24) return null;
  if (tagline.length < 4 || tagline.length > 120) return null;
  if (description.length < 20 || description.length > 280) return null;
  if (toneDirection.length < 4 || toneDirection.length > 120) return null;
  return {
    short_name: shortName,
    tagline,
    description,
    tone_direction: toneDirection,
  };
}

function assistError(error: unknown) {
  if (!(error instanceof CatalogActionError)) {
    return "The writing room could not return ideas. Your draft was not changed. Try again.";
  }
  if (error.code === "brand_ai_rate_limited") {
    return "The writing room has reached its request limit. Wait a moment, then try again.";
  }
  if (error.code === "brand_ai_unavailable") {
    return "AI writing assistance is not available yet. Configure the writing service, then retry.";
  }
  const detail = error.detail.toLocaleLowerCase();
  if (detail.includes("rate") || detail.includes("too many") || detail.includes("request limit")) {
    return "The writing room has reached its request limit. Wait a moment, then try again.";
  }
  if (detail.includes("unavailable") || detail.includes("not configured")) {
    return "AI writing assistance is not available yet. Configure the writing service, then retry.";
  }
  return "The writing room could not return usable ideas. Your draft was not changed. Try again.";
}

export async function assistBrandCopyAction(input: BrandCopyAssistInput): Promise<BrandCopyAssistResult> {
  const payload = assistPayload(input);
  if (!payload) {
    return {
      error: "Add a valid business name and keep the writing brief within its character limits.",
      suggestions: [],
    };
  }
  try {
    const response = await adminCatalogFetch<{ generated_by?: unknown; suggestions?: unknown[] }>("/admin/site/brand/assist-copy", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const suggestions = response.suggestions?.map(validSuggestion) ?? [];
    if (response.generated_by !== "ai" || suggestions.length !== 3 || suggestions.some((suggestion) => suggestion === null)) {
      return {
        error: "The writing room returned an incomplete set. Your draft was not changed. Try again.",
        suggestions: [],
      };
    }
    return { error: "", suggestions: suggestions as BrandCopySuggestion[] };
  } catch (reason) {
    return { error: assistError(reason), suggestions: [] };
  }
}

export async function mutateLaunchSetupAction(
  previous: LaunchSetupFormState,
  form: FormData,
): Promise<LaunchSetupFormState> {
  const sequence = previous.sequence + 1;
  const revision = Number(form.get("revision"));
  const step = stepNumber(form.get("step"));
  const storedCurrentStep = stepNumber(form.get("current_step"));
  const intent = String(form.get("intent") ?? "save");
  const publish = intent === "publish";
  let parsed: unknown;
  try {
    parsed = JSON.parse(String(form.get("payload") ?? ""));
  } catch {
    return { sequence, error: "The launch choices could not be read.", notice: "", setup: null };
  }
  const brand = editablePayload(parsed);
  if (!Number.isInteger(revision) || revision < 0 || !step || !storedCurrentStep || !brand) {
    return { sequence, error: "The launch file is incomplete. Reload the page and try again.", notice: "", setup: null };
  }
  const error = validationError(step, brand, publish);
  if (error) return { sequence, error, notice: "", setup: null };

  const priorCompleted = completedSteps(form.get("completed_steps"));
  const finishedThrough = publish ? 5 : step;
  const completed = Array.from({ length: Math.max(finishedThrough, priorCompleted.length) }, (_, index) => index + 1) as LaunchStep[];
  const nextStep = Math.max(storedCurrentStep, Math.min(5, step + 1)) as LaunchStep;

  try {
    let setup = await adminCatalogFetch<LaunchSetupRecord>("/admin/site/brand", {
      method: "PATCH",
      body: JSON.stringify({
        revision,
        current_step: publish ? 5 : nextStep,
        completed_steps: completed,
        config: configForStep(step, brand, publish),
      }),
    });
    if (publish) {
      setup = await adminCatalogFetch<LaunchSetupRecord>("/admin/site/brand/publish", {
        method: "POST",
        body: JSON.stringify({ revision: setup.revision }),
      });
      updateTag("site-brand");
      revalidatePath("/", "layout");
    }
    revalidatePath("/studio/launch");
    return {
      sequence,
      error: "",
      notice: publish ? `${setup.config.business_name} is now the public identity.` : `Stage ${String(step).padStart(2, "0")} secured.`,
      setup,
    };
  } catch (reason) {
    return { sequence, error: actionError(reason), notice: "", setup: null };
  }
}

async function adminLogoFetch(path: string, init: RequestInit): Promise<LaunchSetupRecord> {
  await requireAdminSession();
  const cookieStore = await cookies();
  const session = cookieStore.get("aperture_admin_session");
  if (!session) redirect("/studio/login");
  const response = await fetch(`${process.env.API_ORIGIN ?? "http://localhost:8000"}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Origin: process.env.WEB_ORIGIN ?? "http://localhost:3000",
      cookie: `${session.name}=${session.value}`,
      ...studioEdgeHeaders(),
      ...init.headers,
    },
  });
  if (response.status === 401) redirect("/studio/login?error=session-expired");
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new CatalogActionError(body?.detail ?? `Logo request failed (${response.status})`);
  }
  return response.json() as Promise<LaunchSetupRecord>;
}

export async function uploadLaunchLogoAction(form: FormData): Promise<LaunchLogoResult> {
  const file = form.get("logo");
  const revision = Number(form.get("revision"));
  if (!(file instanceof File) || file.size === 0) return { error: "Choose a PNG, JPEG, or WebP logo.", notice: "", setup: null };
  if (!acceptedLogoTypes.has(file.type)) return { error: "Logo must be a PNG, JPEG, or WebP image.", notice: "", setup: null };
  if (file.size > maxLogoBytes) return { error: "Logo must be 2 MiB or smaller.", notice: "", setup: null };
  if (!Number.isInteger(revision) || revision < 0) return { error: "Reload the launch file before uploading a logo.", notice: "", setup: null };
  try {
    const setup = await adminLogoFetch(`/admin/site/brand/logo?expected_revision=${revision}`, {
      method: "PUT",
      body: await file.arrayBuffer(),
      headers: { "Content-Type": file.type },
    });
    revalidatePath("/studio/launch");
    return { error: "", notice: "Logo secured in the private launch file.", setup };
  } catch (reason) {
    return { error: actionError(reason), notice: "", setup: null };
  }
}

export async function removeLaunchLogoAction(revision: number): Promise<LaunchLogoResult> {
  if (!Number.isInteger(revision) || revision < 0) return { error: "Reload the launch file before removing the logo.", notice: "", setup: null };
  try {
    const setup = await adminLogoFetch(`/admin/site/brand/logo?expected_revision=${revision}`, { method: "DELETE" });
    revalidatePath("/studio/launch");
    return { error: "", notice: "Custom logo removed. Choose and save a Logo Atelier mark before publishing.", setup };
  } catch (reason) {
    return { error: actionError(reason), notice: "", setup: null };
  }
}
