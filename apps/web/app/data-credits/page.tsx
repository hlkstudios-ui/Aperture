import Link from "next/link";
import { SiteHeader } from "@/app/components/site-header";

export default function DataCreditsPage() {
  return (
    <main className="policy-page">
      <SiteHeader />
      <article>
        <p className="eyebrow">Catalog transparency</p>
        <h1>Data credits</h1>
        <p>Information about external catalog sources used by Aperture.</p>
        <section>
          <h2>The Movie Database</h2>
          <p>This product uses the TMDB API but is not endorsed or certified by TMDB.</p>
          <p>Title metadata and artwork may be supplied by The Movie Database.</p>
          <a href="https://www.themoviedb.org" rel="noreferrer">Visit The Movie Database</a>
        </section>
        <Link className="back-link" href="/">← Return home</Link>
      </article>
    </main>
  );
}
