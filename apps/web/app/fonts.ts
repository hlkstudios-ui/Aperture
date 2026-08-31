import { Manrope, Newsreader, Roboto_Mono } from "next/font/google";

/**
 * Aperture's type families are defined once and exposed as CSS variables.
 * Next self-hosts the files, subsets them, and supplies metric-adjusted fallbacks,
 * so the browser never makes a font request to Google and layout shift stays low.
 */
const reading = Manrope({
  subsets: ["latin"],
  display: "swap",
  fallback: ["system-ui", "Segoe UI", "Arial", "sans-serif"],
  variable: "--font-aperture-reading",
});

const editorial = Newsreader({
  subsets: ["latin"],
  weight: "variable",
  style: ["normal", "italic"],
  axes: ["opsz"],
  display: "swap",
  fallback: ["Iowan Old Style", "Baskerville", "Georgia", "serif"],
  variable: "--font-aperture-editorial",
});

const data = Roboto_Mono({
  subsets: ["latin"],
  weight: "variable",
  display: "optional",
  preload: false,
  fallback: ["SFMono-Regular", "Consolas", "Liberation Mono", "monospace"],
  variable: "--font-aperture-data",
});

export const apertureFontVariables = [
  reading.variable,
  editorial.variable,
  data.variable,
].join(" ");
