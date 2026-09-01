export type PlatformPreviewAsset = {
  kind: "image" | "video";
  url: string;
  alt: string;
};

export type PlatformTemplateVersion = {
  id: string;
  version: string;
  feature_manifest: Record<string, unknown>;
  configuration_schema: Record<string, unknown>;
};

export type PlatformTemplatePricing = {
  price_cents: number;
  currency: string;
  interval: "month" | "year";
};

export type RentalAgreement = {
  id: string;
  version: string;
  title: string;
  content: string;
  content_sha256: string;
  published_at: string;
};

export type PlatformTemplate = {
  id: string;
  slug: string;
  name: string;
  description: string;
  category: string;
  thumbnail_url: string | null;
  preview_assets: PlatformPreviewAsset[];
  demo_url: string | null;
  status: "preview" | "published";
  current_version: PlatformTemplateVersion | null;
  starting_price: PlatformTemplatePricing | null;
  rental_available: boolean;
  unavailable_reason: string | null;
};

export type PlatformTemplateDetail = PlatformTemplate & {
  rental_agreement: RentalAgreement | null;
};

export type PlatformAccount = {
  id: string;
  email: string;
  created_at: string;
};

export type PlatformRental = {
  schema_version: 1;
  id: string;
  status: "awaiting_payment";
  tenant: {
    id: string;
    slug: string;
    business_name: string;
    hosted_hostname: string;
    status: "reserved";
  };
  template: {
    id: string;
    slug: string;
    name: string;
    version_id: string;
    version: string;
  };
  price_snapshot: PlatformTemplatePricing;
  legal_acceptance: {
    id: string;
    agreement_version_id: string;
    version: string;
    content_sha256: string;
    accepted_at: string;
  };
  platform_billing: {
    status: "disabled";
    checkout_available: false;
  };
  provisioning_status: "not_started";
  domain_status: "not_created";
  next_action: "platform_billing_unavailable";
  created_at: string;
};

export type MarketplaceLoadState =
  | { status: "ready"; templates: PlatformTemplate[] }
  | { status: "unavailable"; reason: string };

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function safePublicUrl(value: unknown): string | null {
  if (value === null) return null;
  if (!isString(value)) return null;
  if ([...value].some((character) => character.charCodeAt(0) < 32) || value.includes("\\")) {
    return null;
  }
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:"
      && Boolean(parsed.hostname)
      && !parsed.username
      && !parsed.password
      ? value
      : null;
  } catch {
    return null;
  }
}

function parsePreviewAssets(value: unknown): PlatformPreviewAsset[] | null {
  if (!Array.isArray(value)) return null;
  const assets: PlatformPreviewAsset[] = [];
  for (const item of value) {
    if (!isRecord(item) || (item.kind !== "image" && item.kind !== "video") || !isString(item.alt)) {
      return null;
    }
    const url = safePublicUrl(item.url);
    if (!url) return null;
    assets.push({ kind: item.kind, url, alt: item.alt });
  }
  return assets;
}

function parseVersion(value: unknown): PlatformTemplateVersion | null {
  if (!isRecord(value) || !isString(value.id) || !isString(value.version)) return null;
  if (!isRecord(value.feature_manifest) || !isRecord(value.configuration_schema)) return null;
  return {
    id: value.id,
    version: value.version,
    feature_manifest: value.feature_manifest,
    configuration_schema: value.configuration_schema,
  };
}

function parsePricing(value: unknown): PlatformTemplatePricing | null {
  if (
    !isRecord(value)
    || !Number.isSafeInteger(value.price_cents)
    || (value.price_cents as number) <= 0
    || typeof value.currency !== "string"
    || !/^[A-Z]{3}$/.test(value.currency)
    || (value.interval !== "month" && value.interval !== "year")
  ) {
    return null;
  }
  return {
    price_cents: value.price_cents as number,
    currency: value.currency,
    interval: value.interval,
  };
}

