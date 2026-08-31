"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";
import type { ViewerMonetizationRecord } from "./monetization-types";

export type MonetizationActionState = {
  sequence: number;
  error: string;
  notice: string;
};

function nextState(previous: MonetizationActionState) {
  return previous.sequence + 1;
}

function actionError(previous: MonetizationActionState, error: unknown): MonetizationActionState {
  return {
    sequence: nextState(previous),
    error: error instanceof CatalogActionError
      ? error.detail
      : "Customer payment settings could not be updated. Try again.",
    notice: "",
  };
}

function hostedStripeUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "connect.stripe.com"
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

export async function beginStripeConnectAction(
  previous: MonetizationActionState,
): Promise<MonetizationActionState> {
  let onboardingUrl: string;
  try {
    const response = await adminCatalogFetch<{ onboarding_url: unknown }>(
      "/admin/viewer-monetization/providers/stripe/connect",
      { method: "POST" },
    );
    const safeUrl = hostedStripeUrl(response.onboarding_url);
    if (!safeUrl) {
      return {
        sequence: nextState(previous),
        error: "Stripe returned an invalid hosted onboarding address. No payment setting changed.",
        notice: "",
      };
    }
    onboardingUrl = safeUrl;
  } catch (error) {
    return actionError(previous, error);
  }

  redirect(onboardingUrl);
}

export async function refreshMonetizationStatusAction(
  previous: MonetizationActionState,
): Promise<MonetizationActionState> {
  try {
    await adminCatalogFetch<ViewerMonetizationRecord>(
      "/admin/viewer-monetization/refresh",
      { method: "POST" },
    );
    revalidatePath("/studio/monetization");
    return {
      sequence: nextState(previous),
      error: "",
      notice: "Provider status refreshed. Free access and paid-checkout availability remain unchanged.",
    };
  } catch (error) {
    return actionError(previous, error);
  }
}
