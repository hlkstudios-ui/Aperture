import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StudioShell, studioAccessRequiresLaunch } from "./studio-shell";

vi.mock("./actions", () => ({ signOutAdmin: vi.fn() }));

const studioMocks = vi.hoisted(() => ({ fetch: vi.fn(), redirect: vi.fn() }));

vi.mock("@/app/lib/admin-catalog", () => ({ adminCatalogFetch: studioMocks.fetch }));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => {
    studioMocks.redirect(path);
    throw new Error(`NEXT_REDIRECT:${path}`);
  },
}));

afterEach(() => {
  vi.unstubAllEnvs();
  studioMocks.fetch.mockReset();
  studioMocks.redirect.mockReset();
});

describe("StudioShell first-run navigation", () => {
  it("offers only launch setup and sign out before the first publication", async () => {
    render(await StudioShell({
      admin: { email: "owner@example.test" },
      active: "launch setup",
      eyebrow: "White-label premiere",
      title: "Launch setup",
      setupOnly: true,
      children: <p>Wizard</p>,
    }));

    expect(screen.getAllByRole("link", { name: /Launch Setup/ })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: /Legal & policy/ })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: /Customer payments/ })).toHaveLength(2);
    expect(screen.queryByRole("link", { name: /Dashboard/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Uploads/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Sign out" })).toHaveLength(2);
  });

  it("redirects an unpublished operational shell before returning its children", async () => {
    vi.stubEnv("APP_ENV", "production");
    studioMocks.fetch.mockResolvedValue({ published_at: null });

    await expect(StudioShell({
      admin: { email: "owner@example.test" },
      active: "uploads",
      eyebrow: "Production",
      title: "Uploads",
      children: <button type="button">Delete asset</button>,
    })).rejects.toThrow("NEXT_REDIRECT:/studio/launch");
    expect(studioMocks.redirect).toHaveBeenCalledWith("/studio/launch");
  });

  it("keeps the test-only compatibility seam explicit and isolated", () => {
    expect(studioAccessRequiresLaunch({
      setupOnly: false,
      publishedAt: null,
      appEnv: "test",
    })).toBe(false);
    expect(studioAccessRequiresLaunch({
      setupOnly: false,
      publishedAt: null,
      appEnv: "production",
    })).toBe(true);
  });

  it("includes Explore in both operational navigation surfaces", async () => {
    vi.stubEnv("APP_ENV", "test");

    render(await StudioShell({
      admin: { email: "owner@example.test" },
      active: "explore",
      eyebrow: "Programming",
      title: "Explore",
      children: <p>Explore editor</p>,
    }));

    const links = screen.getAllByRole("link", { name: /Explore/ });
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/studio/explore");
      expect(link).toHaveAttribute("aria-current", "page");
    }
  });

  it("includes Domains in both operational navigation surfaces", async () => {
    vi.stubEnv("APP_ENV", "test");

    render(await StudioShell({
      admin: { email: "owner@example.test" },
      active: "domains",
      eyebrow: "Customer access",
      title: "Domains",
      children: <p>Domain manager</p>,
    }));

    const links = screen.getAllByRole("link", { name: /Domains/ });
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/studio/domains");
      expect(link).toHaveAttribute("aria-current", "page");
    }
  });

  it("includes Legal & policy in both operational navigation surfaces", async () => {
    vi.stubEnv("APP_ENV", "test");

    render(await StudioShell({
      admin: { email: "owner@example.test" },
      active: "legal & policy",
      eyebrow: "Owner workspace",
      title: "Legal & policy",
      children: <p>Private legal input form</p>,
    }));

    const links = screen.getAllByRole("link", { name: /Legal & policy/ });
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/studio/legal-policy");
      expect(link).toHaveAttribute("aria-current", "page");
    }
  });

  it("includes Customer payments in both operational navigation surfaces", async () => {
    vi.stubEnv("APP_ENV", "test");

    render(await StudioShell({
      admin: { email: "owner@example.test" },
      active: "customer payments",
      eyebrow: "Viewer monetization",
      title: "Customer payments",
      children: <p>Provider setup</p>,
    }));

    const links = screen.getAllByRole("link", { name: /Customer payments/ });
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/studio/monetization");
      expect(link).toHaveAttribute("aria-current", "page");
    }
  });
});
