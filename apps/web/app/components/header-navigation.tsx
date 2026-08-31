"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { NavIcon, type NavIconName } from "@/app/components/nav-icons";
import { GeneratedLogo } from "@/app/components/generated-logo";
import { useSiteBrand } from "@/app/components/site-brand-provider";
import { siteBrandLogoSrc } from "@/app/lib/site-brand";

type MenuName = "discover" | "library" | "account" | "mobile" | null;
type NavItem = {
  label: string;
  href: string;
  activeHref?: string;
  detail?: string;
  icon?: NavIconName;
};

const primary: NavItem[] = [
  { label: "Home", href: "/", icon: "home" },
  { label: "Browse", href: "/browse", icon: "browse" },
  { label: "Movies", href: "/movies", icon: "film" },
  { label: "Series", href: "/series", icon: "series" },
];

const rightNow: NavItem[] = [
  { label: "Trending now", href: "/trending", detail: "The titles drawing attention" },
  { label: "New releases", href: "/new-releases", detail: "Fresh arrivals to the catalog" },
  { label: "Currently airing", href: "/currently-airing", detail: "Stories still unfolding" },
];

const goDeeper: NavItem[] = [
  { label: "Collections", href: "/collections", detail: "Curated worlds and double bills" },
  { label: "Journeys", href: "/journeys", detail: "Watch stories in a guided order" },
  { label: "Recently updated", href: "/recently-updated", detail: "The latest catalog changes" },
];

const libraryItems: NavItem[] = [
  { label: "My List", href: "/my-list", detail: "Everything you saved", icon: "bookmark" },
  { label: "Continue watching", href: "/activity", detail: "Return to your recent stories", icon: "activity" },
  { label: "Passport", href: "/passport", detail: "Your viewing history and milestones", icon: "passport" },
];

const viewerAccountItems: NavItem[] = [
  { label: "Profiles", href: "/profiles", detail: "Choose who is watching", icon: "account" },
  { label: "Account", href: "/account", detail: "Membership and preferences", icon: "account" },
];

function routeIsActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function HeaderLink({ item, pathname, className, onNavigate, prefetch }: {
  item: NavItem;
  pathname: string;
  className?: string;
  onNavigate: () => void;
  prefetch?: boolean;
}) {
  const active = routeIsActive(pathname, item.activeHref ?? item.href);
  return <Link
    aria-current={active ? "page" : undefined}
    className={className}
    href={item.href}
    onClick={onNavigate}
    prefetch={prefetch}
  >
    {item.icon ? <NavIcon name={item.icon} /> : null}
    <span>{item.label}</span>
    {item.detail ? <small>{item.detail}</small> : null}
  </Link>;
}

