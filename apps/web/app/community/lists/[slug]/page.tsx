import Link from "next/link";
import { SiteHeader } from "@/app/components/site-header";
import { customerAccountFetch } from "@/app/lib/account";
import type { Collection } from "@/app/lib/curation";
import { requireCustomerSession } from "@/app/lib/customer-session";
import { featureFlags } from "@/app/lib/feature-flags";
import { notFound } from "next/navigation";
export default async function CommunityListPage({params}:{params:Promise<{slug:string}>}){if(!featureFlags.community)notFound();await requireCustomerSession();const {slug}=await params;const list=await customerAccountFetch<Collection>(`/community/lists/${encodeURIComponent(slug)}`);return <main className="catalog-page"><SiteHeader/><section className="catalog-intro"><p className="eyebrow">List by {list.owner_profile_name}</p><h1>{list.title}</h1><p>{list.description}</p></section><section className="my-list-stack"><article><ol>{list.items.map(item=><li key={item.item_id}><Link href={`/${item.kind==="movie"?"movies":"series"}/${item.slug}`}><strong>{item.title}</strong><span>{item.short_description}</span></Link></li>)}</ol></article></section></main>}
