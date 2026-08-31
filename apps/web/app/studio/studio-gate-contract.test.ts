import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const studioRoot = join(process.cwd(), "app", "studio");

function pageFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return pageFiles(path);
    return entry.name === "page.tsx" ? [path] : [];
  });
}

describe("Studio first-run server boundary", () => {
  it("routes every operational workspace page through the server StudioShell gate", () => {
    const missingGate = pageFiles(studioRoot)
      .filter((path) => relative(studioRoot, path).replaceAll("\\", "/") !== "login/page.tsx")
      .filter((path) => !readFileSync(path, "utf8").includes("StudioShell"))
      .map((path) => relative(studioRoot, path));

    expect(missingGate).toEqual([]);
  });

  it("does not put login or development access behind the operational shell", () => {
    const login = readFileSync(join(studioRoot, "login", "page.tsx"), "utf8");
    const developmentAccess = readFileSync(join(studioRoot, "dev-access", "route.ts"), "utf8");
    expect(login).not.toContain("StudioShell");
    expect(developmentAccess).not.toContain("StudioShell");
  });
});