export function HeaderNavigation({
  recommendationsEnabled,
}: {
  recommendationsEnabled: boolean;
}) {
  const brand = useSiteBrand();
  const logo = siteBrandLogoSrc(brand);
  const personalLabel = `My ${brand.short_name}`;
  const pathname = usePathname() || "/";
  const router = useRouter();
  const headerRef = useRef<HTMLElement>(null);
  const discoverButtonRef = useRef<HTMLButtonElement>(null);
  const libraryButtonRef = useRef<HTMLButtonElement>(null);
  const accountButtonRef = useRef<HTMLButtonElement>(null);
  const mobileButtonRef = useRef<HTMLButtonElement>(null);
  const discoverPanelRef = useRef<HTMLElement>(null);
  const libraryPanelRef = useRef<HTMLElement>(null);
  const accountPanelRef = useRef<HTMLElement>(null);
  const mobilePanelRef = useRef<HTMLDivElement>(null);
  const [openMenu, setOpenMenu] = useState<MenuName>(null);
  const [elevated, setElevated] = useState(false);

  const discoverItems = recommendationsEnabled
    ? [...goDeeper, { label: "For you", href: "/discover", detail: "Personalized discovery" }]
    : goDeeper;
  const accountItems = viewerAccountItems;
  const mobileRightNow = rightNow.map((item, index) => ({
    ...item,
    icon: (["browse", "film", "series"] as NavIconName[])[index],
  }));

  function closeMenus() {
    setOpenMenu(null);
  }

  function open(menu: Exclude<MenuName, null>, focusFirst = false) {
    setOpenMenu((current) => current === menu ? null : menu);
    if (focusFirst) {
      window.requestAnimationFrame(() => {
        const panel = menu === "discover" ? discoverPanelRef.current
          : menu === "library" ? libraryPanelRef.current
            : menu === "account" ? accountPanelRef.current : mobilePanelRef.current;
        panel?.querySelector<HTMLAnchorElement>("a")?.focus();
      });
    }
  }

  function openFromKeyboard(event: ReactKeyboardEvent<HTMLButtonElement>, menu: Exclude<MenuName, "mobile" | null>) {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    open(menu, true);
  }

  useEffect(() => {
    let frame = 0;
    function handleScroll() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setElevated(window.scrollY > 24));
    }
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (headerRef.current && !headerRef.current.contains(event.target as Node)) closeMenus();
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && openMenu) {
        event.preventDefault();
        const trigger = openMenu === "discover" ? discoverButtonRef.current
          : openMenu === "library" ? libraryButtonRef.current
            : openMenu === "account" ? accountButtonRef.current : mobileButtonRef.current;
        closeMenus();
        trigger?.focus();
        return;
      }
      const target = event.target as HTMLElement | null;
      const isEditing = target?.matches("input, textarea, select, [contenteditable='true']");
      if (event.key === "/" && !isEditing && !event.altKey && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        closeMenus();
        router.push("/search");
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openMenu, router]);

  useEffect(() => {
    if (openMenu !== "mobile") return;
    document.documentElement.classList.add("aperture-nav-open");
    return () => document.documentElement.classList.remove("aperture-nav-open");
  }, [openMenu]);

  function trapMobileFocus(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab") return;
    const focusable = [...(mobilePanelRef.current?.querySelectorAll<HTMLElement>("a, button:not([disabled])") ?? [])];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  const discoverActive = [...rightNow, ...discoverItems, { label: "Game", href: "/game" }]
    .some((item) => routeIsActive(pathname, item.href));
  const libraryActive = libraryItems.some((item) => routeIsActive(pathname, item.href));
  const accountActive = accountItems.some((item) => routeIsActive(pathname, item.href));

  return <>
    <header className="site-header catalog-header cinematic-nav" data-elevated={elevated || undefined} ref={headerRef} role="banner">
      <Link className="wordmark cinematic-wordmark" href="/" aria-label={`${brand.business_name} home`} onClick={closeMenus}>
        <i
          aria-hidden="true"
          className={logo ? "has-custom-logo" : brand.logo_mark ? "has-generated-logo" : undefined}
          style={logo ? { backgroundImage: `url(${JSON.stringify(logo)})` } : brand.logo_mark ? { color: brand.palette.accent } : undefined}
        >
          {logo ? null : brand.logo_mark
            ? <GeneratedLogo recipe={brand.logo_mark} decorative size={31} instanceKey="public-header" />
            : <span />}
        </i><strong>{brand.short_name.toUpperCase()}</strong>
      </Link>

      <nav className="cinematic-primary-nav" aria-label="Primary navigation">
        {primary.map((item) => <HeaderLink item={item} key={item.href} onNavigate={closeMenus} pathname={pathname} />)}
        <button
          aria-controls="aperture-discover-menu"
          aria-expanded={openMenu === "discover"}
          className={discoverActive ? "is-active" : undefined}
          onClick={(event) => open("discover", event.detail === 0)}
          onKeyDown={(event) => openFromKeyboard(event, "discover")}
          ref={discoverButtonRef}
          type="button"
        >
          <span>Discover</span><NavIcon name="chevron" />
        </button>
      </nav>

      <div className="cinematic-nav-actions">
        <Link className="cinematic-play-link" href="/game" aria-current={routeIsActive(pathname, "/game") ? "page" : undefined} onClick={closeMenus}>
          <NavIcon name="game" /><span>Play</span>
        </Link>
        <Link className="cinematic-search-action" href="/search" aria-current={routeIsActive(pathname, "/search") ? "page" : undefined} aria-label={`Search ${brand.business_name}`} onClick={closeMenus}>
          <NavIcon name="search" /><span>Search</span><kbd aria-hidden="true">/</kbd>
        </Link>
        <button
          aria-controls="aperture-library-menu"
          aria-expanded={openMenu === "library"}
          className={`cinematic-library-action${libraryActive ? " is-active" : ""}`}
          onClick={(event) => open("library", event.detail === 0)}
          onKeyDown={(event) => openFromKeyboard(event, "library")}
          ref={libraryButtonRef}
          type="button"
        >
          <NavIcon name="bookmark" /><span>{personalLabel}</span>
        </button>
        <button
          aria-controls="aperture-account-menu"
          aria-expanded={openMenu === "account"}
          aria-label="Profile and account"
          className={`cinematic-profile-action${accountActive ? " is-active" : ""}`}
          onClick={(event) => open("account", event.detail === 0)}
          onKeyDown={(event) => openFromKeyboard(event, "account")}
          ref={accountButtonRef}
          type="button"
        >
          <span><NavIcon name="account" /></span>
        </button>
      </div>

      <div className="cinematic-mobile-actions">
        <Link className="cinematic-mobile-search" href="/search" aria-label={`Search ${brand.business_name}`} onClick={closeMenus}><NavIcon name="search" /></Link>
        <button
          aria-controls="aperture-mobile-menu"
          aria-expanded={openMenu === "mobile"}
          aria-label={openMenu === "mobile" ? "Close menu" : "Open menu"}
          onClick={() => open("mobile", openMenu !== "mobile")}
          ref={mobileButtonRef}
          type="button"
        ><NavIcon name={openMenu === "mobile" ? "close" : "menu"} /></button>
      </div>

      {openMenu === "discover" ? <section className="cinematic-mega-menu" id="aperture-discover-menu" ref={discoverPanelRef}>
        <div className="cinematic-mega-intro">
          <h2>Find the right story for tonight.</h2>
          <p>Follow what is moving now, or go deeper into a collection built around a feeling.</p>
        </div>
        <div className="cinematic-mega-links">
          <nav aria-label="Watch now">
            <h3>Watch now</h3>
            {rightNow.map((item) => <HeaderLink item={item} key={item.href} onNavigate={closeMenus} pathname={pathname} prefetch={false} />)}
          </nav>
          <nav aria-label="Explore deeper">
            <h3>Explore deeper</h3>
            {discoverItems.map((item) => <HeaderLink item={item} key={item.href} onNavigate={closeMenus} pathname={pathname} prefetch={false} />)}
          </nav>
        </div>
        <Link className="cinematic-mega-feature" href="/trending" onClick={closeMenus} prefetch={false}>
          <span>In the spotlight</span>
          <strong>See what the world cannot stop watching.</strong>
          <small>Open trending titles <b aria-hidden="true">→</b></small>
        </Link>
        <Link className="cinematic-mega-game" href="/game" onClick={closeMenus} prefetch={false}><NavIcon name="game" /><span><strong>Signal Run</strong><small>Take a short break inside {brand.short_name}</small></span></Link>
      </section> : null}

      {openMenu === "library" ? <section className="cinematic-utility-menu cinematic-library-menu" id="aperture-library-menu" ref={libraryPanelRef}>
        <div><h2>{personalLabel}</h2><p>Your saved stories and recent screens.</p></div>
        <nav aria-label={personalLabel}>
          {libraryItems.map((item) => <HeaderLink item={item} key={item.href} onNavigate={closeMenus} pathname={pathname} />)}
        </nav>
      </section> : null}

      {openMenu === "account" ? <section className="cinematic-utility-menu cinematic-account-menu" id="aperture-account-menu" ref={accountPanelRef}>
        <div><h2>Viewer space</h2><p>Profiles, membership and preferences.</p></div>
        <nav aria-label="Account navigation">
          {accountItems.map((item) => <HeaderLink item={item} key={item.href} onNavigate={closeMenus} pathname={pathname} />)}
          <Link className="cinematic-sign-in" href="/login" onClick={closeMenus}>Switch or sign in <span aria-hidden="true">→</span></Link>
        </nav>
      </section> : null}

      {openMenu === "mobile" ? <>
        <button className="cinematic-mobile-scrim" aria-label="Close menu" onClick={closeMenus} type="button" />
        <div
          aria-label={`${brand.business_name} menu`}
          aria-modal="true"
          className="cinematic-mobile-panel"
          id="aperture-mobile-menu"
          onKeyDown={trapMobileFocus}
          ref={mobilePanelRef}
          role="dialog"
        >
          <div className="cinematic-mobile-panel-heading"><h2>Where next?</h2><p>Browse the screen or return to your list.</p></div>
          <Link className="cinematic-mobile-search-field" href="/search" onClick={closeMenus}><NavIcon name="search" /><span>Search films, series and cast</span></Link>
          <nav className="cinematic-mobile-primary" aria-label={`Browse ${brand.business_name}`}>
            {[...primary, ...mobileRightNow].map((item) => <HeaderLink item={item} key={item.href} onNavigate={closeMenus} pathname={pathname} />)}
          </nav>
          <div className="cinematic-mobile-menu-groups">
            <nav aria-label="Your library"><h3>Your library</h3>{libraryItems.map((item) => <HeaderLink item={item} key={item.href} onNavigate={closeMenus} pathname={pathname} />)}</nav>
            <nav aria-label={`More from ${brand.business_name}`}><h3>More</h3>{[...goDeeper.slice(0, 2), { label: "Signal Run", href: "/game", icon: "game" as const }].map((item) => <HeaderLink item={item} key={item.href} onNavigate={closeMenus} pathname={pathname} />)}</nav>
          </div>
          <nav className="cinematic-mobile-account" aria-label="Account"><HeaderLink item={accountItems[0]} onNavigate={closeMenus} pathname={pathname} /><HeaderLink item={accountItems[1]} onNavigate={closeMenus} pathname={pathname} /><Link href="/login" onClick={closeMenus}>Switch or sign in</Link></nav>
        </div>
      </> : null}
    </header>

    <nav className="cinematic-mobile-dock" aria-label="Quick navigation">
      {[primary[0], primary[1], { label: "Search", href: "/search", icon: "search" as const }, { label: "My List", href: "/my-list", icon: "bookmark" as const }].map((item) =>
        <HeaderLink className={item.href === "/my-list" ? "cinematic-mobile-library-link" : undefined} item={item} key={item.href} onNavigate={closeMenus} pathname={pathname} />)}
    </nav>
  </>;
}
