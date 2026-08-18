"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

export function ResetRequestForm() {
  const [message, setMessage] = useState("");
  const [developmentToken, setDevelopmentToken] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const response = await fetch(`${apiOrigin}/auth/password-reset/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: data.get("email") }),
    });
    const body = await response.json().catch(() => null);
    setMessage(body?.message ?? "Unable to request a password reset right now.");
    setDevelopmentToken(body?.development_reset_token ?? "");
  }

  return (
    <form className="login-form" onSubmit={submit}>
      <label htmlFor="reset-email">Account email</label>
      <input id="reset-email" name="email" type="email" autoComplete="email" required />
      <button className="primary" type="submit">Send reset instructions</button>
      {message && <p className="field-hint" role="status">{message}</p>}
      {developmentToken && <Link className="development-link" href={`/reset-password?token=${encodeURIComponent(developmentToken)}`}>Open development reset link</Link>}
    </form>
  );
}

