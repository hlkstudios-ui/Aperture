"use server";

import { revalidatePath } from "next/cache";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";

export async function moderateReview(id:string, status:"approved"|"rejected"|"removed", form:FormData) {
  await adminCatalogFetch(`/admin/community/reviews/${id}/decision`, { method:"POST", body:JSON.stringify({status,reason:String(form.get("reason")??"")}) });
  revalidatePath("/studio/community");
}
export async function moderateList(id:string, status:"approved"|"rejected"|"removed", form:FormData) {
  await adminCatalogFetch(`/admin/community/lists/${id}/decision`, { method:"POST", body:JSON.stringify({status,reason:String(form.get("reason")??"")}) });
  revalidatePath("/studio/community");
}
export async function moderateReport(id:string, status:"resolved"|"dismissed", form:FormData) {
  await adminCatalogFetch(`/admin/community/reports/${id}/decision`, { method:"POST", body:JSON.stringify({status,reason:String(form.get("reason")??"")}) });
  revalidatePath("/studio/community");
}
