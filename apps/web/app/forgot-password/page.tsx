import Link from "next/link";
import { getSiteBrand } from "@/app/lib/site-brand-server";

import { ResetRequestForm } from "./reset-request-form";

export const metadata = { title: "Reset Password" };

export default async function ForgotPasswordPage() {
  const brand = await getSiteBrand();
  return <main className="viewer-auth-shell"><Link className="wordmark" href="/">{brand.short_name.toUpperCase()}</Link><section className="viewer-auth-card"><p className="eyebrow">Account recovery</p><h1>Find your way back.</h1><p className="auth-intro">Enter your email. The response is intentionally identical whether or not an account exists.</p><ResetRequestForm /></section></main>;
}

