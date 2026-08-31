import type { Metadata } from "next";

import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import type { LaunchSetupRecord } from "@/app/studio/launch/launch-setup-types";
import { LegalPolicyForm } from "./legal-policy-form";
import type { LegalPolicyRecord } from "./legal-policy-types";

export const metadata: Metadata = { title: "Legal & policy" };

export default async function LegalPolicyPage() {
  const [admin, record, launchSetup] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<LegalPolicyRecord>("/admin/site/legal-policy"),
    adminCatalogFetch<LaunchSetupRecord>("/admin/site/brand"),
  ]);

  return (
    <StudioShell
      active="legal & policy"
      admin={admin}
      eyebrow="Owner workspace | Private draft"
      title="Legal & policy"
      setupOnly={!launchSetup.published_at}
      actions={<span className="status"><span /> Owner-only draft</span>}
    >
      <p className="editor-intro">Record the operator, jurisdiction, contact, and audience facts that may be needed when the policy package is prepared. Every field can be completed later.</p>
      <LegalPolicyForm initialRecord={record} />
    </StudioShell>
  );
}
