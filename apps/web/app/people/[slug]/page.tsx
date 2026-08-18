import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteHeader } from "@/app/components/site-header";
import { catalogFetch, type CreditDestination } from "@/app/lib/catalog";

export default async function PersonPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params; let person: CreditDestination;
  try { person = await catalogFetch(`/catalog/people/${encodeURIComponent(slug)}/credits`); }
  catch (error) { if ((error as Error & { status?: number }).status === 404) notFound(); throw error; }
  return <main className="credit-destination"><SiteHeader /><header><p className="eyebrow">Credits explorer · person</p><h1>{person.name}</h1><p>{person.biography ?? "No verified biography is available."}</p></header><section><h2>Available catalog credits</h2>{person.titles.length ? <ol>{person.titles.map((title) => <li key={`${title.kind}-${title.id}-${title.role}`}><Link href={title.href}><small>{title.kind} · {title.role}</small><strong>{title.title}</strong>{title.character_name ? <span>as {title.character_name}</span> : null}</Link></li>)}</ol> : <p>No currently available catalog title is connected to this person.</p>}</section></main>;
}
