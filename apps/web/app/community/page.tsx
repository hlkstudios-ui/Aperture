import Link from "next/link";
import { SiteHeader } from "@/app/components/site-header";
import { customerAccountFetch } from "@/app/lib/account";
import type { Collection } from "@/app/lib/curation";
import { requireCustomerSession } from "@/app/lib/customer-session";
import { featureFlags } from "@/app/lib/feature-flags";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

type Activity={id:string;kind:string;actor_profile_name:string;review_id:string|null;collection_id:string|null;created_at:string};
export default async function CommunityPage(){
  if (!featureFlags.community) notFound();
  await requireCustomerSession();
  const [lists,activity]=await Promise.all([customerAccountFetch<Collection[]>("/community/lists"),customerAccountFetch<Activity[]>("/community/activity")]);
  return <main className="catalog-page"><SiteHeader/><section className="catalog-intro"><p className="eyebrow">Moderated discovery</p><h1>Community</h1><p>Approved lists and activity from profiles you follow. Reports, spoiler labels, mute, and block controls remain available at the content source.</p></section><section className="community-directory"><div><div className="section-heading"><div><p className="eyebrow">Approved only</p><h2>Community lists</h2></div></div><div className="curation-grid">{lists.map(list=><Link className="curation-card" href={`/community/lists/${list.slug}`} key={list.id}><small>{list.owner_profile_name}</small><h2>{list.title}</h2><p>{list.description}</p><span>{list.items.length} available titles →</span></Link>)}{!lists.length?<p className="empty-inline">No approved public lists are available yet.</p>:null}</div></div><div><div className="section-heading"><div><p className="eyebrow">Safety filtered</p><h2>Following activity</h2></div></div><ol className="activity-list">{activity.map(item=><li key={item.id}><strong>{item.actor_profile_name}</strong><span>{item.kind.replaceAll("_"," ")}</span><time>{new Date(item.created_at).toLocaleDateString("en-CA")}</time></li>)}{!activity.length?<li>No activity from followed profiles.</li>:null}</ol></div></section></main>;
}
