import type { Metadata } from "next";

import { adminCatalogFetch, CatalogActionError } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { DomainManager } from "./domain-manager";
import {
  normalizeDomainCollection,
  type SiteDomainCollectionResponse,
} from "./domain-types";

export const metadata: Metadata = { title: "Domains" };

function configuredPlatformHostname(): string {
  try {
    return new URL(process.env.WEB_ORIGIN ?? "https://apertures.online").hostname;
  } catch {
    return "apertures.online";
  }
}

export default async function DomainsPage() {
  const admin = await requireAdminSession();
  const fallbackPlatformHostname = configuredPlatformHostname();
  let response: SiteDomainCollectionResponse = [];
  let loadError = "";
  try {
    response = await adminCatalogFetch<SiteDomainCollectionResponse>("/admin/site/domains");
  } catch (error) {
    if (!(error instanceof CatalogActionError)) throw error;
    loadError = error.detail;
  }
  const collection = normalizeDomainCollection(response, fallbackPlatformHostname);

  return <StudioShell
    active="domains"
    admin={admin}
    eyebrow="Brand identity · Customer access"
    title="Domains"
    actions={<span className="status"><span /> Owner-controlled routing</span>}
  >
    <p className="editor-intro">Give the published brand its own customer-facing address. DNS and certificates change the front door only; everything behind it remains the same Aperture application.</p>
    <DomainManager collection={collection} loadError={loadError} />
  </StudioShell>;
}
