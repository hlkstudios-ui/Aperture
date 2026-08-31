import Link from "next/link";

import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { Series } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { setSeriesStatusAction } from "@/app/studio/actions";
import { StudioShell } from "@/app/studio/components/studio-shell";

export const metadata = { title: "Series · Studio" };

export default async function SeriesIndex() {
  const [admin, series] = await Promise.all([
    requireAdminSession(),
    adminCatalogFetch<Series[]>("/admin/catalog/series"),
  ]);
  const ordered = series.toSorted((left, right) =>
    right.updated_at.localeCompare(left.updated_at),
  );

  return (
    <StudioShell
      admin={admin}
      active="series"
      eyebrow="Episodic catalog"
      title="Series"
      actions={
        <Link className="studio-primary action-link" href="/studio/series/new">
          New series
        </Link>
      }
    >
      <div className="editor-intro">
        <p>
          Create series, organize seasons and episodes, preview the viewer
          experience, and publish only when the complete release is ready.
        </p>
      </div>

      <div className="content-table-wrap">
        <table className="content-table series-content-table">
          <thead>
            <tr>
              <th>Series</th>
              <th>Status</th>
              <th>Updated</th>
              <th><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((item) => {
              const base = `/studio/series/${item.id}`;
              const statusAction = setSeriesStatusAction.bind(
                null,
                item.id,
                item.status === "published" ? "draft" : "published",
              );
              return (
                <tr key={item.id}>
                  <td><strong>{item.title}</strong><small>/{item.slug}</small></td>
                  <td>
                    <span className={`catalog-badge ${item.status}`}>
                      {item.status}
                    </span>
                  </td>
                  <td>{new Date(item.updated_at).toLocaleDateString("en-CA")}</td>
                  <td>
                    <div className="row-actions">
                      <Link href={base}>Edit</Link>
                      <Link href={`${base}/preview`}>Preview</Link>
                      <form action={statusAction}>
                        <button type="submit">
                          {item.status === "published" ? "Unpublish" : "Publish"}
                        </button>
                      </form>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {!ordered.length && (
          <div className="studio-empty">
            <h2>No series yet</h2>
            <p>Create the first series container, then add seasons and episodes.</p>
            <Link className="studio-primary action-link" href="/studio/series/new">
              Create a series
            </Link>
          </div>
        )}
      </div>
    </StudioShell>
  );
}
