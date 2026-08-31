import Image from "next/image";
import Link from "next/link";
import { SiteHeader } from "@/app/components/site-header";
import { getSiteBrand } from "@/app/lib/site-brand-server";

export default async function DataCreditsPage() {
  const brand = await getSiteBrand();
  return (
    <main className="policy-page">
      <SiteHeader />
      <article>
        <p className="eyebrow">Catalog transparency</p>
        <h1>Data credits</h1>
        <p>Information about external catalog sources used by {brand.business_name}.</p>
        <section>
          <h2>The Movie Database</h2>
          <a href="https://www.themoviedb.org" rel="noreferrer" aria-label="Visit The Movie Database">
            <Image
              src="https://www.themoviedb.org/assets/2/v4/logos/v2/blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82bb2cd95f6c.svg"
              alt="TMDB"
              width={154}
              height={66}
              unoptimized
            />
          </a>
          <p>
            This website uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise
            approved by TMDB.
          </p>
          <p>Title metadata and artwork may be supplied by The Movie Database.</p>
          <a href="https://www.themoviedb.org" rel="noreferrer">Visit The Movie Database</a>
        </section>
        <Link className="back-link" href="/">← Return home</Link>
      </article>
    </main>
  );
}
