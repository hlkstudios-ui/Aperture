import { describe, expect, it } from "vitest";

import { normalizeDomainCollection, type SiteDomain } from "./domain-types";

describe("normalizeDomainCollection", () => {
  it("accepts the compatibility bare-list response and derives its primary", () => {
    const domains: SiteDomain[] = [{
      id: "domain-1",
      hostname: "watch.example.com",
      status: "active",
      is_primary: true,
      revision: 5,
      dns_records: [],
    }];

    expect(normalizeDomainCollection(domains, "apertures.online")).toEqual({
      revision: 5,
      platform_hostname: "apertures.online",
      primary_domain_id: "domain-1",
      custom_domains_available: true,
      domains,
    });
  });

  it("preserves the structured API response", () => {
    expect(normalizeDomainCollection({
      revision: 7,
      platform_hostname: "hosted.example",
      primary_domain_id: null,
      domains: [],
    }, "fallback.example")).toEqual({
      revision: 7,
      platform_hostname: "hosted.example",
      primary_domain_id: null,
      custom_domains_available: true,
      domains: [],
    });
  });

  it("preserves an explicit unavailable capability from the API", () => {
    expect(normalizeDomainCollection({
      revision: 2,
      platform_hostname: "hosted.example",
      primary_domain_id: null,
      custom_domains_available: false,
      domains: [],
    }, "fallback.example").custom_domains_available).toBe(false);
  });
});
