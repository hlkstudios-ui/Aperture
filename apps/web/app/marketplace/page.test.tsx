import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headerValues, notFoundMock } = vi.hoisted(() => ({
  headerValues: new Map<string, string>(),
  notFoundMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: vi.fn(async () => ({
    get: (name: string) => headerValues.get(name.toLowerCase()) ?? null,
  })),
}));

vi.mock("next/navigation", () => ({
  notFound: notFoundMock,
}));

import MarketplacePage from "./page";

beforeEach(() => {
  notFoundMock.mockImplementation(() => {
    throw new Error("NEXT_NOT_FOUND");
  });
});

afterEach(() => {
  headerValues.clear();
  notFoundMock.mockReset();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("marketplace server boundary", () => {
  it("loads the registry without caching on the canonical Apertures host", async () => {
    vi.stubEnv("PLATFORM_CONTROL_PLANE_ENABLED", "true");
    vi.stubEnv("WEB_ORIGIN", "https://apertures.online");
    headerValues.set("host", "apertures.online");
    headerValues.set("x-forwarded-proto", "https");
    const fetchMock = vi.fn(async (_input: string | URL | Request, _init?: RequestInit) => {
      void _input;
      void _init;
      return Response.json({ schema_version: 1, items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(await MarketplacePage());

    expect(screen.getByRole("heading", { name: /Your identity/i })).toBeInTheDocument();
    expect(screen.getByText("No templates are published yet.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ cache: "no-store" });
    expect(notFoundMock).not.toHaveBeenCalled();
  });

  it("does not expose the platform marketplace on a tenant custom domain", async () => {
    vi.stubEnv("PLATFORM_CONTROL_PLANE_ENABLED", "true");
    vi.stubEnv("WEB_ORIGIN", "https://apertures.online");
    headerValues.set("x-aperture-public-host", "watch.customer.example");
    headerValues.set("x-forwarded-proto", "https");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(MarketplacePage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fails closed before host or registry work when the control plane is disabled", async () => {
    vi.stubEnv("PLATFORM_CONTROL_PLANE_ENABLED", "false");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(MarketplacePage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
