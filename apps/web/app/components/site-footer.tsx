import Link from "next/link";
import { FooterBackToTop } from "@/app/components/footer-back-to-top";
import { GeneratedLogo } from "@/app/components/generated-logo";
import { approvedPolicies } from "@/app/lib/policies";
import { DEFAULT_SITE_BRAND, siteBrandLogoSrc, type SiteBrand } from "@/app/lib/site-brand";

const footerGroups = [
  {
    index: "01",
    label: "Watch",
    links: [
      ["Movies", "/movies"],
      ["Series", "/series"],
      ["Trending", "/trending"],
      ["New releases", "/new-releases"],
      ["Currently airing", "/currently-airing"],
    ],
  },
  {
    index: "02",
    label: "Explore",
    links: [
      ["Browse", "/browse"],
      ["Collections", "/collections"],
      ["Journeys", "/journeys"],
      ["Recently updated", "/recently-updated"],
      ["Signal Run", "/game"],
    ],
  },
  {
    index: "03",
    label: "Your library",
    links: [
      ["My List", "/my-list"],
      ["Activity", "/activity"],
      ["Passport", "/passport"],
      ["Profiles", "/profiles"],
      ["Account", "/account"],
    ],
  },
] as const;

function Arrow() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20">
      <path d="M3 10h14m0 0-5-5m5 5-5 5" />
    </svg>
  );
}

export function SiteFooter({ brand = DEFAULT_SITE_BRAND }: { brand?: SiteBrand }) {
  const policies = approvedPolicies();
  const year = new Date().getUTCFullYear();
  const logo = siteBrandLogoSrc(brand);
  const personalLabel = `My ${brand.short_name}`;

  return (
    <footer className="site-footer closing-iris">
      <div className="closing-iris__threshold" aria-hidden="true">
        <span className="closing-iris__beam" />
        <span className="closing-iris__lens"><i /></span>
        <span className="closing-iris__frame closing-iris__frame--left" />
        <span className="closing-iris__frame closing-iris__frame--right" />
      </div>

      <div className="closing-iris__stage">
        <section className="closing-iris__manifesto">
          <p className="closing-iris__kicker"><span>After the credits</span><span>Keep looking</span></p>
          <h2 id="closing-iris-title">The next story starts in the dark.</h2>
          <p className="closing-iris__lede">
            Browse with intention. Keep what stays with you. Return when the room is ready for another frame.
          </p>
          <nav className="closing-iris__actions" aria-label={`Continue exploring ${brand.business_name}`}>
            <Link className="closing-iris__primary" href="/browse">
              <span>Open the full program</span><Arrow />
            </Link>
            <Link className="closing-iris__secondary" href="/search">
              <span>Search by title or cast</span><Arrow />
            </Link>
          </nav>
        </section>

        <nav className="closing-iris__index" aria-label={`${brand.business_name} directory`}>
          {footerGroups.map((group) => (
            <div className="closing-iris__index-row" key={group.index}>
              <header>
                <span>{group.index}</span>
                <h3>{group.index === "03" ? personalLabel : group.label}</h3>
              </header>
              <div>
                {group.links.map(([label, href]) => (
                  <Link href={href} key={href} prefetch={false}><span>{label}</span><Arrow /></Link>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </div>

      <div className="closing-iris__signature" aria-hidden="true">
        <span>{brand.short_name.toUpperCase()}</span>
      </div>

      <div className="closing-iris__ledger">
        <Link className="closing-iris__lockup" href="/" aria-label={`${brand.business_name} home`}>
          {logo
            ? <span aria-hidden="true" className="closing-iris__brand-image" style={{ backgroundImage: `url(${JSON.stringify(logo)})` }} />
            : brand.logo_mark
              ? <span aria-hidden="true" className="closing-iris__generated-mark" style={{ color: brand.palette.accent }}><GeneratedLogo recipe={brand.logo_mark} decorative size={34} instanceKey="public-footer" /></span>
              : <i aria-hidden="true"><span /></i>}
          <div><strong>{brand.short_name}</strong><small>{brand.tagline ?? "Stories, chosen with a point of view."}</small></div>
        </Link>
        <div className="closing-iris__legal">
          <small>© {year} {brand.business_name}</small>
          {policies.length ? (
            <nav aria-label="Policies">
              {policies.map((policy) => (
                <Link key={policy.slug} href={`/policies/${policy.slug}`} prefetch={false}>{policy.title}</Link>
              ))}
            </nav>
          ) : null}
        </div>
        <FooterBackToTop />
      </div>
    </footer>
  );
}
