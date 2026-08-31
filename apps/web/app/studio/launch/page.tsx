import type { Metadata } from "next";

import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { LaunchSetupWizard } from "./launch-setup-wizard";
import type { LaunchSetupRecord } from "./launch-setup-types";

export const metadata: Metadata = { title: "Launch setup" };

export default async function LaunchSetupPage() {
  const [admin, setup] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<LaunchSetupRecord>("/admin/site/brand"),
  ]);

  return (
    <StudioShell
      admin={admin}
      active="launch setup"
      eyebrow="White-label premiere"
      title="Launch setup"
      setupOnly={!setup.published_at}
      actions={<span className="status"><span /> Owner-only configuration</span>}
    >
      <LaunchSetupWizard initialSetup={setup} />
    </StudioShell>
  );
}
