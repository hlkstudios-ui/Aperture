import { siteBrandIconImage } from "@/app/lib/site-brand-icon-image";
import { getSiteBrand } from "@/app/lib/site-brand-server";

export const dynamic = "force-dynamic";
export const size = { width: 64, height: 64 };
export const contentType = "image/png";

export default async function Icon() {
  const brand = await getSiteBrand();
  return siteBrandIconImage(brand, size.width, "runtime-favicon");
}
