import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { MfaEnrollment } from "./mfa-enrollment";
export default async function Settings() {
  const admin = await requireAdminSession();
  return (
    <StudioShell
      admin={admin}
      active="settings"
      eyebrow="Security & workspace"
      title="Settings"
    >
      <div className="studio-grid">
        <article className="system-card">
          <h2>Administrator security</h2>
          <dl>
            <div>
              <dt>Identity</dt>
              <dd>{admin.email}</dd>
            </div>
            <div>
              <dt>Multi-factor authentication</dt>
              <dd>{admin.mfa_enabled ? "Enabled" : "Not enabled"}</dd>
            </div>
            <div>
              <dt>Session</dt>
              <dd>Server verified</dd>
            </div>
          </dl>
        </article>
        <MfaEnrollment enabled={admin.mfa_enabled} />
      </div>
    </StudioShell>
  );
}
