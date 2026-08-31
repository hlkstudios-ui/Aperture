import { ImageResponse } from "next/og";

import { StaticGeneratedLogo } from "@/app/components/generated-logo";
import { siteBrandInitials, type SiteBrand } from "@/app/lib/site-brand";

async function embeddedLogo(logoPath: string | null): Promise<string | null> {
  if (!logoPath || !/^\/site\/brand\/logo(?:\?revision=\d+)?$/.test(logoPath)) return null;
  try {
    const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";
    const response = await fetch(`${apiOrigin.replace(/\/$/, "")}${logoPath}`, { cache: "no-store" });
    const logoType = response.headers.get("content-type") ?? "";
    if (!response.ok || !["image/png", "image/jpeg", "image/webp"].includes(logoType)) return null;
    const bytes = await response.arrayBuffer();
    if (!bytes.byteLength || bytes.byteLength > 2 * 1024 * 1024) return null;
    return `data:${logoType};base64,${Buffer.from(bytes).toString("base64")}`;
  } catch {
    return null;
  }
}

export async function siteBrandIconImage(
  brand: SiteBrand,
  pixelSize: number,
  instanceKey: string,
) {
  const logo = await embeddedLogo(brand.logo_url);
  const markSize = Math.round(pixelSize * 0.71875);
  const imageSize = Math.round(pixelSize * 0.625);
  const dimensions = { width: pixelSize, height: pixelSize };

  return new ImageResponse(
    <div style={{
      alignItems: "center",
      background: brand.palette.surface,
      color: brand.palette.text,
      display: "flex",
      fontSize: Math.round(pixelSize * 0.344),
      fontWeight: 900,
      height: "100%",
      justifyContent: "center",
      letterSpacing: "-0.04em",
      position: "relative",
      width: "100%",
    }}>
      <div style={{
        alignItems: "center",
        background: brand.logo_mark ? "transparent" : `linear-gradient(145deg, ${brand.palette.accent_hover}, ${brand.palette.accent})`,
        border: brand.logo_mark ? "0" : `1px solid ${brand.palette.accent_hover}`,
        borderRadius: brand.logo_mark ? "0" : "50%",
        color: brand.palette.accent,
        display: "flex",
        height: markSize,
        justifyContent: "center",
        position: "relative",
        width: markSize,
      }}>
        {logo ? (
          // ImageResponse renders this server-side into the icon PNG.
          // eslint-disable-next-line @next/next/no-img-element
          <img alt="" height={imageSize} src={logo} style={{ objectFit: "contain" }} width={imageSize} />
        ) : brand.logo_mark
          ? StaticGeneratedLogo({
            recipe: brand.logo_mark,
            decorative: true,
            size: markSize,
            instanceKey,
            color: brand.palette.accent,
          })
          : siteBrandInitials(brand)}
      </div>
    </div>,
    dimensions,
  );
}