export function parsePlatformTemplate(value: unknown): PlatformTemplate | null {
  if (!isRecord(value)) return null;
  if (
    !isString(value.id)
    || !isString(value.slug)
    || !isString(value.name)
    || !isString(value.description)
    || !isString(value.category)
    || (value.status !== "preview" && value.status !== "published")
    || typeof value.rental_available !== "boolean"
  ) {
    return null;
  }
  const thumbnail = safePublicUrl(value.thumbnail_url);
  const demo = safePublicUrl(value.demo_url);
  const assets = parsePreviewAssets(value.preview_assets);
  if (assets === null || (value.thumbnail_url !== null && thumbnail === null) || (value.demo_url !== null && demo === null)) {
    return null;
  }
  const currentVersion = value.current_version === null ? null : parseVersion(value.current_version);
  const startingPrice = value.starting_price === null ? null : parsePricing(value.starting_price);
  if ((value.current_version !== null && !currentVersion) || (value.starting_price !== null && !startingPrice)) {
    return null;
  }
  if (value.unavailable_reason !== null && typeof value.unavailable_reason !== "string") return null;
  return {
    id: value.id,
    slug: value.slug,
    name: value.name,
    description: value.description,
    category: value.category,
    thumbnail_url: thumbnail,
    preview_assets: assets,
    demo_url: demo,
    status: value.status,
    current_version: currentVersion,
    starting_price: startingPrice,
    rental_available: value.rental_available,
    unavailable_reason: value.unavailable_reason,
  };
}

export function parseTemplateCollection(value: unknown): PlatformTemplate[] | null {
  if (!isRecord(value) || value.schema_version !== 1 || !Array.isArray(value.items)) return null;
  const templates = value.items.map(parsePlatformTemplate);
  return templates.every((template): template is PlatformTemplate => template !== null)
    ? templates
    : null;
}

export function parseTemplateDetail(value: unknown): PlatformTemplateDetail | null {
  const template = parsePlatformTemplate(value);
  if (!template || !isRecord(value)) return null;
  if (value.rental_agreement === null) return { ...template, rental_agreement: null };
  const agreement = value.rental_agreement;
  if (
    !isRecord(agreement)
    || !isString(agreement.id)
    || !isString(agreement.version)
    || !isString(agreement.title)
    || !isString(agreement.content)
    || typeof agreement.content_sha256 !== "string"
    || !/^[0-9a-f]{64}$/.test(agreement.content_sha256)
    || !isString(agreement.published_at)
  ) {
    return null;
  }
  return {
    ...template,
    rental_agreement: {
      id: agreement.id,
      version: agreement.version,
      title: agreement.title,
      content: agreement.content,
      content_sha256: agreement.content_sha256,
      published_at: agreement.published_at,
    },
  };
}

export function isPlatformAccount(value: unknown): value is PlatformAccount {
  return isRecord(value)
    && isString(value.id)
    && isString(value.email)
    && isString(value.created_at);
}

