import Link from "next/link";
import type { ReactNode } from "react";
import { signOutAdmin } from "./actions";

type Admin = { email: string };

const liveSections = [
  ["Dashboard", "/studio"],
  ["Content", "/studio/content"],
  ["Movies", "/studio/movies"],
  ["Series", "/studio/series"],
  ["Uploads", "/studio/uploads"],
  ["Processing", "/studio/processing"],
  ["Homepage", "/studio/homepage"],
  ["Analytics", "/studio/analytics"],
  ["Operations", "/studio/operations"],
  ["Scene Data", "/studio/scenes"],
  ["Knowledge", "/studio/knowledge"],
  ["Curation", "/studio/curation"],
  ["Community", "/studio/community"],
  ["Users", "/studio/users"],
  ["Subscriptions", "/studio/subscriptions"],
  ["Storage", "/studio/storage"],
] as const;

function Navigation({ active }: { active: string }) {
  return (
    <>
      {liveSections.map(([label, href]) => (
        <Link
          className={active === label.toLowerCase() ? "active" : undefined}
          href={href}
          key={href}
        >
          {label}
        </Link>
      ))}
      <Link
        className={active === "settings" ? "active" : undefined}
        href="/studio/settings"
      >
        Settings
      </Link>
    </>
  );
}

export function StudioShell({
  admin,
  active,
  eyebrow,
  title,
  actions,
  children,
}: {
  admin: Admin;
  active: string;
  eyebrow: string;
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="studio-shell">
      <aside>
        <Link className="wordmark" href="/">
          APERTURE <span>STUDIO</span>
        </Link>
        <nav aria-label="Studio navigation">
          <Navigation active={active} />
        </nav>
        <p className="access-note">
          Private administrator workspace
          <br />
          {admin.email}
        </p>
        <form action={signOutAdmin}><button type="submit">Sign out</button></form>
      </aside>
      <header className="studio-mobile-header">
        <Link className="wordmark" href="/">
          APERTURE <span>STUDIO</span>
        </Link>
        <details className="mobile-menu">
          <summary>Menu</summary>
          <nav aria-label="Mobile Studio navigation">
            <Navigation active={active} />
            <form action={signOutAdmin}><button type="submit">Sign out</button></form>
          </nav>
        </details>
      </header>
      <section className="studio-main">
        <header>
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
