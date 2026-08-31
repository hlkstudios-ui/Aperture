import type { GeneratedLogoRecipe } from "@/app/lib/generated-logo";

export type LaunchStep = 1 | 2 | 3 | 4 | 5;

export type SiteBrandPalette = {
  accent: string;
  accent_hover: string;
  on_accent: "#000000" | "#ffffff";
  surface: string;
  surface_elevated: string;
  text: string;
  text_muted: string;
};

export type EditableSiteBrandPalette = Omit<SiteBrandPalette, "on_accent">;

export type SiteBrandLocale = {
  default_locale: string;
  home_market: string;
  currency: string;
};

export type SiteBrandConfig = {
  business_name: string;
  short_name: string;
  tagline: string | null;
  description: string | null;
  logo_url: string | null;
  logo_revision: number;
  logo_mark: GeneratedLogoRecipe | null;
  palette: SiteBrandPalette;
  locale: SiteBrandLocale;
};

export type LaunchSetupRecord = {
  schema_version: 1;
  revision: number;
  status: "draft" | "published";
  current_step: LaunchStep;
  completed_steps: LaunchStep[];
  config: SiteBrandConfig;
  updated_at: string | null;
  published_at: string | null;
};

export type EditableSiteBrand = {
  business_name: string;
  short_name: string;
  tagline: string;
  description: string;
  logo_mark: GeneratedLogoRecipe | null;
  palette: EditableSiteBrandPalette;
  locale: SiteBrandLocale;
};

export const brandCopyTones = [
  "cinematic",
  "warm",
  "bold",
  "refined",
  "playful",
  "mysterious",
] as const;

export type BrandCopyTone = (typeof brandCopyTones)[number];

export type BrandCopyAssistInput = {
  business_name: string;
  short_name: string | null;
  existing_tagline: string | null;
  existing_description: string | null;
  audience: string | null;
  tone: BrandCopyTone;
  additional_direction: string | null;
};

export type BrandCopySuggestion = {
  tagline: string;
  description: string;
  short_name: string;
  tone_direction: string;
};

export const launchSteps: ReadonlyArray<{
  number: LaunchStep;
  label: string;
  note: string;
}> = [
  { number: 1, label: "Identity", note: "Name and point of view" },
  { number: 2, label: "Signature", note: "Wordmark and compact mark" },
  { number: 3, label: "Palette", note: "Light, depth and contrast" },
  { number: 4, label: "Home market", note: "Language, region and currency" },
  { number: 5, label: "Premiere", note: "Review and take the name live" },
] as const;

export const defaultLaunchSetup: LaunchSetupRecord = {
  schema_version: 1,
  revision: 0,
  status: "draft",
  current_step: 1,
  completed_steps: [],
  config: {
    business_name: "",
    short_name: "",
    tagline: "",
    description: "",
    logo_url: null,
    logo_revision: 0,
    logo_mark: null,
    palette: {
      accent: "#ff5c35",
      accent_hover: "#ff7657",
      on_accent: "#000000",
      surface: "#090909",
      surface_elevated: "#171310",
      text: "#f7f2ea",
      text_muted: "#b8afa6",
    },
    locale: {
      default_locale: "en-US",
      home_market: "US",
      currency: "USD",
    },
  },
  updated_at: null,
  published_at: null,
};
