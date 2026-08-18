import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { Movie } from "@/app/lib/catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { CollectionDraft, JourneyDraft } from "./actions";
import { CurationEditor } from "./curation-editor";

type ApiItem = { title_id: string; kind: string };
type ApiCollection = Omit<CollectionDraft, "movieIds"> & { id: string; items: ApiItem[] };
type ApiJourney = Omit<JourneyDraft, "chapters"> & { id: string; chapters: Array<{ title: string; introduction: string | null; items: ApiItem[] }> };

export default async function CurationStudioPage() {
  const admin = await requireAdminSession();
  const [movies, collections, journeys] = await Promise.all([
    adminCatalogFetch<Movie[]>("/admin/catalog/movies"),
    adminCatalogFetch<ApiCollection[]>("/admin/curation/collections"),
    adminCatalogFetch<ApiJourney[]>("/admin/curation/journeys"),
  ]);
  return <StudioShell admin={admin} active="curation" eyebrow="Editorial programming" title="Collections & Film Journeys">
    <CurationEditor movies={movies.map(({ id, title }) => ({ id, title }))} initialCollections={collections.map((item) => ({ ...item, movieIds: item.items.filter((entry) => entry.kind === "movie").map((entry) => entry.title_id) }))} initialJourneys={journeys.map((item) => ({ ...item, chapters: item.chapters.map((chapter) => ({ title: chapter.title, introduction: chapter.introduction ?? "", movieIds: chapter.items.filter((entry) => entry.kind === "movie").map((entry) => entry.title_id) })) }))} />
  </StudioShell>;
}
