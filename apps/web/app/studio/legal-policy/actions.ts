"use server";

import { revalidatePath } from "next/cache";

import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";
import type { LegalPolicyDraftInput, LegalPolicyRecord } from "./legal-policy-types";

export type LegalPolicyFormState = {
  sequence: number;
  revision: number;
  updatedAt: string | null;
  error: string;
  notice: string;
};

type TextResult = { value: string | null; error: string };

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const controlCharacters = /[\u0000-\u001f\u007f]/;

function entry(form: FormData, key: string): string | null {
  const value = form.get(key);
  return typeof value === "string" ? value : null;
}

function cleanText(form: FormData, key: string, maximum: number, label: string): TextResult {
  const raw = entry(form, key);
  if (raw === null) return { value: null, error: `${label} could not be read.` };
  const value = raw.normalize("NFC").trim().replace(/\s+/g, " ");
  if (value.length > maximum) {
    return { value, error: `${label} must be ${maximum} characters or fewer.` };
  }
  if (controlCharacters.test(value)) {
    return { value, error: `${label} contains unsupported characters.` };
  }
  return { value: value || null, error: "" };
}

function cleanEmail(form: FormData, key: string, label: string): TextResult {
  const result = cleanText(form, key, 320, label);
  if (result.error || !result.value) return result;
  return emailPattern.test(result.value)
    ? result
    : { value: result.value, error: `Enter a valid ${label.toLocaleLowerCase()}.` };
}

function parseRevision(form: FormData): number | null {
  const value = entry(form, "revision");
  if (value === null || !/^\d+$/.test(value)) return null;
  const revision = Number(value);
  return Number.isSafeInteger(revision) ? revision : null;
}

function parseMinimumAge(form: FormData): { value: number | null; error: string } {
  const raw = entry(form, "minimum_user_age");
  if (raw === null) return { value: null, error: "Minimum user age could not be read." };
  const value = raw.trim();
  if (!value) return { value: null, error: "" };
  if (!/^\d{1,3}$/.test(value)) {
    return { value: null, error: "Minimum user age must be a whole number from 0 to 120." };
  }
  const age = Number(value);
  return age >= 0 && age <= 120
    ? { value: age, error: "" }
    : { value: null, error: "Minimum user age must be a whole number from 0 to 120." };
}

function draftPayload(form: FormData): { value: LegalPolicyDraftInput | null; error: string } {
  const legalOperatorName = cleanText(form, "legal_operator_name", 200, "Legal operator name");
  const region = cleanText(form, "region", 120, "Province or state");
  const supportEmail = cleanEmail(form, "support_email", "Support email");
  const privacyEmail = cleanEmail(form, "privacy_email", "Privacy email");
  const copyrightEmail = cleanEmail(form, "copyright_email", "Copyright and takedown email");
  const governingLaw = cleanText(
    form,
    "governing_law_jurisdiction",
    200,
    "Governing-law jurisdiction",
  );
  const minimumAge = parseMinimumAge(form);
  const countryEntry = entry(form, "country_code");
  const countryCode = countryEntry?.trim().toLocaleUpperCase() || null;
  const error = [
    legalOperatorName.error,
    region.error,
    supportEmail.error,
    privacyEmail.error,
    copyrightEmail.error,
    governingLaw.error,
    minimumAge.error,
    countryEntry === null
      ? "Country could not be read."
      : countryCode && !/^[A-Z]{2}$/.test(countryCode)
        ? "Country must use a two-letter country code."
        : "",
  ].find(Boolean) ?? "";
  if (error) return { value: null, error };
  return {
    value: {
      legal_operator_name: legalOperatorName.value,
      country_code: countryCode,
      region: region.value,
      support_email: supportEmail.value,
      privacy_email: privacyEmail.value,
      copyright_email: copyrightEmail.value,
      minimum_user_age: minimumAge.value,
      governing_law_jurisdiction: governingLaw.value,
    },
    error: "",
  };
}

function failedState(
  previous: LegalPolicyFormState,
  error: string,
): LegalPolicyFormState {
  return {
    ...previous,
    sequence: previous.sequence + 1,
    error,
    notice: "",
  };
}

export async function saveLegalPolicyDraftAction(
  previous: LegalPolicyFormState,
  form: FormData,
): Promise<LegalPolicyFormState> {
  const revision = parseRevision(form);
  if (revision === null || revision !== previous.revision) {
    return failedState(previous, "This draft changed. Reload the page before saving again.");
  }
  const payload = draftPayload(form);
  if (!payload.value) return failedState(previous, payload.error);

  try {
    const record = await adminCatalogFetch<LegalPolicyRecord>("/admin/site/legal-policy", {
      method: "PUT",
      body: JSON.stringify({ revision, ...payload.value }),
    });
    revalidatePath("/studio/legal-policy");
    return {
      sequence: previous.sequence + 1,
      revision: record.revision,
      updatedAt: record.updated_at,
      error: "",
      notice: "Private draft saved. No policy was approved or published.",
    };
  } catch (error) {
    return failedState(
      previous,
      error instanceof CatalogActionError
        ? error.detail
        : "The private legal and policy draft could not be saved. Please try again.",
    );
  }
}
