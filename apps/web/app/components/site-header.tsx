import Link from "next/link";
import { featureFlags } from "@/app/lib/feature-flags";

const primary = [["Home", "/"], ["Browse", "/browse"], ["Movies", "/movies"], ["Series", "/series"]];
const explore = [
  ["New releases", "/new-releases", "The latest additions"],
  ["Currently airing", "/currently-airing", "Episodes still arriving"],
  ["Trending", "/trending", "The editorial spotlight"],
  ["Recently updated", "/recently-updated", "Fresh catalog changes"],
  ["Collections", "/collections", "Stories grouped with purpose"],
  ["Journeys", "/journeys", "Watch in a guided order"],
  ...(featureFlags.experimentalRecommendations ? [["Discover", "/discover", "Personalized discovery"]] : []),
];
const mobileItems = [...primary, ...explore.map(([label, href]) => [label, href]), ["My List", "/my-list"], ["Activity", "/activity"], ["Passport", "/passport"], ["Search", "/search"]];

export function SiteHeader() {
  return <header className="site-header catalog-header cinematic-nav">
    <Link className="wordmark cinematic-wordmark" href="/" aria-label="Aperture home" prefetch={false}><i aria-hidden="true"><span /></i><strong>APERTURE</strong></Link>
    <nav className="desktop-nav" aria-label="Primary navigation">{primary.map(([label, href]) => <Link href={href} key={href} prefetch={false}>{label}</Link>)}</nav>
    <details className="nav-explore"><summary>Explore <span aria-hidden="true">⌄</span></summary><div className="nav-mega-panel">
      <header><p className="eyebrow">Go beyond the credits</p><strong>Find your next obsession</strong></header>
      <nav aria-label="Explore Aperture">{explore.map(([label, href, detail]) => <Link href={href} key={href} prefetch={false}><span>{label}</span><small>{detail}</small></Link>)}</nav>
      <Link className="nav-feature" href="/currently-airing" prefetch={false}><span>Now unfolding</span><strong>Stories that haven’t finished yet</strong><small>Explore ongoing series →</small></Link>
    </div></details>
    <div className="nav-library" aria-label="Your library"><Link href="/my-list" prefetch={false}><span aria-hidden="true">＋</span> My List</Link><Link href="/activity" prefetch={false}><span aria-hidden="true">◉</span> Activity</Link></div>
    <div className="header-actions cinematic-actions"><Link className="nav-icon-action" href="/search" aria-label="Search the catalog" prefetch={false}>⌕</Link><details className="account-menu"><summary aria-label="Open account menu"><span aria-hidden="true">A</span></summary><nav aria-label="Account navigation"><Link href="/account">Account</Link><Link href="/passport">Passport</Link><Link href="/profiles">Profiles</Link><Link href="/login">Sign in</Link><Link href="/studio">Studio</Link></nav></details></div>
    <details className="mobile-menu cinematic-mobile-menu"><summary><span>Menu</span><i aria-hidden="true">☰</i></summary><nav aria-label="Mobile navigation">{mobileItems.map(([label, href]) => <Link href={href} key={href} prefetch={false}>{label}</Link>)}<Link href="/account">Account</Link><Link href="/login">Sign in</Link><Link href="/studio">Studio</Link></nav></details>
  </header>;
}