export function isPlatformRental(value: unknown): value is PlatformRental {
  if (
    !isRecord(value)
    || !isRecord(value.tenant)
    || !isRecord(value.template)
    || !isRecord(value.platform_billing)
    || !isRecord(value.legal_acceptance)
  ) return false;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const slug = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
  const hostname = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
  const timestamp = (candidate: unknown) => typeof candidate === "string"
    && candidate.length > 0
    && Number.isFinite(Date.parse(candidate));
  return value.schema_version === 1
    && typeof value.id === "string"
    && uuid.test(value.id)
    && value.status === "awaiting_payment"
    && typeof value.tenant.id === "string"
    && uuid.test(value.tenant.id)
    && typeof value.tenant.slug === "string"
    && slug.test(value.tenant.slug)
    && isString(value.tenant.business_name)
    && isString(value.tenant.hosted_hostname)
    && value.tenant.hosted_hostname === value.tenant.hosted_hostname.toLowerCase()
    && hostname.test(value.tenant.hosted_hostname)
    && value.tenant.status === "reserved"
    && typeof value.template.id === "string"
    && uuid.test(value.template.id)
    && typeof value.template.slug === "string"
    && slug.test(value.template.slug)
    && isString(value.template.name)
    && typeof value.template.version_id === "string"
    && uuid.test(value.template.version_id)
    && isString(value.template.version)
    && parsePricing(value.price_snapshot) !== null
    && typeof value.legal_acceptance.id === "string"
    && uuid.test(value.legal_acceptance.id)
    && typeof value.legal_acceptance.agreement_version_id === "string"
    && uuid.test(value.legal_acceptance.agreement_version_id)
    && isString(value.legal_acceptance.version)
    && typeof value.legal_acceptance.content_sha256 === "string"
    && /^[0-9a-f]{64}$/.test(value.legal_acceptance.content_sha256)
    && timestamp(value.legal_acceptance.accepted_at)
    && value.platform_billing.status === "disabled"
    && value.platform_billing.checkout_available === false
    && value.provisioning_status === "not_started"
    && value.domain_status === "not_created"
    && value.next_action === "platform_billing_unavailable"
    && timestamp(value.created_at);
}

export function rentalMatchesIntent(
  rental: PlatformRental,
  detail: PlatformTemplateDetail,
  businessName: string,
  tenantSlug: string,
): boolean {
  const version = detail.current_version;
  const agreement = detail.rental_agreement;
  const price = detail.starting_price;
  if (!version || !agreement || !price) return false;

  const normalizedBusinessName = businessName.trim().split(/\s+/u).join(" ");
  const normalizedTenantSlug = tenantSlug.trim().toLowerCase();
  return rental.tenant.slug === normalizedTenantSlug
    && rental.tenant.business_name === normalizedBusinessName
    && rental.template.id === detail.id
    && rental.template.slug === detail.slug
    && rental.template.name === detail.name
    && rental.template.version_id === version.id
    && rental.template.version === version.version
    && rental.legal_acceptance.agreement_version_id === agreement.id
    && rental.legal_acceptance.version === agreement.version
    && rental.legal_acceptance.content_sha256 === agreement.content_sha256
    && rental.price_snapshot.price_cents === price.price_cents
    && rental.price_snapshot.currency === price.currency
    && rental.price_snapshot.interval === price.interval;
}

function featureLabel(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (!isRecord(value)) return null;
  for (const key of ["label", "name", "title"]) {
    if (typeof value[key] === "string" && value[key].trim()) return value[key].trim();
  }
  return null;
}

function humanizeFeatureKey(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function templateFeatures(template: PlatformTemplate): string[] {
  const manifest = template.current_version?.feature_manifest;
  if (!manifest) return [];
  const labels: string[] = [];
  for (const key of ["features", "capabilities", "modules"]) {
    const group = manifest[key];
    if (!Array.isArray(group)) continue;
    for (const item of group) {
      const label = featureLabel(item);
      if (label) labels.push(label);
    }
  }
  if (!labels.length) {
    for (const [key, enabled] of Object.entries(manifest)) {
      if (enabled === true) labels.push(humanizeFeatureKey(key));
    }
  }
  return [...new Set(labels)].slice(0, 5);
}

export function formatTemplatePrice(pricing: PlatformTemplatePricing | null): string | null {
  if (!pricing) return null;
  try {
    const amount = new Intl.NumberFormat("en", {
      style: "currency",
      currency: pricing.currency,
      maximumFractionDigits: pricing.price_cents % 100 === 0 ? 0 : 2,
    }).format(pricing.price_cents / 100);
    return `${amount} / ${pricing.interval}`;
  } catch {
    return `${pricing.currency} ${(pricing.price_cents / 100).toFixed(2)} / ${pricing.interval}`;
  }
}
