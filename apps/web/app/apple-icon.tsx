import { siteBrandIconImage } from "@/app/lib/site-brand-icon-image";
import { getSiteBrand } from "@/app/lib/site-brand-server";

export const dynamic = "force-dynamic";
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default async function AppleIcon() {
  const brand = await getSiteBrand();
  return siteBrandIconImage(brand, size.width, "runtime-apple-icon");
}
