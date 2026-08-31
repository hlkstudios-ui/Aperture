import { Children, isValidElement, type CSSProperties, type ReactElement, type ReactNode } from "react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_SITE_BRAND, type SiteBrand } from "@/app/lib/site-brand";

const brandLoader = vi.hoisted(() => vi.fn());

vi.mock("@/app/lib/site-brand-server", () => ({
  getSiteBrand: brandLoader,
}));

vi.mock("@/app/fonts", () => ({
  apertureFontVariables: "font-reading font-editorial font-data",
}));

vi.mock("next/og", () => ({
  ImageResponse: class MockImageResponse {
    element: ReactElement;
    options: { width: number; height: number };

    constructor(element: ReactElement, options: { width: number; height: number }) {
      this.element = element;
      this.options = options;
    }
  },
}));

import AppleIcon, { dynamic as appleIconDynamic } from "@/app/apple-icon";
import Icon, { contentType, dynamic as iconDynamic, size } from "@/app/icon";
import RootLayout, { dynamic as layoutDynamic, generateMetadata } from "@/app/layout";

const customBrand: SiteBrand = {
  ...DEFAULT_SITE_BRAND,
  revision: 21,
  business_name: "Northstar Pictures",
  short_name: "North Star",
  tagline: "Stories that point home.",
  description: "Independent cinema for curious nights.",
  logo_url: "/site/brand/logo?revision=21",
  logo_revision: 21,
  palette: {
    accent: "#14b8a6",
    accent_hover: "#2dd4bf",
    on_accent: "#000000",
    surface: "#06110f",
    surface_elevated: "#10201d",
    text: "#f0fdfa",
    text_muted: "#9db8b2",
  },
  locale: {
    default_locale: "ar-AE",
    home_market: "AE",
    currency: "AED",
  },
  published_at: "2026-08-23T04:05:06Z",
};

beforeEach(() => {
  brandLoader.mockReset();
  brandLoader.mockResolvedValue(customBrand);
});

describe("root site-brand integration", () => {
  it("defers every published-brand surface to the running application", () => {
    expect(layoutDynamic).toBe("force-dynamic");
    expect(iconDynamic).toBe("force-dynamic");
    expect(appleIconDynamic).toBe("force-dynamic");
    expect(AppleIcon).toBeTypeOf("function");
  });

  it("builds public metadata from the published business identity", async () => {
    const metadata = await generateMetadata();

    expect(metadata.applicationName).toBe("Northstar Pictures");
    expect(metadata.description).toBe("Independent cinema for curious nights.");
    expect(metadata.title).toMatchObject({
      default: "Northstar Pictures",
      template: expect.stringContaining("Northstar Pictures"),
    });
    expect(metadata.icons).toEqual({
      icon: expect.stringMatching(/\/site\/brand\/logo\?revision=21$/),
      shortcut: expect.stringMatching(/\/site\/brand\/logo\?revision=21$/),
      apple: expect.stringMatching(/\/site\/brand\/logo\?revision=21$/),
    });
  });

  it("hydrates locale, direction, palette and client consumers from one snapshot", async () => {
    const root = await RootLayout({ children: <main>Feature</main> });
    const rootProps = root.props as {
      lang: string;
      dir: string;
      className: string;
      style: CSSProperties & Record<`--${string}`, string>;
      children: ReactNode;
    };

    expect(root.type).toBe("html");
    expect(rootProps.lang).toBe("ar-AE");
    expect(rootProps.dir).toBe("rtl");
    expect(rootProps.className).toContain("font-reading");
    expect(rootProps.style["--brand-accent"]).toBe("#14b8a6");
    expect(rootProps.style["--brand-on-accent"]).toBe("#000000");
    expect(rootProps.style["--brand-surface"]).toBe("#06110f");
    expect(rootProps.style["--brand-text"]).toBe("#f0fdfa");

    const body = Children.toArray(rootProps.children).find(
      (child) => isValidElement(child) && child.type === "body",
    ) as ReactElement<{ children: ReactNode }>;
    const provider = body.props.children as ReactElement<{ brand: SiteBrand }>;
    expect(provider.props.brand).toBe(customBrand);
  });

  it("uses the derived on-accent token across public primary actions", () => {
    const styles = readFileSync(join(process.cwd(), "app", "styles.css"), "utf8");
    const footer = readFileSync(join(process.cwd(), "app", "footer.css"), "utf8");
    expect(styles).toMatch(/:where\(\.primary,\.studio-primary\)[^{]*\{[^}]*color:var\(--on-accent\)/);
    expect(styles).toMatch(/\.player-state button\{color:var\(--on-accent\)\}/);
    expect(footer).toMatch(/\.closing-iris__primary\s*\{[^}]*color:\s*var\(--brand-on-accent/);
  });

  it("keeps generated marks on the same validated surfaces used by their previews", () => {
    const navbar = readFileSync(join(process.cwd(), "app", "navbar.css"), "utf8");
    const footer = readFileSync(join(process.cwd(), "app", "footer.css"), "utf8");
    const launch = readFileSync(join(process.cwd(), "app", "studio", "launch", "launch-setup.module.css"), "utf8");

    expect(navbar).toMatch(/--aperture-nav-surface:\s*var\(--brand-surface/);
    expect(navbar).toMatch(/--aperture-nav-elevated:\s*var\(--brand-surface-elevated/);
    expect(footer).toMatch(/\.closing-iris__ledger\s*\{[^}]*background:\s*var\(--footer-surface\)/s);
    expect(launch).toMatch(/\.logoVariantPicker label\s*\{[^}]*background:\s*var\(--atelier-elevated\)/s);
    expect(launch).toMatch(/\.signatureGeneratedLogo\s*\{[^}]*color:\s*var\(--atelier-accent/);
  });

  it("generates a runtime favicon from the same published name and palette", async () => {
    const response = await Icon() as unknown as {
      element: ReactElement;
      options: { width: number; height: number };
    };

    expect(contentType).toBe("image/png");
    expect(response.options).toEqual(size);
    render(response.element);
    expect(screen.getByText("NS")).toBeInTheDocument();
    expect(screen.getByText("NS")).toHaveStyle({
      background: "linear-gradient(145deg, #2dd4bf, #14b8a6)",
    });
  });

  it("renders a revisioned generated mark in metadata and the runtime favicon", async () => {
    brandLoader.mockResolvedValue({
      ...customBrand,
      logo_url: null,
      logo_revision: 0,
      logo_mark: { renderer_version: 1, glyph: "n", variant: "prism" },
    });

    const metadata = await generateMetadata();
    expect(metadata.icons).toEqual({
      icon: "/icon?revision=21",
      shortcut: "/icon?revision=21",
      apple: "/apple-icon?revision=21",
    });

    const response = await Icon() as unknown as { element: ReactElement };
    render(response.element);
    expect(document.querySelector('[data-logo-glyph="n"][data-logo-variant="prism"]')).not.toBeNull();
    expect(document.querySelector("svg text")).toBeNull();
    expect(document.querySelector('svg path[data-logo-letter="n"]')).toHaveAttribute("d");
  });
});
