import Link from "next/link";

import { requireCustomerSession } from "@/app/lib/customer-session";

import { ProfileSelector } from "./profile-selector";

export const metadata = { title: "Choose Profile" };

export default async function ProfilesPage() {
  const account = await requireCustomerSession();
  return (
    <main className="profiles-shell">
      <header><Link className="wordmark" href="/">APERTURE</Link><span>{account.email}</span></header>
      <section aria-labelledby="profiles-title"><p className="eyebrow">One account, distinct film lives</p><h1 id="profiles-title">Who&apos;s watching?</h1><ProfileSelector account={account} /></section>
    </main>
  );
}

