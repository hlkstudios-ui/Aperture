"use server";

import { revalidatePath } from "next/cache";
import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";

export type PayoutState = { error: string; success?: string };

function cents(value: FormDataEntryValue | null): number | null {
  const raw = String(value ?? "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(raw)) return null;
  const [whole, fraction = ""] = raw.split(".");
  const amount = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(amount) && amount > 0 ? amount : null;
}

export async function createPayoutAction(_: PayoutState, form: FormData): Promise<PayoutState> {
  const amount = cents(form.get("amount"));
  if (amount === null) return { error: "Enter a valid payout amount with no more than two decimal places." };
  try {
    const payout = await adminCatalogFetch<{ id: string; status: string; amount: number; currency: string }>("/admin/revenue/payouts", {
      method: "POST",
      body: JSON.stringify({ amount, currency: String(form.get("currency") ?? ""), confirmation: String(form.get("confirmation") ?? ""), request_id: String(form.get("request_id") ?? "") }),
    });
    revalidatePath("/studio");
    revalidatePath("/studio/revenue");
    return { error: "", success: `Payout ${payout.id} was created with status ${payout.status}.` };
  } catch (error) {
    return { error: error instanceof CatalogActionError ? error.detail : "The payout request could not be completed." };
  }
}
