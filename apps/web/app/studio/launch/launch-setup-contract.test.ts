import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const launchRoot = join(process.cwd(), "app", "studio", "launch");

describe("white-label launch boundary", () => {
  it("loads only through the authenticated Studio shell", () => {
    const page = readFileSync(join(launchRoot, "page.tsx"), "utf8");
    expect(page).toContain("requireAdminSession()");
    expect(page).toContain("adminCatalogFetch<LaunchSetupRecord>(\"/admin/site/brand\")");
    expect(page).toContain("<StudioShell");
    expect(page).toContain("setupOnly={!setup.published_at}");
  });

  it("renders the preview primary action with the derived on-accent token", () => {
    const wizard = readFileSync(join(launchRoot, "launch-setup-wizard.tsx"), "utf8");
    const styles = readFileSync(join(launchRoot, "launch-setup.module.css"), "utf8");
    expect(wizard).toContain('"--launch-on-accent": onAccent');
    expect(styles).toMatch(/\.previewButton[^}]+color:\s*var\(--launch-on-accent\)/);
  });

  it("uses revisioned private draft and explicit publish endpoints", () => {
    const actions = readFileSync(join(launchRoot, "actions.ts"), "utf8");
    expect(actions).toContain('adminCatalogFetch<LaunchSetupRecord>("/admin/site/brand"');
    expect(actions).toContain('adminCatalogFetch<LaunchSetupRecord>("/admin/site/brand/publish"');
    expect(actions).toContain("expected_revision=${revision}");
    expect(actions).not.toMatch(/https?:\/\/[^"']+logo/i);
  });

  it("keeps AI copy assistance owner-invoked, provider-neutral, and separate from saving", () => {
    const actions = readFileSync(join(launchRoot, "actions.ts"), "utf8");
    const wizard = readFileSync(join(launchRoot, "launch-setup-wizard.tsx"), "utf8");
    expect(actions).toContain('adminCatalogFetch<{ generated_by?: unknown; suggestions?: unknown[] }>("/admin/site/brand/assist-copy"');
    expect(wizard).toContain('type="button" disabled={assistantPending} onClick={requestCopySuggestions}');
    expect(wizard).toContain("disabled={!available || pending || assistantPending}");
    expect(wizard).toContain('type="submit" disabled={pending || assistantPending}');
    expect(wizard).toContain("Your draft has not changed");
    expect(wizard).toContain("business name, current compact name, tagline, introduction, audience, voice, and optional note are sent to OpenAI");
    expect(wizard).toContain("Studio does not add the generation request or returned options to your saved brand record.");
    expect(wizard.indexOf("When you ask for ideas")).toBeLessThan(wizard.indexOf("<div className={styles.assistantCommand}>"));
    expect(wizard).not.toMatch(/Anthropic|Gemini/i);
  });

  it("proxies the authenticated logo preview without caching it publicly", () => {
    const route = readFileSync(join(launchRoot, "logo", "route.ts"), "utf8");
    expect(route).toContain("requireAdminSession()");
    expect(route).toContain('"Cache-Control": "private, no-store"');
    expect(route).toContain("studioEdgeHeaders()");
  });

  it("builds marks from a finite recipe without accepting SVG or external artwork", () => {
    const wizard = readFileSync(join(launchRoot, "launch-setup-wizard.tsx"), "utf8");
    const atelier = readFileSync(join(launchRoot, "logo-atelier.tsx"), "utf8");
    const recipe = readFileSync(join(process.cwd(), "app", "lib", "generated-logo.ts"), "utf8");
    const renderer = readFileSync(join(process.cwd(), "app", "components", "generated-logo.tsx"), "utf8");
    const combined = `${atelier}\n${recipe}\n${renderer}`;

    expect(wizard).not.toContain('type="file"');
    expect(recipe).toContain('renderer_version: typeof GENERATED_LOGO_RENDERER_VERSION');
    expect(recipe).toContain('"A", "B", "C"');
    expect(recipe).toContain('"a", "b", "c"');
    expect(combined).not.toMatch(/dangerouslySetInnerHTML|foreignObject|data:image|blob:|image\/svg\+xml/);
    expect(recipe).not.toMatch(/variant:\s*"aperture"/);
  });
});
