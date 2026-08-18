import Link from "next/link";

import { ResetPasswordForm } from "./reset-password-form";

export const metadata = { title: "Choose New Password" };

export default async function ResetPasswordPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  return <main className="viewer-auth-shell"><Link className="wordmark" href="/">APERTURE</Link><section className="viewer-auth-card"><p className="eyebrow">Secure reset</p><h1>Choose a new password.</h1>{token ? <ResetPasswordForm token={token} /> : <p className="form-error">This reset link is incomplete. Request a new one.</p>}</section></main>;
}

