import Link from "next/link";

import { LoginForm } from "./login-form";

export const metadata = { title: "Studio Sign In" };

export default function StudioLogin() {
  return (
    <main className="login-shell">
      <section className="login-brand">
        <Link className="wordmark" href="/">
          APERTURE <span>STUDIO</span>
        </Link>
        <div>
          <p className="eyebrow">Private access</p>
          <h1>The room behind the screen.</h1>
          <p>
            Publishing, processing, and platform operations for the single
            authorized administrator.
          </p>
        </div>
      </section>
      <section className="login-panel" aria-labelledby="login-title">
        <p className="eyebrow">Administrator</p>
        <h2 id="login-title">Sign in to Studio</h2>
        <p>There is no public administrator registration.</p>
        <LoginForm />
      </section>
    </main>
  );
}
