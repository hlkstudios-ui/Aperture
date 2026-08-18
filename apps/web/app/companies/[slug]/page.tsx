import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch, type CreditDestination } from "@/app/lib/catalog";

export default async function CompanyPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params; let company: CreditDestination;
  try { company = await catalogFetch(`/catalog/companies/${encodeURIComponent(slug)}/credits`); }
  catch (error) { if ((error as Error & { status?: number }).status === 404) notFound(); throw error; }
  return <main className="credit-destination"><SiteHeader /><header><p className="eyebrow">Credits explorer · company</p><h1>{company.name}</h1><p>{company.country_code ? `Based in ${company.country_code}.` : "Verified company location is unavailable."}</p></header><section><h2>Available catalog credits</h2>{company.titles.length ? <ol>{company.titles.map((title) => <li key={`${title.kind}-${title.id}-${title.role}`}><Link href={title.href}><small>{title.kind} · {title.role}</small><strong>{title.title}</strong></Link></li>)}</ol> : <p>No currently available catalog title is connected to this company.</p>}</section></main>;
}
