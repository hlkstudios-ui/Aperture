import type { CSSProperties } from "react";
import type { Metadata, Viewport } from "next";
import "./styles.css";
import "./navbar.css";
import "./auth.css";
import "./account-chooser.css";
import "./performance.css";
import "./universal-search.css";
import "./federated-search.css";
import "./instant-search.css";
import "./card-fixes.css";
import "./footer.css";
import "./typography.css";
import { DocumentLocale } from "./components/document-locale";
import { SiteBrandProvider } from "./components/site-brand-provider";
import { SiteFooter } from "./components/site-footer";
import { apertureFontVariables } from "./fonts";
import { DEFAULT_SITE_BRAND, siteBrandLogoSrc } from "./lib/site-brand";
import { getSiteBrand } from "./lib/site-brand-server";
import { currentStorefrontOrigin, primaryStorefrontOrigin } from "./lib/public-origin";

// The published identity belongs to the running API, not the release artifact.
// Keep the entire route tree request-rendered so builds never bake a brand.
export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const [brand, publicOrigin, primaryOrigin] = await Promise.all([
    getSiteBrand(),
    currentStorefrontOrigin(),
    primaryStorefrontOrigin(),
  ]);
  const uploadedLogo = siteBrandLogoSrc(brand);
  const icon = uploadedLogo ?? (brand.logo_mark ? `/icon?revision=${brand.revision}` : null);
  const appleIcon = uploadedLogo ?? (brand.logo_mark ? `/apple-icon?revision=${brand.revision}` : null);
  return {
    metadataBase: new URL(publicOrigin),
    applicationName: brand.business_name,
    title: { default: brand.business_name, template: `%s · ${brand.business_name}` },
    description: brand.description ?? DEFAULT_SITE_BRAND.description,
    // Every connected hostname remains usable. Only the owner-selected front
    // door is indexable, avoiding duplicate search listings without redirects.
    robots: publicOrigin === primaryOrigin
      ? { index: true, follow: true }
      : { index: false, follow: true },
    ...(icon ? { icons: { icon, shortcut: icon, apple: appleIcon ?? icon } } : {}),
  };
}

export async function generateViewport(): Promise<Viewport> {
  const brand = await getSiteBrand();
  return {
    width: "device-width",
    initialScale: 1,
    viewportFit: "cover",
    themeColor: brand.palette.surface,
    colorScheme: "dark",
  };
}

const rtlLanguages = new Set(["ar", "fa", "he", "ur"]);

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const brand = await getSiteBrand();
  const language = brand.locale.default_locale.split("-")[0].toLowerCase();
  const brandStyle = {
    "--brand-accent": brand.palette.accent,
    "--brand-accent-hover": brand.palette.accent_hover,
    "--brand-on-accent": brand.palette.on_accent,
    "--brand-surface": brand.palette.surface,
    "--brand-surface-elevated": brand.palette.surface_elevated,
    "--brand-text": brand.palette.text,
    "--brand-text-muted": brand.palette.text_muted,
    "--accent": brand.palette.accent,
    "--accent-hover": brand.palette.accent_hover,
    "--on-accent": brand.palette.on_accent,
    "--red": brand.palette.accent,
    "--red-light": brand.palette.accent_hover,
    "--red-dark": brand.palette.accent,
    "--panel": brand.palette.surface_elevated,
    "--surface-0": brand.palette.surface,
    "--surface-1": brand.palette.surface_elevated,
    "--surface-2": brand.palette.surface_elevated,
    "--surface-3": brand.palette.surface_elevated,
    "--ink": brand.palette.text,
    "--muted": brand.palette.text_muted,
    "--text-strong": brand.palette.text,
    "--text-soft": brand.palette.text_muted,
  } as CSSProperties;
  return (
    <html lang={brand.locale.default_locale} dir={rtlLanguages.has(language) ? "rtl" : "ltr"} className={apertureFontVariables} style={brandStyle}>
      <head><link rel="preconnect" href="https://image.tmdb.org" crossOrigin="anonymous" /><link rel="dns-prefetch" href="https://image.tmdb.org" /></head>
      <body><SiteBrandProvider brand={brand}><DocumentLocale defaultLocale={brand.locale.default_locale} /><a className="skip-link" href="#main-content">Skip to main content</a><div id="main-content" tabIndex={-1}>{children}</div><SiteFooter brand={brand} /></SiteBrandProvider></body>
    </html>
  );
}
