import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import type { LaunchSetupRecord } from "@/app/studio/launch/launch-setup-types";
import { signOutAdmin } from "./actions";

type Admin = { email: string };

type StudioNavigationGroup = {
  label: string;
  items: ReadonlyArray<readonly [label: string, href: string]>;
};

const navigationGroups: ReadonlyArray<StudioNavigationGroup> = [
  {
    label: "Overview",
    items: [["Dashboard", "/studio"]],
  },
  {
    label: "Programming",
    items: [
      ["Content", "/studio/content"],
      ["Movies", "/studio/movies"],
      ["Series", "/studio/series"],
      ["Homepage", "/studio/homepage"],
      ["Explore", "/studio/explore"],
      ["Curation", "/studio/curation"],
    ],
  },
  {
    label: "Production",
    items: [
      ["Uploads", "/studio/uploads"],
      ["Processing", "/studio/processing"],
      ["Media Sources", "/studio/sources"],
      ["Scene Data", "/studio/scenes"],
      ["Knowledge", "/studio/knowledge"],
    ],
  },
  {
    label: "Audience",
    items: [
      ["Analytics", "/studio/analytics"],
      ["Community", "/studio/community"],
      ["Users", "/studio/users"],
      ["Customer payments", "/studio/monetization"],
      ["Subscriptions", "/studio/subscriptions"],
      ["Revenue", "/studio/revenue"],
    ],
  },
  {
    label: "System",
    items: [
      ["Operations", "/studio/operations"],
      ["Storage", "/studio/storage"],
      ["Launch Setup", "/studio/launch"],
      ["Legal & policy", "/studio/legal-policy"],
      ["Domains", "/studio/domains"],
      ["Settings", "/studio/settings"],
    ],
  },
] as const;

const navigationIndex = new Map<string, number>(
  navigationGroups
    .flatMap((group) => group.items)
    .map(([, href], index) => [href, index + 1]),
);

function Navigation({ active, setupOnly }: { active: string; setupOnly: boolean }) {
  const visibleGroups = setupOnly
    ? [{
      label: "Setup",
      items: [
        ["Launch Setup", "/studio/launch"],
        ["Legal & policy", "/studio/legal-policy"],
        ["Customer payments", "/studio/monetization"],
      ] as const,
    }]
    : navigationGroups;
  return (
    <>
      {visibleGroups.map((group) => (
        <section className="studio-nav-group" key={group.label}>
          <p>{group.label}</p>
          {group.items.map(([label, href]) => {
            const selected = active === label.toLowerCase();
            return (
              <Link
                aria-current={selected ? "page" : undefined}
                className={selected ? "active" : undefined}
                href={href}
                prefetch={false}
                key={href}
              >
                <span aria-hidden="true" className="studio-nav-index">
                  {String(navigationIndex.get(href)).padStart(2, "0")}
                </span>
                <span>{label}</span>
              </Link>
            );
          })}
        </section>
      ))}
    </>
  );
}

export function studioAccessRequiresLaunch({
  setupOnly,
  publishedAt,
  appEnv,
}: {
  setupOnly: boolean;
  publishedAt: string | null;
  appEnv: string | undefined;
}): boolean {
  return !setupOnly && appEnv !== "test" && !publishedAt;
}

export async function StudioShell({
  admin,
  active,
  eyebrow,
  title,
  actions,
  setupOnly = false,
  children,
}: {
  admin: Admin;
  active: string;
  eyebrow: string;
  title: string;
  actions?: ReactNode;
  setupOnly?: boolean;
  children: ReactNode;
}) {
  if (!setupOnly && process.env.APP_ENV !== "test") {
    const launchSetup = await adminCatalogFetch<LaunchSetupRecord>("/admin/site/brand");
    if (studioAccessRequiresLaunch({
      setupOnly,
      publishedAt: launchSetup.published_at,
      appEnv: process.env.APP_ENV,
    })) {
      redirect("/studio/launch");
    }
  }
  return (
    <main className="studio-shell">
      <aside>
        <div className="studio-brand-lockup">
          <Link className="wordmark" href="/" prefetch={false}>
            APERTURE <span>STUDIO</span>
          </Link>
          <p>Production console</p>
        </div>
        <nav aria-label="Studio navigation">
          <Navigation active={active} setupOnly={setupOnly} />
        </nav>
        <div className="studio-access-card">
          <span><i /> Restricted workspace</span>
          <strong>{admin.email}</strong>
          <form action={signOutAdmin}><button type="submit">Sign out</button></form>
        </div>
      </aside>
      <header className="studio-mobile-header">
        <Link className="wordmark" href="/" prefetch={false}>
          APERTURE <span>STUDIO</span>
        </Link>
        <details className="mobile-menu">
          <summary>Menu</summary>
          <nav aria-label="Mobile Studio navigation">
            <Navigation active={active} setupOnly={setupOnly} />
            <form action={signOutAdmin}><button type="submit">Sign out</button></form>
          </nav>
        </details>
      </header>
      <section className="studio-main">
        <header className="studio-page-header">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
            <p className="signed-in-as">Signed in as {admin.email}</p>
          </div>
          {actions}
        </header>
        {children}
      </section>
    </main>
  );
}
