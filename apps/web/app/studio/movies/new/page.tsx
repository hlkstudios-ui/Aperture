import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { NamedRecord } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { MovieForm } from "@/app/studio/components/movie-form";
import { StudioShell } from "@/app/studio/components/studio-shell";

export const metadata = { title: "New movie · Studio" };
export default async function NewMovie() {
  const admin = await requireAdminSession();
  const [genres, themes, tags] = await Promise.all([
    adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/genres"),
    adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/themes"),
    adminCatalogFetch<NamedRecord[]>("/admin/catalog/named/tags"),
  ]);
  return (
    <StudioShell
      admin={admin}
      active="movies"
      eyebrow="Movie editor"
      title="Create a draft movie"
    >
      <div className="editor-intro">
        <p>
          The record remains private until an administrator deliberately
          publishes it. Media availability is managed separately.
        </p>
      </div>
      <MovieForm genres={genres} themes={themes} tags={tags} />
    </StudioShell>
  );
}
