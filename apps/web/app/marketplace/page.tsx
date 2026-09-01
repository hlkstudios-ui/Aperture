import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { currentStorefrontOrigin } from "@/app/lib/public-origin";
import { MarketplaceCatalog } from "./marketplace-catalog";
import { parseTemplateCollection, type MarketplaceLoadState } from "./platform-marketplace";
import styles from "./marketplace.module.css";

const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

export const metadata: Metadata = {
  title: { absolute: "Apertures Marketplace" },
  description: "Review and request an Apertures streaming platform template for your own business.",
};

export async function loadMarketplaceTemplates(): Promise<MarketplaceLoadState> {
  try {
    const response = await fetch(`${apiOrigin}/platform/templates`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return {
        status: "unavailable",
        reason: "The template catalogue is temporarily unavailable. No rental request can be started right now.",
      };
    }
    const templates = parseTemplateCollection(await response.json());
    if (!templates) {
      return {
        status: "unavailable",
        reason: "The template catalogue returned an invalid response, so rentals have been paused safely.",
      };
    }
    return { status: "ready", templates };
  } catch {
    return {
      status: "unavailable",
      reason: "The template catalogue could not be reached. No rental request can be started right now.",
    };
  }
}

function AperturesMark() {
  return (
    <span className={styles.mark} aria-hidden="true">
      <i /><i /><i /><i /><i /><i />
    </span>
  );
}

export default async function MarketplacePage() {
  if (process.env.PLATFORM_CONTROL_PLANE_ENABLED !== "true") notFound();
  const requestOrigin = await currentStorefrontOrigin();
  const platformOrigin = new URL(process.env.WEB_ORIGIN ?? "http://localhost:3000").origin;
  if (requestOrigin !== platformOrigin) notFound();
  const initialState = await loadMarketplaceTemplates();
  return (
    <div className={`${styles.shell} platform-marketplace-root`} data-hide-public-footer>
      <header className={styles.header}>
        <Link className={styles.identity} href="/marketplace" aria-label="Apertures Marketplace home">
          <AperturesMark />
          <span><strong>APERTURES</strong><small>Template marketplace</small></span>
        </Link>
        <nav aria-label="Marketplace navigation">
          <a href="#templates">Templates</a>
          <span className={styles.headerStatus}><i aria-hidden="true" /> Rental preview</span>
        </nav>
      </header>

      <main className={styles.main}>
        <section className={styles.hero} aria-labelledby="marketplace-title">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>Apertures platform</p>
            <h1 id="marketplace-title">Your identity.<br />A proven cinema system.</h1>
            <p>
              Review the exact template release, price, and rental agreement before reserving a
              hosted tenant. Custom domains remain optional and are configured only after billing
              and provisioning become available.
            </p>
            <a className={styles.heroAction} href="#templates">Explore templates <span aria-hidden="true">↓</span></a>
          </div>
          <aside className={styles.truthPanel} aria-label="Rental process">
            <p>What happens here</p>
            <ol>
              <li><span>01</span><div><strong>Review</strong><small>Version, price, and complete terms</small></div></li>
              <li><span>02</span><div><strong>Accept</strong><small>Sign in and reserve your business slug</small></div></li>
              <li><span>03</span><div><strong>Wait for billing</strong><small>No charge or provisioning is attempted yet</small></div></li>
            </ol>
          </aside>
        </section>

        <section className={styles.catalogSection} id="templates" aria-labelledby="templates-title">
          <header className={styles.sectionHeader}>
            <div><p className={styles.eyebrow}>Available systems</p><h2 id="templates-title">Choose a foundation.</h2></div>
            <p>Every rentable release is pinned to a reviewed artifact and an immutable agreement.</p>
          </header>
          <MarketplaceCatalog initialState={initialState} />
        </section>
      </main>

      <footer className={styles.footer}>
        <span><AperturesMark /> APERTURES</span>
        <p>Platform marketplace · Tenant storefront identities remain separate.</p>
      </footer>
    </div>
  );
}
