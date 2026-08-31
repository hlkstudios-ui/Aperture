import Link from "next/link";
import { getSiteBrand } from "@/app/lib/site-brand-server";

import { AuthForm } from "../login/auth-form";

export const metadata = { title: "Create Account" };

export default async function RegisterPage() {
  const brand = await getSiteBrand();
  return (
    <main className="viewer-auth-shell">
      <Link className="wordmark" href="/">{brand.short_name.toUpperCase()}</Link>
      <section className="viewer-auth-card" aria-labelledby="register-title">
        <p className="eyebrow">Begin your film history</p><h1 id="register-title">Make cinema personal.</h1>
        <AuthForm mode="register" />
      </section>
    </main>
  );
}

