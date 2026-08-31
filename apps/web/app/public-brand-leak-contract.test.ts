import { existsSync, readFileSync, readdirSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { describe, expect, it } from "vitest";

type AllowlistedOccurrence = {
  path: string;
  line: RegExp;
  reason: string;
};

const allowlist: AllowlistedOccurrence[] = [
  {
    path: "lib/site-brand.ts",
    line: /^\s*business_name:\s*"Aperture",\s*$/,
    reason: "safe fallback while the public brand endpoint is unavailable",
  },
  {
    path: "lib/site-brand.ts",
    line: /^\s*short_name:\s*"Aperture",\s*$/,
    reason: "safe fallback while the public brand endpoint is unavailable",
  },
  {
    path: "fonts.ts",
    line: /^\s*\* Aperture's type families are defined once/,
    reason: "source documentation for intentionally stable internal font tokens",
  },
  {
    path: "game/ball-simulation.ts",
    line: /^\s*\* Deterministic fixed-step rules for Aperture's/,
    reason: "non-rendered source documentation",
  },
  {
    path: "game/physics/rapier-loader.ts",
    line: /adding Rapier's inlined WASM to Aperture's shared bundle/,
    reason: "non-rendered source documentation",
  },
  {
    path: "api/gateway/[[...path]]/route.ts",
    line: /^\s*headers\.set\("X-Aperture-(?:Public-Origin|Edge-Secret)",/,
    reason: "server-only trusted-edge protocol headers",
  },
  {
    path: "lib/account.ts",
    line: /^\s*"X-Aperture-(?:Public-Origin|Edge-Secret)":/,
    reason: "server-only trusted-edge protocol headers",
  },
];

function productionSources(root: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const absolute = resolve(root, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "studio" || entry.name === "__test__") continue;
      files.push(...productionSources(absolute));
      continue;
    }
    if (!/\.(?:ts|tsx)$/.test(entry.name) || /\.test\.(?:ts|tsx)$/.test(entry.name)) continue;
    files.push(absolute);
  }
  return files;
}

describe("public white-label source boundary", () => {
  it("has no hard-coded visible vendor name outside the documented fallback/internal allowlist", () => {
    const appRoot = resolve(process.cwd(), "app");
    const unexpected: string[] = [];

    for (const file of productionSources(appRoot)) {
      const sourcePath = relative(appRoot, file).split(sep).join("/");
      for (const [index, line] of readFileSync(file, "utf8").split(/\r?\n/).entries()) {
        if (!/\b(?:Aperture|APERTURE)\b/.test(line)) continue;
        const allowed = allowlist.some((entry) => entry.path === sourcePath && entry.line.test(line));
        if (!allowed) unexpected.push(`${sourcePath}:${index + 1}: ${line.trim()}`);
      }
    }

    expect(unexpected, `Unexpected public vendor-name leaks:\n${unexpected.join("\n")}`).toEqual([]);
  });

  it("uses the runtime icon route instead of a static vendor favicon", () => {
    const appRoot = resolve(process.cwd(), "app");
    const iconSource = readFileSync(resolve(appRoot, "icon.tsx"), "utf8");
    const appleIconSource = readFileSync(resolve(appRoot, "apple-icon.tsx"), "utf8");
    const rendererSource = readFileSync(resolve(appRoot, "lib", "site-brand-icon-image.tsx"), "utf8");

    expect(existsSync(resolve(appRoot, "icon.svg"))).toBe(false);
    expect(iconSource).toContain("getSiteBrand()");
    expect(iconSource).toContain("siteBrandIconImage(brand");
    expect(appleIconSource).toContain("width: 180");
    expect(rendererSource).toContain("siteBrandInitials(brand)");
    expect(iconSource).not.toContain(">A<");
    expect(appleIconSource).not.toContain(">A<");
  });
});
