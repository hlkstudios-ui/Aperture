import Link from "next/link";
import { approvedPolicies } from "@/app/lib/policies";

export function SiteFooter() {
  const policies = approvedPolicies();
  return <footer className="site-footer">
    <strong>Aperture</strong>
    {policies.length ? <nav aria-label="Policies">{policies.map((policy) =>
      <Link key={policy.slug} href={`/policies/${policy.slug}`}>{policy.title}</Link>)}</nav> : null}
    <Link href="/data-credits">Data credits</Link>
    <small>Policy documents appear only after accountable owner approval.</small>
  </footer>;
}
