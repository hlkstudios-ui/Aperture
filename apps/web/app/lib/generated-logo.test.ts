import { describe, expect, it } from "vitest";

import {
  GENERATED_LOGO_RENDERER_VERSION,
  createGeneratedLogoRecipe,
  generatedLogoDefinitionPrefix,
  generatedLogoGlyphFrom,
  generatedLogoGlyphs,
  generatedLogoRecipeKey,
  generatedLogoVariants,
  parseGeneratedLogoRecipe,
} from "./generated-logo";
import {
  GENERATED_LOGO_GLYPH_SOURCE_SHA256,
  generatedLogoGlyphOutlines,
} from "./generated-logo-glyph-paths";

describe("generated logo recipes", () => {
  it("contains every A–Z and a–z glyph exactly once", () => {
    expect(generatedLogoGlyphs).toHaveLength(52);
    expect(new Set(generatedLogoGlyphs)).toHaveLength(52);
    expect(generatedLogoGlyphs.slice(0, 26).join("")).toBe("ABCDEFGHIJKLMNOPQRSTUVWXYZ");
    expect(generatedLogoGlyphs.slice(26).join("")).toBe("abcdefghijklmnopqrstuvwxyz");
  });

  it("offers twelve unique curated variants", () => {
    expect(generatedLogoVariants).toHaveLength(12);
    expect(new Set(generatedLogoVariants.map((variant) => variant.id))).toHaveLength(12);
  });

  it("round-trips all 624 finite recipes", () => {
    for (const glyph of generatedLogoGlyphs) {
      for (const variant of generatedLogoVariants) {
        const recipe = createGeneratedLogoRecipe(glyph, variant.id);
        expect(parseGeneratedLogoRecipe(JSON.parse(JSON.stringify(recipe)))).toEqual(recipe);
        expect(generatedLogoRecipeKey(recipe)).toBe(`${GENERATED_LOGO_RENDERER_VERSION}:${glyph}:${variant.id}`);
      }
    }
  });

  it("rejects unknown versions, glyphs, variants and extra recipe fields", () => {
    expect(parseGeneratedLogoRecipe({ renderer_version: 2, glyph: "A", variant: "orbit" })).toBeNull();
    expect(parseGeneratedLogoRecipe({ renderer_version: 1, glyph: "Å", variant: "orbit" })).toBeNull();
    expect(parseGeneratedLogoRecipe({ renderer_version: 1, glyph: "A", variant: "custom" })).toBeNull();
    expect(parseGeneratedLogoRecipe({ renderer_version: 1, glyph: "A", variant: "orbit", color: "red" })).toBeNull();
    expect(parseGeneratedLogoRecipe(null)).toBeNull();
  });

  it("preserves case and suggests the first ASCII letter from a name", () => {
    expect(generatedLogoGlyphFrom("A")).toBe("A");
    expect(generatedLogoGlyphFrom("a")).toBe("a");
    expect(generatedLogoGlyphFrom("  northstar")).toBe("n");
    expect(generatedLogoGlyphFrom("Élan")).toBe("E");
    expect(generatedLogoGlyphFrom("123", "Z")).toBe("Z");
  });

  it("creates deterministic, valid definition ids without copying instance text", () => {
    const recipe = createGeneratedLogoRecipe("A", "orbit");
    const first = generatedLogoDefinitionPrefix(recipe, "customer/<script>");
    expect(first).toBe(generatedLogoDefinitionPrefix(recipe, "customer/<script>"));
    expect(first).toMatch(/^[a-z][a-z0-9-]+$/);
    expect(first).not.toContain("script");
  });

  it("ships one finite, optically centered trusted outline for every glyph", () => {
    expect(GENERATED_LOGO_GLYPH_SOURCE_SHA256).toMatch(/^[0-9a-f]{64}$/);
    expect(Object.keys(generatedLogoGlyphOutlines)).toEqual([...generatedLogoGlyphs]);
    expect(new Set(Object.values(generatedLogoGlyphOutlines).map((outline) => outline.d))).toHaveLength(52);

    for (const glyph of generatedLogoGlyphs) {
      const outline = generatedLogoGlyphOutlines[glyph];
      expect(outline.d).toMatch(/^M[MLHVQCZ0-9 .-]+$/);
      expect(outline.d).not.toMatch(/(?:url|href|script|<|>|["'])/i);
      expect(outline.bounds.every(Number.isFinite)).toBe(true);
      const [left, top, right, bottom] = outline.bounds;
      expect(left).toBeGreaterThanOrEqual(0);
      expect(top).toBeGreaterThanOrEqual(0);
      expect(right).toBeLessThanOrEqual(104);
      expect(bottom).toBeLessThanOrEqual(104);
      expect(right - left).toBeLessThanOrEqual(50.001);
      expect(bottom - top).toBeLessThanOrEqual(44.001);
      expect(Math.abs(outline.opticalCenter[0] - 52)).toBeLessThanOrEqual(0.15);
      expect(Math.abs(outline.opticalCenter[1] - 52)).toBeLessThanOrEqual(0.15);
    }
  });
});
