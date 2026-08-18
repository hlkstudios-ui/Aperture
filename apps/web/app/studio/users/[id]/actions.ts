"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";

export async function updateCustomerState(formData: FormData) {
  const id = String(formData.get("id"));
  await adminCatalogFetch(`/admin/support/users/${id}/state`, { method: "PATCH", body: JSON.stringify({ is_active: formData.get("is_active") === "true", reason: formData.get("reason") }) });
  revalidatePath(`/studio/users/${id}`);
}

export async function revokeCustomerSessions(formData: FormData) {
  const id = String(formData.get("id"));
  await adminCatalogFetch(`/admin/support/users/${id}/revoke-sessions`, { method: "POST", body: JSON.stringify({ reason: formData.get("reason") }) });
  revalidatePath(`/studio/users/${id}`);
}

export async function deleteCustomer(formData: FormData) {
  const id = String(formData.get("id"));
  await adminCatalogFetch(`/admin/support/users/${id}`, {
    method: "DELETE",
    body: JSON.stringify({
      confirmation_email: formData.get("confirmation_email"),
      confirmation_phrase: formData.get("confirmation_phrase"),
      reason: formData.get("reason"),
      authorization_reference: formData.get("authorization_reference"),
    }),
  });
  redirect("/studio/users?deleted=1");
}
