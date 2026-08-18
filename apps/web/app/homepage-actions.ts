"use server";

import { revalidatePath } from "next/cache";
import { customerAccountFetch } from "@/app/lib/account";

export async function setHomepageMode(mode: "curated" | "no_algorithm") {
  await customerAccountFetch("/homepage/mode", {
    method: "PATCH",
    body: JSON.stringify({ mode }),
  });
  revalidatePath("/");
  revalidatePath("/account");
}
