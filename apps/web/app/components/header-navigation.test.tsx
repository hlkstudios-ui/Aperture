import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HeaderNavigation } from "./header-navigation";
import { SiteBrandProvider } from "./site-brand-provider";
import { DEFAULT_SITE_BRAND, type SiteBrand } from "../lib/site-brand";

const navigation = vi.hoisted(() => ({
  pathname: "/",
  push: vi.fn(),
}));

const customBrand = {
  ...DEFAULT_SITE_BRAND,
  revision: 9,
  business_name: "Northstar Pictures",
  short_name: "Northstar",
  tagline: "Stories that point home.",
  published_at: "2026-08-23T04:05:06Z",
} satisfies SiteBrand;

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({ push: navigation.push }),
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    prefetch,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & {
    children: ReactNode;
    href: string;
    prefetch?: boolean;
  }) => {
    void prefetch;
    return <a href={href} {...props}>{children}</a>;
  },
}));

beforeEach(() => {
  navigation.pathname = "/";
  navigation.push.mockReset();
});

afterEach(() => {
  cleanup();
  document.documentElement.classList.remove("aperture-nav-open");
});

describe("HeaderNavigation", () => {
  it("uses the published brand across its visible labels and accessible names", () => {
    render(
      <SiteBrandProvider brand={customBrand}>
        <HeaderNavigation recommendationsEnabled />
      </SiteBrandProvider>,
    );

    expect(screen.getByRole("link", { name: "Northstar Pictures home" })).toHaveTextContent("NORTHSTAR");
    expect(screen.getByRole("button", { name: "My Northstar" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Search Northstar Pictures" })).not.toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "My Northstar" }));
    expect(screen.getByRole("heading", { name: "My Northstar" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "My Northstar" })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("Aperture");
  });

  it("renders the published generated mark without exposing a logo URL", () => {
    render(
      <SiteBrandProvider brand={{
        ...customBrand,
        logo_url: null,
        logo_revision: 0,
        logo_mark: { renderer_version: 1, glyph: "n", variant: "orbit" },
      }}>
        <HeaderNavigation recommendationsEnabled />
      </SiteBrandProvider>,
    );

    expect(document.querySelector('.cinematic-wordmark [data-logo-glyph="n"][data-logo-variant="orbit"]')).not.toBeNull();
    expect(document.querySelector(".cinematic-wordmark .has-generated-logo")).not.toBeNull();
  });

  it("marks the matching parent route as the current page", () => {
    navigation.pathname = "/movies/interstellar";
    render(<HeaderNavigation recommendationsEnabled />);

    expect(screen.getByRole("link", { name: "Movies" })).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { name: "Home" }).every(
      (link) => !link.hasAttribute("aria-current"),
    )).toBe(true);
  });

  it("keeps the Discover, library and account menus mutually exclusive", () => {
    render(<HeaderNavigation recommendationsEnabled />);

    const discover = screen.getByRole("button", { name: "Discover" });
    const library = screen.getByRole("button", { name: "My Aperture" });
    const account = screen.getByRole("button", { name: "Profile and account" });

    fireEvent.click(discover);
    expect(discover).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("heading", { name: "Find the right story for tonight." })).toBeInTheDocument();

    fireEvent.click(library);
    expect(discover).toHaveAttribute("aria-expanded", "false");
    expect(library).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("heading", { name: "Find the right story for tonight." })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "My Aperture" })).toBeInTheDocument();

    fireEvent.click(account);
    expect(library).toHaveAttribute("aria-expanded", "false");
    expect(account).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("heading", { name: "My Aperture" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Viewer space" })).toBeInTheDocument();
  });

  it("closes an open menu with Escape and returns focus to its trigger", () => {
    render(<HeaderNavigation recommendationsEnabled />);
    const discover = screen.getByRole("button", { name: "Discover" });

    fireEvent.click(discover);
    fireEvent.keyDown(document, { key: "Escape" });

    expect(discover).toHaveFocus();
    expect(discover).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("heading", { name: "Find the right story for tonight." })).not.toBeInTheDocument();
  });

  it("moves keyboard focus into each disclosed desktop menu", async () => {
    render(<HeaderNavigation recommendationsEnabled />);
    const discover = screen.getByRole("button", { name: "Discover" });

    fireEvent.keyDown(discover, { key: "ArrowDown" });
    await waitFor(() => expect(screen.getByRole("link", { name: /Trending now/ })).toHaveFocus());

    fireEvent.keyDown(document, { key: "Escape" });
    const library = screen.getByRole("button", { name: "My Aperture" });
    fireEvent.click(library, { detail: 0 });
    const libraryMenu = screen.getByRole("navigation", { name: "My Aperture" });
    await waitFor(() => expect(within(libraryMenu).getByRole("link", { name: /My List/ })).toHaveFocus());
  });

  it("opens search with the slash shortcut except while an input is being edited", () => {
    render(<>
      <HeaderNavigation recommendationsEnabled />
      <input aria-label="Edit title" />
    </>);

    fireEvent.keyDown(document.body, { key: "/" });
    expect(navigation.push).toHaveBeenCalledOnce();
    expect(navigation.push).toHaveBeenCalledWith("/search");

    navigation.push.mockClear();
    const input = screen.getByRole("textbox", { name: "Edit title" });
    input.focus();
    fireEvent.keyDown(input, { key: "/" });
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("shows personalized discovery only when its feature flag is enabled", () => {
    const { rerender } = render(<HeaderNavigation recommendationsEnabled={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Discover" }));
    expect(screen.queryByRole("link", { name: /For you/ })).not.toBeInTheDocument();

    rerender(<HeaderNavigation recommendationsEnabled />);
    expect(screen.getByRole("link", { name: /For you/ })).toHaveAttribute("href", "/discover");
  });

  it("does not disclose the owner Studio in public navigation", () => {
    render(<HeaderNavigation recommendationsEnabled />);
    fireEvent.click(screen.getByRole("button", { name: "Profile and account" }));
    expect(screen.queryByRole("link", { name: /studio/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    expect(screen.queryByRole("link", { name: /studio/i })).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("Aperture Studio");
  });

  it("exposes each navigation group as a named navigation landmark", () => {
    render(<HeaderNavigation recommendationsEnabled />);

    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Quick navigation" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Discover" }));
    expect(screen.getByRole("navigation", { name: "Watch now" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Explore deeper" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "My Aperture" }));
    expect(screen.getByRole("navigation", { name: "My Aperture" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Watch now" })).not.toBeInTheDocument();
  });
});
