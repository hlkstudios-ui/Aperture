import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./actions", () => ({
  addDomainAction: vi.fn(),
  refreshDomainAction: vi.fn(),
  makePrimaryDomainAction: vi.fn(),
  removeDomainAction: vi.fn(),
  usePlatformDomainAction: vi.fn(),
}));

import { DomainManager } from "./domain-manager";
import type { SiteDomain, SiteDomainCollection } from "./domain-types";

function domain(overrides: Partial<SiteDomain> = {}): SiteDomain {
  return {
    id: "domain-1",
    hostname: "watch.example.com",
    status: "active",
    is_primary: false,
    revision: 4,
    dns_records: [
      { type: "CNAME", name: "watch", value: "edge.apertures.online", purpose: "Routing" },
      { type: "TXT", name: "_aperture.watch", value: "verify-123", purpose: "Ownership" },
    ],
    ownership_status: "verified",
    certificate_status: "ready",
    last_checked_at: "2026-08-30T12:00:00Z",
    ...overrides,
  };
}

function collection(domains: SiteDomain[] = []): SiteDomainCollection {
  return {
    revision: 1,
    platform_hostname: "apertures.online",
    primary_domain_id: domains.find((item) => item.is_primary)?.id ?? null,
    custom_domains_available: true,
    domains,
  };
}

describe("DomainManager", () => {
  it("keeps the hosted address visible as the optional, launch-safe default", () => {
    render(<DomainManager collection={collection()} />);

    expect(screen.getByRole("heading", { name: "apertures.online" })).toBeInTheDocument();
    expect(screen.getByText(/Safe hosted address:/).closest("p")).toHaveTextContent("apertures.online remains available");
    expect(screen.getByText(/custom domain is optional and never blocks launch/i)).toBeInTheDocument();
    expect(screen.getByText(/Aperture-hosted address is already in use/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No custom domains yet" })).toBeInTheDocument();
  });

  it("disables adding while custom-domain infrastructure is unavailable", () => {
    render(<DomainManager collection={{
      ...collection(),
      custom_domains_available: false,
    }} />);

    expect(screen.getByRole("textbox", { name: /Customer domain/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Custom domains unavailable" })).toBeDisabled();
    expect(screen.getByText(/Aperture-hosted access stays available/i)).toBeInTheDocument();
    expect(screen.getAllByText(/apertures\.online remains fully usable/i)).not.toHaveLength(0);
    expect(screen.getByText(/does not block launch or setup/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Custom domains are not enabled" })).toBeInTheDocument();
  });

  it("shows registrar-neutral CNAME and TXT cards and enables an active domain", () => {
    render(<DomainManager collection={collection([domain()])} />);

    expect(screen.getByRole("heading", { name: "watch.example.com" })).toBeInTheDocument();
    expect(screen.getByText("CNAME")).toBeInTheDocument();
    expect(screen.getByText("TXT")).toBeInTheDocument();
    expect(screen.getByText("edge.apertures.online")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check connection" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Make primary" })).toBeEnabled();
  });

  it("disables provider-backed mutations when infrastructure is unavailable", () => {
    render(<DomainManager collection={{
      ...collection([domain()]),
      custom_domains_available: false,
    }} />);

    expect(screen.getByRole("button", { name: "Check connection" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Make primary" })).toBeDisabled();
    expect(screen.getByText("Removal unavailable", { selector: "summary" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Removal unavailable", { selector: "summary" }));
    expect(screen.getByText(/Domain changes are unavailable until/i)).toBeInTheDocument();
  });

  it("labels provider HTTP validation records without presenting them as DNS fields", () => {
    render(<DomainManager collection={collection([domain({
      dns_records: [{
        type: "HTTP",
        name: "https://watch.example.com/.well-known/verify",
        value: "verification-body",
        purpose: "ownership",
      }],
    })])} />);

    expect(screen.getByText("Validation URL")).toBeInTheDocument();
    expect(screen.getByText("Response body")).toBeInTheDocument();
    expect(screen.getByText(/serve the response body at the exact validation URL/i)).toBeInTheDocument();
  });

  it("locks activation while edge setup is pending", () => {
    render(<DomainManager collection={collection([domain({ status: "pending_edge" })])} />);

    expect(screen.getByText("Connecting edge")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Make primary" })).toBeDisabled();
    expect(screen.getByText(/unlocks after Check connection reports the domain as connected/i)).toBeInTheDocument();
  });

  it("requires an authoritative active state before primary selection", () => {
    render(<DomainManager collection={collection([domain({ status: "ready" })])} />);

    expect(screen.getByText("Connection check required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Make primary" })).toBeDisabled();
  });

  it("explains initial provisioning without enabling activation", () => {
    render(<DomainManager collection={collection([domain({ status: "provisioning" })])} />);

    expect(screen.getByText("Preparing setup")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Make primary" })).toBeDisabled();
  });

  it("requires the exact hostname before enabling removal", () => {
    render(<DomainManager collection={collection([domain()])} />);

    fireEvent.click(screen.getByText("Remove domain", { selector: "summary" }));
    const confirmation = screen.getByLabelText(/Type watch\.example\.com to confirm/);
    const remove = screen.getByRole("button", { name: "Remove domain" });
    expect(remove).toBeDisabled();

    fireEvent.change(confirmation, { target: { value: "watch.example.com" } });
    expect(remove).toBeEnabled();
  });

  it("allows the primary domain to fall back to the hosted address", () => {
    render(<DomainManager collection={collection([domain({ status: "active", is_primary: true })])} />);

    expect(screen.getByText("Live · Primary")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Remove domain", { selector: "summary" }));
    expect(screen.getByText(/Aperture-hosted address will become the primary/i)).toBeInTheDocument();
    const confirmation = screen.getByLabelText(/Type watch\.example\.com to confirm/);
    fireEvent.change(confirmation, { target: { value: "watch.example.com" } });
    expect(screen.getByRole("button", { name: "Remove domain" })).toBeEnabled();
  });

  it("can make the hosted address primary without deleting the connected domain", () => {
    render(<DomainManager collection={{
      ...collection([domain({ status: "active", is_primary: true })]),
      revision: 12,
    }} />);

    expect(screen.getByRole("button", {
      name: "Use Aperture-hosted address as primary",
    })).toBeEnabled();
    expect(screen.getByText(/Connected custom domains stay available as alternate entrances/i)).toBeInTheDocument();
  });

  it("turns provider failure codes into readable guidance", () => {
    render(<DomainManager collection={collection([domain({
      status: "failed",
      failure_reason: "turnstile_hostname_quota",
    })])} />);

    expect(screen.getByText(/CAPTCHA widget has reached its hostname limit/i)).toBeInTheDocument();
    expect(screen.queryByText("turnstile_hostname_quota")).not.toBeInTheDocument();
  });
});
