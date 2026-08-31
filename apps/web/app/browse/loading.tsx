import { SiteHeader } from "@/app/components/site-header";

export default function BrowseLoading() {
  return (
    <main className="browse-experience browse-experience--loading" aria-live="polite" aria-busy="true">
      <SiteHeader />
      <section className="browse-experience__loading-hero">
        <span className="browse-experience__loading-mark" aria-hidden="true" />
        <h1>Opening the specialist index</h1>
      </section>
      <div className="browse-experience__loading-circles" aria-hidden="true">
        {Array.from({ length: 5 }, (_, index) => <span key={index} />)}
      </div>
      <div className="browse-experience__loading-grid" aria-hidden="true">
        {Array.from({ length: 8 }, (_, index) => <span key={index} />)}
      </div>
    </main>
  );
}
