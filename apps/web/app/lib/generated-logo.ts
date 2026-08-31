export const GENERATED_LOGO_RENDERER_VERSION = 1 as const;

export const generatedLogoGlyphs = [
  "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
  "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
  "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
  "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
] as const;

export type GeneratedLogoGlyph = (typeof generatedLogoGlyphs)[number];

export const generatedLogoVariants = [
  { id: "iris", name: "Iris cut", note: "Precise lens geometry with a cinematic centre." },
  { id: "marquee", name: "Marquee light", note: "A theatre frame with a restrained illuminated edge." },
  { id: "prism", name: "Prism split", note: "An editorial monogram divided by a beam of light." },
  { id: "orbit", name: "Orbit", note: "A confident circular seal traced by a fine orbital line." },
  { id: "film-frame", name: "Film frame", note: "A compact screen-shaped mark with subtle sprockets." },
  { id: "eclipse", name: "Eclipse", note: "An atmospheric disc drawn around the letter." },
  { id: "stencil", name: "Stencil block", note: "A bold cut-out designed to remain legible when tiny." },
  { id: "signal", name: "Signal echo", note: "A contemporary letterform with a broadcast echo." },
  { id: "portal", name: "Portal", note: "A screen mark with rays extending beyond the frame." },
  { id: "monolith", name: "Monolith", note: "A tall, architectural frame with an editorial rhythm." },
  { id: "ribbon", name: "Ribbon loop", note: "A softer signature wrapped in intersecting curves." },
  { id: "beam", name: "Light beam", note: "A focused letter held inside a stage-light beam." },
] as const;

export type GeneratedLogoVariant = (typeof generatedLogoVariants)[number]["id"];

export type GeneratedLogoRecipe = Readonly<{
  renderer_version: typeof GENERATED_LOGO_RENDERER_VERSION;
  glyph: GeneratedLogoGlyph;
  variant: GeneratedLogoVariant;
}>;

const glyphSet = new Set<string>(generatedLogoGlyphs);
const variantSet = new Set<string>(generatedLogoVariants.map((variant) => variant.id));

export function isGeneratedLogoGlyph(value: unknown): value is GeneratedLogoGlyph {
  return typeof value === "string" && value.length === 1 && glyphSet.has(value);
}

export function isGeneratedLogoVariant(value: unknown): value is GeneratedLogoVariant {
  return typeof value === "string" && variantSet.has(value);
}

export function createGeneratedLogoRecipe(
  glyph: GeneratedLogoGlyph,
  variant: GeneratedLogoVariant,
): GeneratedLogoRecipe {
  return { renderer_version: GENERATED_LOGO_RENDERER_VERSION, glyph, variant };
}

/** Strictly validates the small recipe persisted by the API. */
export function parseGeneratedLogoRecipe(value: unknown): GeneratedLogoRecipe | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record);
  if (keys.length !== 3 || !keys.includes("renderer_version") || !keys.includes("glyph") || !keys.includes("variant")) {
    return null;
  }
  if (
    record.renderer_version !== GENERATED_LOGO_RENDERER_VERSION
    || !isGeneratedLogoGlyph(record.glyph)
    || !isGeneratedLogoVariant(record.variant)
  ) {
    return null;
  }
  return createGeneratedLogoRecipe(record.glyph, record.variant);
}

export function isGeneratedLogoRecipe(value: unknown): value is GeneratedLogoRecipe {
  return parseGeneratedLogoRecipe(value) !== null;
}

/** Preserves the user's upper/lowercase choice when suggesting a starting glyph. */
export function generatedLogoGlyphFrom(
  value: string,
  fallback: GeneratedLogoGlyph = "A",
): GeneratedLogoGlyph {
  if (isGeneratedLogoGlyph(value)) return value;
  const match = value.normalize("NFKD").match(/[A-Za-z]/)?.[0];
  return isGeneratedLogoGlyph(match) ? match : fallback;
}

export function generatedLogoVariantMeta(variant: GeneratedLogoVariant) {
  return generatedLogoVariants.find((candidate) => candidate.id === variant) ?? generatedLogoVariants[0];
}

function stableHash(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36).padStart(7, "0");
}

/** IDs contain only validated recipe values and a hash of the React instance seed. */
export function generatedLogoDefinitionPrefix(recipe: GeneratedLogoRecipe, instanceSeed: string): string {
  return `brand-mark-v${recipe.renderer_version}-${recipe.variant}-${recipe.glyph.charCodeAt(0).toString(36)}-${stableHash(instanceSeed)}`;
}

export function generatedLogoRecipeKey(recipe: GeneratedLogoRecipe): string {
  return `${recipe.renderer_version}:${recipe.glyph}:${recipe.variant}`;
}
