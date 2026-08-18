"use client";

import Link from "next/link";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";
const providerPresentation = { google: { label: "Google", mark: "G" }, microsoft: { label: "Microsoft", mark: "⊞" }, github: { label: "GitHub", mark: "⌘" }, apple: { label: "Apple", mark: "●" } };
type AuthCapabilities = { captcha: { required: boolean; test_mode: boolean }; providers: { id: keyof typeof providerPresentation; label: string; enabled: boolean }[] };
type RememberedAccount = { id: string; email: string; provider: string; label: string };

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [capabilities, setCapabilities] = useState<AuthCapabilities | null>(null);
  const [remembered, setRemembered] = useState<RememberedAccount[]>([]);
  const [selectedEmail, setSelectedEmail] = useState("");

  useEffect(() => {
    fetch(`${apiOrigin}/auth/oauth/providers`).then((response) => response.ok ? response.json() : Promise.reject()).then(setCapabilities).catch(() => setCapabilities(null));
    fetch(`${apiOrigin}/auth/remembered-accounts`, { credentials: "include" }).then((response) => response.ok ? response.json() : Promise.reject()).then((data) => setRemembered(data.accounts ?? [])).catch(() => setRemembered([]));
  }, []);

  function chooseAccount(account: RememberedAccount) {
    if (account.provider !== "email") {
      router.push(`${apiOrigin}/auth/oauth/${account.provider}/start`);
      return;
    }
    setSelectedEmail(account.email);
    document.getElementById("viewer-password")?.focus();
  }

  async function removeAccount(account: RememberedAccount) {
    await fetch(`${apiOrigin}/auth/remembered-accounts/${account.id}`, { method: "DELETE", credentials: "include" });
    setRemembered((current) => current.filter((item) => item.id !== account.id));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const payload = {
      email: data.get("email"),
      password: data.get("password"),
      ...(mode === "register" ? { profile_name: data.get("profile_name") } : {}),
      captcha_token: capabilities?.captcha.test_mode ? "local-captcha-pass" : data.get("cf-turnstile-response"),
    };
    try {
      const response = await fetch(`${apiOrigin}/auth/${mode === "register" ? "register" : "login"}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const detail = Array.isArray(body?.detail)
          ? body.detail.map((item: { msg: string }) => item.msg).join(" ")
          : body?.detail;
        setError(detail ?? "We could not complete that request.");
        return;
      }
      router.replace("/profiles");
      router.refresh();
    } catch {
      setError("The account service is unavailable. Try again shortly.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className={`auth-form-experience ${remembered.length ? "has-remembered" : ""}`}>
    {remembered.length > 0 && <aside className="remembered-accounts" aria-label="Accounts saved on this device"><header><p className="eyebrow">Welcome back</p><h2>Choose an account</h2><small>Saved securely on this device</small></header><div>{remembered.map((account) => <article key={account.id}><button type="button" className="remembered-choice" onClick={() => chooseAccount(account)}><i aria-hidden="true">{account.label.slice(0, 1).toUpperCase()}</i><span><strong>{account.label}</strong><small>{account.email}</small><em>{account.provider === "email" ? "Email" : account.provider}</em></span></button><button type="button" className="forget-account" aria-label={`Remove ${account.email} from this device`} onClick={() => removeAccount(account)}>×</button></article>)}</div><p>No passwords are stored.</p></aside>}
    <div className="auth-entry"><section className="social-auth" aria-label="Single sign-on options">
      <p>Continue securely with</p><div className="social-auth-grid">
        {Object.entries(providerPresentation).map(([id, item]) => {
          const configured = capabilities?.providers.find((provider) => provider.id === id)?.enabled;
          return configured ? <a className={`social-provider provider-${id}`} href={`${apiOrigin}/auth/oauth/${id}/start`} key={id}><i aria-hidden="true">{item.mark}</i><span>{item.label}</span></a> : <span className="social-provider is-unavailable" title="Add this provider's credentials to enable it" key={id} aria-disabled="true"><i aria-hidden="true">{item.mark}</i><span>{item.label}</span><small>Setup</small></span>;
        })}
      </div><div className="auth-divider"><span>or use email</span></div>
    </section><form className="login-form" onSubmit={submit}>
      {mode === "register" && <><label htmlFor="profile-name">Your profile name</label><input id="profile-name" name="profile_name" autoComplete="nickname" maxLength={50} required /></>}
      <label htmlFor="viewer-email">Email</label>
      <input id="viewer-email" name="email" type="email" autoComplete="email" value={selectedEmail} onChange={(event) => setSelectedEmail(event.target.value)} required />
      <label htmlFor="viewer-password">Password</label>
      <input id="viewer-password" name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 12 : 1} required />
      {mode === "register" && <p className="field-hint">Use at least 12 characters with uppercase, lowercase, and a number.</p>}
      {capabilities?.captcha.required && capabilities.captcha.test_mode && <div className="captcha-local"><span aria-hidden="true">✓</span><div><strong>Local security check</strong><small>Test mode — production uses Turnstile</small></div></div>}
      {capabilities?.captcha.required && !capabilities.captcha.test_mode && <><Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" strategy="afterInteractive" /><div className="cf-turnstile captcha-widget" data-sitekey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY} data-theme="dark" /></>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary" type="submit" disabled={pending}>{pending ? "Please wait…" : mode === "login" ? "Continue" : "Create account"}</button>
      <div className="form-links">
        {mode === "login" ? <><Link href="/forgot-password">Forgot password?</Link><Link href="/register">Create an account</Link></> : <Link href="/login">Already have an account?</Link>}
      </div>
    </form><p className="auth-privacy">Protected by encrypted sessions, OAuth state validation, PKCE, and bot verification.</p></div></div>
  );
}
