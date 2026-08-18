import Link from "next/link";

import { AuthForm } from "./auth-form";

export const metadata = { title: "Sign In" };

export default function LoginPage() {
  return (
    <main className="viewer-auth-shell">
      <Link className="wordmark" href="/">APERTURE</Link>
      <section className="viewer-auth-card" aria-labelledby="sign-in-title">
        <p className="eyebrow">Welcome back</p><h1 id="sign-in-title">Your next film is waiting.</h1>
        <AuthForm mode="login" />
      </section>
    </main>
  );
}

