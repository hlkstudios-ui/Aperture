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
import { DocumentLocale } from "./components/document-locale";
import { SiteFooter } from "./components/site-footer";

export const metadata: Metadata = {
  title: { default: "Aperture", template: "%s · Aperture" },
  description: "A cinema-first streaming and discovery platform.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#090909",
  colorScheme: "dark",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" dir="ltr">
      <head><link rel="preconnect" href="https://image.tmdb.org" crossOrigin="anonymous" /><link rel="dns-prefetch" href="https://image.tmdb.org" /></head>
      <body><DocumentLocale /><a className="skip-link" href="#main-content">Skip to main content</a><div id="main-content" tabIndex={-1}>{children}</div><SiteFooter /></body>
    </html>
  );
}
