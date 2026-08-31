"use client";

import { FormEvent, useState } from "react";
import { apiGatewayPath } from "@/app/lib/api-gateway";

export function LoginForm() {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const response = await fetch(apiGatewayPath("/admin/auth/login"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: data.get("email"),
          password: data.get("password"),
          ...(data.get("mfa_code") ? { mfa_code: data.get("mfa_code") } : {}),
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setError(
          body?.detail ??
            "Sign-in failed. Check your credentials and try again.",
        );
        return;
      }
      // The administrator cookie is issued through the same-origin gateway. A document
      // navigation guarantees it is committed before the authenticated
      // Server Component and Studio proxy inspect the next request.
      window.location.replace("/studio");
    } catch {
      setError("The authentication service is unavailable. Try again shortly.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="login-form" onSubmit={submit}>
      <label htmlFor="admin-email">Administrator email</label>
      <input
        id="admin-email"
        name="email"
        type="email"
        autoComplete="username"
        required
      />
      <label htmlFor="admin-password">Password</label>
      <input
        id="admin-password"
        name="password"
        type="password"
        autoComplete="current-password"
        required
      />
      <label htmlFor="admin-mfa">
        Security code <span className="optional">when MFA is enabled</span>
      </label>
      <input
        id="admin-mfa"
        name="mfa_code"
        inputMode="numeric"
        autoComplete="one-time-code"
      />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <button className="primary" type="submit" disabled={pending}>
        {pending ? "Signing in…" : "Enter Studio"}
      </button>
    </form>
  );
}
