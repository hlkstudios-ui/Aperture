import { isGeneratedLogoRecipe, type GeneratedLogoRecipe } from "@/app/lib/generated-logo";

export type SiteBrandPalette = {
  accent: string;
  accent_hover: string;
  on_accent: "#000000" | "#ffffff";
  surface: string;
  surface_elevated: string;
  text: string;
  text_muted: string;
};

export type SiteBrandLocale = {
  default_locale: string;
  home_market: string;
  currency: string;
};

export type SiteBrand = {
  schema_version: 1;
  revision: number;
  business_name: string;
  short_name: string;
  tagline: string | null;
  description: string | null;
  logo_url: string | null;
  logo_revision: number | null;
  logo_mark: GeneratedLogoRecipe | null;
  palette: SiteBrandPalette;
  locale: SiteBrandLocale;
  published_at: string | null;
};

export const DEFAULT_SITE_BRAND: Readonly<SiteBrand> = Object.freeze({
  schema_version: 1,
  revision: 0,
  business_name: "Aperture",
  short_name: "Aperture",
  tagline: "Stories worth staying for.",
  description: "A cinematic home for films and series.",
  logo_url: null,
  logo_revision: null,
  logo_mark: null,
  palette: Object.freeze({
    accent: "#ff5c35",
    accent_hover: "#ff7657",
    on_accent: "#000000",
    surface: "#090909",
    surface_elevated: "#171310",
    text: "#f7f2ea",
    text_muted: "#b8afa6",
  }),
  locale: Object.freeze({
    default_locale: "en-US",
    home_market: "US",
    currency: "USD",
  }),
  published_at: null,
});

const HEX_COLOR = /^#[0-9a-f]{6}$/i;
const PUBLIC_LOGO_PATH = /^\/site\/brand\/logo(?:\?revision=\d+)?$/;
const LOCALE = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;

function validCopy(value: unknown, maximum: number, required = false): boolean {
  if (value === null) return !required;
  if (typeof value !== "string") return false;
  const clean = value.trim();
  return (!required || clean.length > 0)
    && clean.length <= maximum
    && !/[\u0000-\u001f\u007f]/.test(clean);
}

export function isSiteBrand(value: unknown): value is SiteBrand {
  if (!value || typeof value !== "object") return false;
  const brand = value as Partial<SiteBrand>;
  const palette = brand.palette as Partial<SiteBrandPalette> | undefined;
  const locale = brand.locale as Partial<SiteBrandLocale> | undefined;
  return brand.schema_version === 1
    && Number.isInteger(brand.revision) && Number(brand.revision) >= 0
    && validCopy(brand.business_name, 60, true)
    && validCopy(brand.short_name, 24, true)
    && validCopy(brand.tagline, 120)
    && validCopy(brand.description, 280)
    && (brand.logo_url === null || (typeof brand.logo_url === "string" && PUBLIC_LOGO_PATH.test(brand.logo_url)))
    && (brand.logo_revision === null || (Number.isInteger(brand.logo_revision) && Number(brand.logo_revision) >= 0))
    && (brand.logo_mark === null || isGeneratedLogoRecipe(brand.logo_mark))
    && !(brand.logo_url !== null && brand.logo_mark !== null)
    && Boolean(palette)
    && [palette?.accent, palette?.accent_hover, palette?.surface, palette?.surface_elevated, palette?.text, palette?.text_muted]
      .every((color) => typeof color === "string" && HEX_COLOR.test(color))
    && (palette?.on_accent === "#000000" || palette?.on_accent === "#ffffff")
    && typeof locale?.default_locale === "string" && LOCALE.test(locale.default_locale)
    && typeof locale?.home_market === "string" && /^[A-Z]{2}$/.test(locale.home_market)
    && typeof locale?.currency === "string" && /^[A-Z]{3}$/.test(locale.currency)
    && (brand.published_at === null || typeof brand.published_at === "string");
}

export function siteBrandLogoSrc(brand: SiteBrand): string | null {
  if (!brand.logo_url || !PUBLIC_LOGO_PATH.test(brand.logo_url)) return null;
  return brand.logo_url.replace(/^\/site\/brand\/logo/, "/api/site/brand/logo");
}

export function siteBrandInitials(brand: SiteBrand): string {
  const words = brand.short_name.trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "A";
}
