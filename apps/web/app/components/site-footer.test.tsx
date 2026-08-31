import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiteFooter } from "@/app/components/site-footer";
import { DEFAULT_SITE_BRAND, type SiteBrand } from "@/app/lib/site-brand";

const customBrand = {
  ...DEFAULT_SITE_BRAND,
  revision: 12,
  business_name: "Northstar Pictures",
  short_name: "Northstar",
  tagline: "Stories that point home.",
  published_at: "2026-08-23T04:05:06Z",
} satisfies SiteBrand;

describe("SiteFooter", () => {
  it("carries the published identity through its lockup, directory and personal library", () => {
    render(<SiteFooter brand={customBrand} />);

    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: "Northstar Pictures home" })).toHaveTextContent("Northstar");
    expect(within(footer).getByRole("navigation", { name: "Continue exploring Northstar Pictures" })).toBeInTheDocument();
    expect(within(footer).getByRole("navigation", { name: "Northstar Pictures directory" })).toBeInTheDocument();
    expect(within(footer).getByRole("heading", { name: "My Northstar" })).toBeInTheDocument();
    expect(within(footer).getByText("Stories that point home.")).toBeInTheDocument();
    expect(footer).not.toHaveTextContent("Aperture");
  });

  it("carries a generated mark into the public footer lockup", () => {
    render(<SiteFooter brand={{
      ...customBrand,
      logo_url: null,
      logo_revision: 0,
      logo_mark: { renderer_version: 1, glyph: "N", variant: "beam" },
    }} />);

    expect(document.querySelector('.closing-iris__generated-mark [data-logo-glyph="N"][data-logo-variant="beam"]')).not.toBeNull();
  });

  it("ends the public experience with useful, real destinations", () => {
    render(<SiteFooter />);

    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: "Aperture home" })).toHaveAttribute("href", "/");
    expect(within(footer).getByRole("navigation", { name: "Continue exploring Aperture" })).toBeInTheDocument();

    const directory = within(footer).getByRole("navigation", { name: "Aperture directory" });
    for (const [name, href] of [
      ["Movies", "/movies"],
      ["Series", "/series"],
      ["Trending", "/trending"],
      ["Browse", "/browse"],
      ["Collections", "/collections"],
      ["Signal Run", "/game"],
      ["My List", "/my-list"],
      ["Passport", "/passport"],
      ["Account", "/account"],
    ]) {
      expect(within(directory).getByRole("link", { name })).toHaveAttribute("href", href);
    }
    expect(within(footer).getByRole("link", { name: "Back to top" })).toHaveAttribute("href", "#main-content");
    expect(within(footer).queryAllByRole("region")).toHaveLength(0);
  });

  it("returns keyboard focus to the main content", () => {
    const main = document.createElement("div");
    main.id = "main-content";
    main.tabIndex = -1;
    main.scrollIntoView = () => undefined;
    document.body.append(main);
    render(<SiteFooter />);

    fireEvent.click(screen.getByRole("link", { name: "Back to top" }));
    expect(main).toHaveFocus();
    main.remove();
  });

  it("does not expose owner or provider infrastructure", () => {
    render(<SiteFooter />);

    expect(screen.queryByText(/studio/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/tmdb/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/movie api/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/data credits/i)).not.toBeInTheDocument();
  });

  it("keeps one global render seam and progressive motion fallbacks", () => {
    const root = resolve(process.cwd(), "app");
    const layout = readFileSync(resolve(root, "layout.tsx"), "utf8");
    const titlePage = readFileSync(resolve(root, "titles", "[kind]", "[id]", "page.tsx"), "utf8");
    const css = readFileSync(resolve(root, "footer.css"), "utf8");
    const footerControl = readFileSync(resolve(root, "components", "footer-back-to-top.tsx"), "utf8");
    const privateLayout = readFileSync(resolve(root, "studio", "layout.tsx"), "utf8");

    expect(layout.match(/<SiteFooter\s+brand=\{brand\}\s*\/>/g)).toHaveLength(1);
    expect(titlePage).not.toContain("SiteFooter");
    expect(css).toContain(".closing-iris--motion-ready");
    expect(footerControl).toContain("IntersectionObserver");
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
    expect(css).toMatch(/body:has\(\[data-hide-public-footer\]\)/);
    expect(css).not.toMatch(/studio-(?:shell|route-loading)/);
    expect(privateLayout).toContain("data-hide-public-footer");
    expect(css).toMatch(/body:has\(\.watch-page\)/);
    expect(css).toMatch(/min-height:\s*44px/);
  });
});
