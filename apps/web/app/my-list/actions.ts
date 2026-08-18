"use server";

import { revalidatePath } from "next/cache";
import { customerAccountFetch } from "@/app/lib/account";
import type { Collection } from "@/app/lib/curation";

export async function setListVisibility(list:Collection, form:FormData) {
  const visibility=String(form.get("visibility")??"private");
  await customerAccountFetch(`/curation/my-lists/${list.id}`, {method:"PUT",body:JSON.stringify({title:list.title,description:list.description,visibility,items:list.items.map(item=>item.kind==="movie"?{movie_id:item.title_id,note:item.note}:{series_id:item.title_id,note:item.note})})});
  revalidatePath("/my-list"); revalidatePath("/community");
}
