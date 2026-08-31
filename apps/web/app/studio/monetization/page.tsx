import type { Metadata } from "next";

import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import type { LaunchSetupRecord } from "@/app/studio/launch/launch-setup-types";
import { MonetizationSetup } from "./monetization-setup";
import type { ViewerMonetizationRecord, ViewerPlan } from "./monetization-types";

export const metadata: Metadata = { title: "Customer payments" };

export default async function CustomerPaymentsPage() {
  const [admin, record, plans, launchSetup] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<ViewerMonetizationRecord>("/admin/viewer-monetization"),
    adminCatalogFetch<ViewerPlan[]>("/admin/viewer-plans"),
    adminCatalogFetch<LaunchSetupRecord>("/admin/site/brand"),
  ]);

  return <StudioShell
    active="customer payments"
    admin={admin}
    eyebrow="Viewer monetization | Owner setup"
    title="Customer payments"
    setupOnly={!launchSetup.published_at}
    actions={<span className="status"><span /> Payments off by default</span>}
  >
    <p className="editor-intro">Prepare how your viewers can subscribe without mixing their payments with the fee you pay for Aperture. Free access remains active until a separate server-authorized change.</p>
    <MonetizationSetup plans={plans} record={record} />
  </StudioShell>;
}
