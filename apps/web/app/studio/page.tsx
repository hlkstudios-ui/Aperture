import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";

export const metadata = { title: "Studio" };

export default async function Studio() {
  const admin = await requireAdminSession();
  return (
    <StudioShell
      admin={admin}
      active="dashboard"
      eyebrow="Operations"
      title="Good evening."
      actions={
        <div className="status">
          <span /> Systems online
        </div>
      }
    >
      <div className="studio-grid">
        <article className="launch-card">
          <p className="eyebrow">Catalog operations</p>
          <h2>Your publishing room is open.</h2>
          <p>
            Create and refine draft movies or series, inspect catalog previews,
            and deliberately publish only ready metadata.
          </p>
        </article>
        <article className="system-card">
          <h2>Operational domains</h2>
          <dl>
            <div>
              <dt>Authentication</dt>
              <dd>Ready</dd>
            </div>
            <div>
              <dt>Catalog</dt>
              <dd>Ready</dd>
            </div>
            <div>
              <dt>Media pipeline</dt>
              <dd>Later phase</dd>
            </div>
          </dl>
        </article>
      </div>
    </StudioShell>
  );
}
