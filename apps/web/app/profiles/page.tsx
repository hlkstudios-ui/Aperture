import Link from "next/link";

import { requireCustomerSession } from "@/app/lib/customer-session";
import { getSiteBrand } from "@/app/lib/site-brand-server";

import { ProfileSelector } from "./profile-selector";

export const metadata = { title: "Choose Profile" };

export default async function ProfilesPage() {
  const [account, brand] = await Promise.all([requireCustomerSession(), getSiteBrand()]);
  return (
    <main className="profiles-shell">
      <header>
        <Link className="wordmark" href="/">{brand.short_name.toUpperCase()}</Link>
        <div className="profiles-account" title={account.email}>
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M12 12.2a4.1 4.1 0 1 0 0-8.2 4.1 4.1 0 0 0 0 8.2Zm-7 7.3c.8-3.4 3.4-5.3 7-5.3s6.2 1.9 7 5.3" />
          </svg>
          <span>{account.email}</span>
        </div>
      </header>
      <section aria-labelledby="profiles-title">
        <div className="profiles-intro">
          <p className="eyebrow">One account, distinct film lives</p>
          <h1 id="profiles-title">Who&apos;s watching?</h1>
          <p>Choose a profile to enter your personal cinema.</p>
        </div>
        <ProfileSelector account={account} />
      </section>
    </main>
  );
}

