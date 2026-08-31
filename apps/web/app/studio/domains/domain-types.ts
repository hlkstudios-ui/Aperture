export type DomainDnsRecord = {
  type: string;
  name: string;
  value: string;
  purpose?: string | null;
};

export type SiteDomain = {
  id: string;
  hostname: string;
  status: string;
  is_primary: boolean;
  revision: number;
  dns_records: DomainDnsRecord[];
  ownership_status?: string | null;
  certificate_status?: string | null;
  verified_at?: string | null;
  activated_at?: string | null;
  last_checked_at?: string | null;
  failure_reason?: string | null;
};

export type SiteDomainCollection = {
  revision: number;
  platform_hostname: string | null;
  primary_domain_id: string | null;
  custom_domains_available: boolean;
  domains: SiteDomain[];
};

export type SiteDomainCollectionResponse =
  | SiteDomain[]
  | {
      revision?: number;
      platform_hostname?: string | null;
      primary_domain_id?: string | null;
      custom_domains_available?: boolean;
      domains?: SiteDomain[];
    };

export function normalizeDomainCollection(
  payload: SiteDomainCollectionResponse,
  fallbackPlatformHostname: string,
): SiteDomainCollection {
  if (Array.isArray(payload)) {
    return {
      revision: Math.max(0, ...payload.map((domain) => domain.revision)),
      platform_hostname: fallbackPlatformHostname,
      primary_domain_id: payload.find((domain) => domain.is_primary)?.id ?? null,
      custom_domains_available: true,
      domains: payload,
    };
  }

  const domains = Array.isArray(payload.domains) ? payload.domains : [];
  return {
    revision: Number.isInteger(payload.revision) ? Number(payload.revision) : 0,
    platform_hostname: payload.platform_hostname?.trim() || fallbackPlatformHostname,
    primary_domain_id:
      payload.primary_domain_id ?? domains.find((domain) => domain.is_primary)?.id ?? null,
    custom_domains_available:
      payload.custom_domains_available === undefined
        ? true
        : payload.custom_domains_available === true,
    domains,
  };
}
