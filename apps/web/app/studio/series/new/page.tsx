import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { NamedRecord } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { SeriesCreateForm } from "@/app/studio/components/series-forms";
import { StudioShell } from "@/app/studio/components/studio-shell";
export default async function NewSeries() {
  const [admin, genres] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/genres"),
  ]);
  return (
    <StudioShell
      admin={admin}
      active="series"
      eyebrow="Series editor"
      title="Create a draft series"
    >
      <div className="editor-intro">
        <p>
          Create the series container first. Seasons and ordered episodes are
          added in the next step.
        </p>
      </div>
      <SeriesCreateForm genres={genres} />
    </StudioShell>
  );
}
