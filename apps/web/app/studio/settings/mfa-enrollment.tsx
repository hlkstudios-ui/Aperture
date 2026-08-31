"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { API_GATEWAY_PREFIX } from "@/app/lib/api-gateway";

const apiOrigin = API_GATEWAY_PREFIX;

export function MfaEnrollment({ enabled }: { enabled: boolean }) {
  const router = useRouter();
  const [secret, setSecret] = useState("");
  const [provisioningUri, setProvisioningUri] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function begin() {
    setBusy(true);
    setMessage("");
    const response = await fetch(`${apiOrigin}/admin/auth/mfa/enroll`, {
      method: "POST",
      credentials: "include",
    });
    const body = await response.json().catch(() => null);
    setBusy(false);
    if (!response.ok) {
      setMessage(body?.detail ?? "MFA enrollment could not be started.");
      return;
    }
    setSecret(body.secret);
    setProvisioningUri(body.provisioning_uri);
    setRecoveryCodes([]);
    setMessage("Add the key to your authenticator, then confirm a current code.");
  }

  async function confirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const code = new FormData(event.currentTarget).get("code");
    const response = await fetch(`${apiOrigin}/admin/auth/mfa/confirm`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const body = await response.json().catch(() => null);
    setBusy(false);
    if (!response.ok) {
      setMessage(body?.detail ?? "The security code could not be confirmed.");
      return;
    }
    setRecoveryCodes(body.recovery_codes);
    setSecret("");
    setProvisioningUri("");
    setMessage("MFA is enabled. Store every recovery code offline now; they are shown once.");
    router.refresh();
  }

  return <article className="system-card">
    <h2>{enabled ? "MFA enabled" : "Enable multi-factor authentication"}</h2>
    <p>{enabled ? "Studio login requires a current authenticator code or one unused recovery code." : "Protect the single administrator with a time-based authenticator code."}</p>
    {!enabled && !secret && !recoveryCodes.length && <button className="studio-primary" type="button" disabled={busy} onClick={() => void begin()}>Start MFA enrollment</button>}
    {secret && <div className="mfa-enrollment">
      <p><strong>Manual authenticator key</strong></p>
      <code data-testid="mfa-secret">{secret}</code>
      <details><summary>Authenticator provisioning URI</summary><code>{provisioningUri}</code></details>
      <form onSubmit={confirm}>
        <label htmlFor="mfa-confirm-code">Current six-digit code</label>
        <input id="mfa-confirm-code" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required />
        <button className="studio-primary" disabled={busy}>Confirm and enable MFA</button>
      </form>
    </div>}
    {recoveryCodes.length > 0 && <div className="mfa-recovery" role="status">
      <h3>One-use recovery codes</h3>
      <p>Store these in an approved password manager. Leaving this page permanently hides them.</p>
      <ul>{recoveryCodes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
    </div>}
    {message && <p role="status">{message}</p>}
  </article>;
}
