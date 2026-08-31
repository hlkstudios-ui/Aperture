import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

function source(name: string) {
  return readFileSync(resolve(process.cwd(), "app", name), "utf8");
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeSelector(value: string) {
  return value
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function declarations(body: string) {
  const result = new Map<string, string>();
  for (const declaration of body.split(";")) {
    const separator = declaration.indexOf(":");
    if (separator === -1) continue;
    result.set(
      declaration.slice(0, separator).trim(),
      declaration.slice(separator + 1).trim(),
    );
  }
  return result;
}

function ruleDeclarations(css: string, selector: string) {
  let latest: Map<string, string> | undefined;
  const rules = /([^{}]+)\{([^{}]*)\}/gs;
  for (const match of css.matchAll(rules)) {
    const selectors = normalizeSelector(match[1])
      .split(",")
      .map((item) => item.trim());
    if (selectors.includes(selector)) latest = declarations(match[2]);
  }
  if (!latest) throw new Error(`Missing CSS rule for ${selector}`);
  return latest;
}

function customProperty(css: string, name: string) {
  const match = css.match(
    new RegExp(`--${escapeRegExp(name)}\\s*:\\s*([^;]+);`),
  );
  if (!match) throw new Error(`Missing custom property --${name}`);
  return match[1].trim();
}

function remToPixels(value: string) {
  const match = value.match(/^(\d*\.?\d+)rem$/);
  if (!match) throw new Error(`Expected a fixed rem value, received ${value}`);
  return Number(match[1]) * 16;
}

function mediaBlock(css: string, query: RegExp) {
  const match = query.exec(css);
  if (!match) throw new Error(`Missing media query ${query.source}`);
  const openingBrace = css.indexOf("{", match.index + match[0].length);
  let depth = 0;
  for (let index = openingBrace; index < css.length; index += 1) {
    if (css[index] === "{") depth += 1;
    if (css[index] === "}") depth -= 1;
    if (depth === 0) return css.slice(openingBrace + 1, index);
  }
  throw new Error(`Unclosed media query ${query.source}`);
}

describe("Aperture semantic typography contract", () => {
  it("attaches generated font variables to the document root without naming hashes", () => {
    const fonts = source("fonts.ts");
    const layout = source("layout.tsx");

    expect(fonts).toMatch(/variable:\s*["']--font-aperture-reading["']/);
    expect(fonts).toMatch(/variable:\s*["']--font-aperture-editorial["']/);
    expect(fonts).toMatch(/variable:\s*["']--font-aperture-data["']/);
    expect(fonts).toMatch(
      /export const apertureFontVariables\s*=\s*\[[\s\S]*reading\.variable[\s\S]*editorial\.variable[\s\S]*data\.variable[\s\S]*\]\.join\(["'] ["']\)/,
    );
    expect(layout).toMatch(
      /<html\s+lang=\{brand\.locale\.default_locale\}\s+dir=\{rtlLanguages\.has\(language\)\s*\?\s*["']rtl["']\s*:\s*["']ltr["']\}\s+className=\{apertureFontVariables\}\s+style=\{brandStyle\}>/,
    );
  });

  it("loads the semantic layer after every legacy global stylesheet", () => {
    const layout = source("layout.tsx");
    const cssImports = [...layout.matchAll(/import\s+["']([^"']+\.css)["'];?/g)].map(
      (match) => match[1],
    );

    expect(cssImports.at(-1)).toBe("./typography.css");
    for (const legacy of [
      "./styles.css",
      "./navbar.css",
      "./auth.css",
      "./account-chooser.css",
      "./universal-search.css",
      "./federated-search.css",
      "./instant-search.css",
      "./card-fixes.css",
    ]) {
      expect(cssImports.indexOf(legacy)).toBeGreaterThanOrEqual(0);
      expect(cssImports.indexOf(legacy)).toBeLessThan(
        cssImports.indexOf("./typography.css"),
      );
    }
  });

  it("keeps semantic families, compatibility aliases, and readable size floors", () => {
    const typography = source("typography.css");

    for (const role of ["display", "editorial", "body", "ui", "metadata", "data"]) {
      expect(customProperty(typography, `font-${role}`)).toBeTruthy();
    }
    expect(customProperty(typography, "font-sans")).toBe("var(--font-ui)");
    expect(customProperty(typography, "font-serif")).toBe("var(--font-display)");
    expect(customProperty(typography, "font-mono")).toBe("var(--font-data)");

    expect(remToPixels(customProperty(typography, "type-body"))).toBeGreaterThanOrEqual(16);
    expect(remToPixels(customProperty(typography, "type-ui"))).toBeGreaterThanOrEqual(15);
    expect(remToPixels(customProperty(typography, "type-meta"))).toBeGreaterThanOrEqual(14);
    expect(
      remToPixels(customProperty(typography, "studio-type-meta")),
    ).toBeGreaterThanOrEqual(13);

    const mobile = mediaBlock(
      typography,
      /@media\s*\(max-width:\s*700px\)/,
    );
    expect(mobile).toMatch(
      /:is\([\s\S]*\.studio-shell[\s\S]*\)\s*:is\(input,\s*select,\s*textarea\)\s*\{[\s\S]*font-size:\s*1rem\s*!important/,
    );
  });

  it("places readable Signal Run interaction overrides after responsive reductions", () => {
    const ball = source("game/ball-interface.module.css");
    const overrideStart = ball.lastIndexOf("Readable interaction copy");

    expect(overrideStart).toBeGreaterThan(
      ball.lastIndexOf("@media (max-height: 480px) and (orientation: landscape)"),
    );

    const minimums = new Map<string, number>([
      [".exitButton span", 14],
      [".pauseButton strong", 14],
      [".secondaryAction", 14],
      [".textAction", 14],
      [".countdownControl", 14],
      [".controlHint", 14],
      [".modalLead > p:not(.eyebrow)", 14],
      [".optionButton span", 14],
      [".optionButton strong", 14],
    ]);

    for (const [selector, minimum] of minimums) {
      const value = ruleDeclarations(ball, selector).get("font-size");
      expect(value, selector).toBeDefined();
      expect(remToPixels(value!), selector).toBeGreaterThanOrEqual(minimum);
    }
  });

  it("preserves scrollable auth layouts on phones and short landscape screens", () => {
    const auth = source("auth.css");
    const mobile = mediaBlock(auth, /@media\s*\(max-width:\s*760px\)/);
    const shortLandscape = mediaBlock(
      auth,
      /@media\s*\(max-height:\s*520px\)\s*and\s*\(orientation:\s*landscape\)/,
    );

    const mobileShell = ruleDeclarations(mobile, ".viewer-auth-shell");
    expect(mobileShell.get("display")).toBe("block");
    expect(mobileShell.get("min-height")).toBe("100dvh");
    expect(mobileShell.get("overflow-y")).toBe("auto");
    expect(mobileShell.get("perspective")).toBe("none");

    const mobileCard = ruleDeclarations(mobile, ".viewer-auth-card");
    expect(mobileCard.get("height")).toBe("auto");
    expect(mobileCard.get("min-height")).toBe("0");

    const landscapeShell = ruleDeclarations(shortLandscape, ".viewer-auth-shell");
    expect(landscapeShell.get("min-height")).toBe("100dvh");
    expect(landscapeShell.get("overflow-y")).toBe("auto");

    const landscapeCard = ruleDeclarations(shortLandscape, ".viewer-auth-card");
    expect(landscapeCard.get("height")).toBe("auto");
    expect(landscapeCard.get("min-height")).toBe("0");
    expect(ruleDeclarations(shortLandscape, ".viewer-auth-card h1").get("font-size"))
      .toMatch(/^clamp\(/);
  });
});
