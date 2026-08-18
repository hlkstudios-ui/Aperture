import Link from "next/link";
import { SiteHeader } from "@/app/components/site-header";
import { customerAccountFetch } from "@/app/lib/account";
import { Collection } from "@/app/lib/curation";
import { requireCustomerSession } from "@/app/lib/customer-session";
import { setListVisibility } from "./actions";

export default async function MyListPage() {
  await requireCustomerSession();
  const lists = await customerAccountFetch<Collection[]>("/curation/my-lists");
  return <main className="catalog-page"><SiteHeader /><section className="catalog-intro"><p className="eyebrow">Private to this profile</p><h1>My List</h1><p>Saved movies and series, kept separate from Aperture&apos;s editorial collections.</p></section>
    <section className="my-list-stack">{lists.map((list) => <article key={list.id}><div className="section-heading"><div><h2>{list.title}</h2>{list.description && <p>{list.description}</p>}</div><form action={setListVisibility.bind(null,list)} className="list-visibility"><label>Visibility<select name="visibility" defaultValue={list.visibility}><option value="private">Private</option><option value="unlisted">Unlisted</option><option value="public">Public</option></select></label><button className="secondary">Save visibility</button></form></div>{list.visibility!=="private"?<p className="community-notice">Moderation: {list.moderation_status}. Public discovery stays disabled until approval.</p>:null}<ol>{list.items.map((item) => <li key={item.item_id}><Link href={`/${item.kind === "movie" ? "movies" : "series"}/${item.slug}`}><strong>{item.title}</strong><span>{item.short_description}</span></Link></li>)}</ol></article>)}{!lists.length && <div className="studio-empty"><h2>Your list is empty</h2><p>Use “My List” on a movie page to save your first title.</p><Link href="/movies">Browse movies</Link></div>}</section>
  </main>;
}
