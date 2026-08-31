import { render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  createGeneratedLogoRecipe,
  generatedLogoGlyphs,
  generatedLogoVariants,
  type GeneratedLogoRecipe,
} from "@/app/lib/generated-logo";
import { GeneratedLogo, StaticGeneratedLogo } from "./generated-logo";

describe("GeneratedLogo", () => {
  it("renders every letter as an accessible, focus-safe React SVG", () => {
    render(
      <div>
        {generatedLogoGlyphs.map((glyph) => (
          <GeneratedLogo
            key={glyph}
            recipe={createGeneratedLogoRecipe(glyph, "iris")}
            label={`${glyph} logo choice`}
            instanceKey={`glyph-${glyph}`}
          />
        ))}
      </div>,
    );

    const logos = screen.getAllByRole("img");
    expect(logos).toHaveLength(52);
    expect(screen.getByRole("img", { name: "A logo choice" })).toHaveAttribute("data-logo-glyph", "A");
    expect(screen.getByRole("img", { name: "a logo choice" })).toHaveAttribute("data-logo-glyph", "a");
    expect(logos.every((logo) => logo.getAttribute("focusable") === "false")).toBe(true);
  });

  it("renders all variants without raw markup, external references, or caller paint", () => {
    for (const variant of generatedLogoVariants) {
      const markup = renderToStaticMarkup(
        <GeneratedLogo recipe={createGeneratedLogoRecipe("Q", variant.id)} />,
      );
      expect(markup).toContain(`data-logo-variant="${variant.id}"`);
      expect(markup).not.toMatch(/<script|<image|<foreignObject|<filter|<feDropShadow|dangerouslySetInnerHTML|javascript:|href=|https?:\/\/(?!www\.w3\.org\/2000\/svg)/i);
      const paints = Array.from(markup.matchAll(/(?:fill|stroke)="([^"]+)"/g), (match) => match[1]);
      expect(paints.every((paint) => ["currentColor", "black", "white", "none"].includes(paint) || /^url\(#brand-mark-/.test(paint))).toBe(true);
    }
  });

  it("renders every finite glyph and construction pairing from trusted paths", () => {
    let rendered = 0;
    for (const glyph of generatedLogoGlyphs) {
      for (const variant of generatedLogoVariants) {
        const markup = renderToStaticMarkup(
          <StaticGeneratedLogo
            recipe={createGeneratedLogoRecipe(glyph, variant.id)}
            decorative
            instanceKey={`contract-${glyph}-${variant.id}`}
          />,
        );
        expect(markup).toContain(`data-logo-glyph="${glyph}"`);
        expect(markup).toContain(`data-logo-variant="${variant.id}"`);
        expect(markup).toContain(`data-logo-letter="${glyph}"`);
        expect(markup).not.toContain("<text");
        rendered += 1;
      }
    }
    expect(rendered).toBe(624);
  });

  it("isolates definition ids when identical recipes render together", () => {
    const recipe = createGeneratedLogoRecipe("N", "eclipse");
    const { container } = render(
      <>
        <GeneratedLogo recipe={recipe} instanceKey="preview" />
        <GeneratedLogo recipe={recipe} instanceKey="preview" />
      </>,
    );
    const svgs = Array.from(container.querySelectorAll("svg"));
    const idGroups = svgs.map((svg) => Array.from(svg.querySelectorAll("[id]"), (element) => element.id));
    expect(idGroups[0]).not.toEqual(idGroups[1]);
    expect(new Set(idGroups.flat())).toHaveLength(idGroups.flat().length);

    for (const svg of svgs) {
      const localIds = new Set(Array.from(svg.querySelectorAll("[id]"), (element) => element.id));
      const references = Array.from(svg.querySelectorAll("*"))
        .flatMap((element) => Array.from(element.attributes))
        .map((attribute) => attribute.value.match(/^url\(#(.+)\)$/)?.[1])
        .filter((value): value is string => Boolean(value));
      expect(references.length).toBeGreaterThan(0);
      expect(references.every((reference) => localIds.has(reference))).toBe(true);
    }
  });

  it("supports decorative use without exposing a duplicate name", () => {
    const { container } = render(<GeneratedLogo recipe={createGeneratedLogoRecipe("Q", "ribbon")} decorative />);
    const logo = container.querySelector("svg");
    expect(logo).toHaveAttribute("aria-hidden", "true");
    expect(logo).not.toHaveAttribute("role");
    expect(logo).not.toHaveAttribute("aria-labelledby");
    expect(logo?.querySelector("title")).toBeNull();
  });

  it("uses the same trusted glyph paths without runtime font text in every variant", () => {
    for (const variant of generatedLogoVariants) {
      const { container, unmount } = render(
        <GeneratedLogo
          recipe={createGeneratedLogoRecipe("q", variant.id)}
          decorative
        />,
      );
      expect(container.querySelector("svg")).not.toBeNull();
      expect(container.querySelector("text")).toBeNull();
      expect(container.querySelector('[data-logo-letter="q"]')).not.toBeNull();
      unmount();
    }
  });

  it("keeps the hook-free image renderer path-based and text-free", () => {
    const { container } = render(
      <StaticGeneratedLogo recipe={createGeneratedLogoRecipe("q", "stencil")} decorative />,
    );
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.querySelector("text")).toBeNull();
    expect(container.querySelector('[data-logo-letter="q"]')).not.toBeNull();
  });

  it("preserves the three optically centered signal echoes", () => {
    const { container } = render(
      <StaticGeneratedLogo recipe={createGeneratedLogoRecipe("R", "signal")} decorative />,
    );
    const visibleLetters = container.querySelectorAll('svg > g [data-logo-letter="R"]');
    expect(visibleLetters).toHaveLength(3);
    expect(Array.from(visibleLetters, (letter) => letter.getAttribute("transform"))).toEqual([
      "translate(-7 0)",
      "translate(-3 0)",
      "translate(2 0)",
    ]);
  });

  it("fails closed for a malformed runtime recipe", () => {
    const malformed = { renderer_version: 1, glyph: "<script>", variant: "orbit" } as unknown as GeneratedLogoRecipe;
    const { container } = render(<GeneratedLogo recipe={malformed} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});
