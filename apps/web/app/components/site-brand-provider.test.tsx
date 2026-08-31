import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  SiteBrandProvider,
  SiteBrandWordmark,
  useSiteBrand,
} from "@/app/components/site-brand-provider";
import type { SiteBrand } from "@/app/lib/site-brand";

const customBrand: SiteBrand = {
  schema_version: 1,
  revision: 4,
  business_name: "Northstar Pictures",
  short_name: "Northstar",
  tagline: "Stories that point home.",
  description: "A new place for cinema.",
  logo_url: null,
  logo_revision: null,
  logo_mark: null,
  palette: {
    accent: "#ca8a04",
    accent_hover: "#eab308",
    on_accent: "#000000",
    surface: "#090806",
    surface_elevated: "#1c1917",
    text: "#fafaf9",
    text_muted: "#b8b3aa",
  },
  locale: {
    default_locale: "en-CA",
    home_market: "CA",
    currency: "CAD",
  },
  published_at: "2026-08-23T04:05:06Z",
};

function BrandConsumer() {
  const brand = useSiteBrand();
  return <output aria-label="brand-name">{brand.business_name}</output>;
}

describe("SiteBrandProvider", () => {
  it("provides the safe fallback when a surface is rendered outside the root provider", () => {
    render(<><SiteBrandWordmark /><BrandConsumer /></>);

    expect(screen.getByText("APERTURE")).toBeInTheDocument();
    expect(screen.getByLabelText("brand-name")).toHaveTextContent("Aperture");
  });

  it("makes one published snapshot available to every client consumer", () => {
    render(
      <SiteBrandProvider brand={customBrand}>
        <SiteBrandWordmark />
        <BrandConsumer />
      </SiteBrandProvider>,
    );

    expect(screen.getByText("NORTHSTAR")).toBeInTheDocument();
    expect(screen.getByLabelText("brand-name")).toHaveTextContent("Northstar Pictures");
    expect(screen.queryByText("APERTURE")).not.toBeInTheDocument();
  });
});
