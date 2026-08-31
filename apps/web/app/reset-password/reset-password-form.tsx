"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { apiGatewayPath } from "@/app/lib/api-gateway";

export function ResetPasswordForm({ token }: { token: string }) {
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const data = new FormData(event.currentTarget);
    if (data.get("password") !== data.get("confirmation")) { setError("Passwords do not match."); return; }
    const response = await fetch(apiGatewayPath("/auth/password-reset/confirm"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, password: data.get("password") }),
    });
    if (!response.ok) { const body = await response.json().catch(() => null); setError(body?.detail ?? "The reset link is invalid or expired."); return; }
    setComplete(true);
  }

  if (complete) return <div className="reset-complete"><p>Password updated. Existing sessions have been signed out.</p><Link href="/login">Continue to sign in</Link></div>;
  return <form className="login-form" onSubmit={submit}><label htmlFor="new-password">New password</label><input id="new-password" name="password" type="password" minLength={12} autoComplete="new-password" required /><label htmlFor="confirm-password">Confirm password</label><input id="confirm-password" name="confirmation" type="password" minLength={12} autoComplete="new-password" required />{error && <p className="form-error" role="alert">{error}</p>}<button className="primary" type="submit">Update password</button></form>;
}

