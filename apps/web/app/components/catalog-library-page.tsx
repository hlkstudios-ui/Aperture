import { ContentCard } from "@/app/components/content-card";
import { SiteHeader } from "@/app/components/site-header";
import type { Movie, Series } from "@/app/lib/catalog";

export type LibraryTitle = { title: Movie | Series; kind: "movie" | "series" };

export function CatalogLibraryPage({ eyebrow, title, description, items, empty }: {
  eyebrow: string;
  title: string;
  description: string;
  items: LibraryTitle[];
  empty: string;
}) {
  return <main className="catalog-page discovery-library-page">
    <SiteHeader />
    <header className="library-heading">
      <p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p>
      <span className="library-count">{items.length} {items.length === 1 ? "title" : "titles"}</span>
    </header>
    {items.length ? <section className="catalog-grid" aria-label={title}>{items.map((item) => <ContentCard title={item.title} kind={item.kind} key={`${item.kind}:${item.title.id}`} />)}</section> : <section className="catalog-state compact"><h2>{empty}</h2><p>New catalog entries will appear here automatically.</p></section>}
  </main>;
}
