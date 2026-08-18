import { adminCatalogFetch } from "@/app/lib/admin-catalog";
import { requireAdminSession } from "@/app/lib/admin-session";
import { StudioShell } from "@/app/studio/components/studio-shell";
import { moderateList, moderateReport, moderateReview } from "./actions";

type Review={id:string;headline:string|null;body:string;contains_spoilers:boolean;profile_id:string;created_at:string};
type List={id:string;title:string;description:string;owner_profile_name:string|null;visibility:string;items:Array<{title:string}>};
type Report={id:string;reason:string;details:string|null;review_id:string|null;collection_id:string|null;created_at:string};
type Queue={reviews:Review[];lists:List[];reports:Report[]};
function DecisionForm({action, approve=true}:{action:(form:FormData)=>void|Promise<void>;approve?:boolean}) { return <form action={action} className="moderation-decision"><label>Decision reason<textarea name="reason" minLength={3} maxLength={1000} required /></label><button className={approve?"primary":"secondary"}>{approve?"Approve":"Reject"}</button></form>; }
export default async function CommunityModerationPage(){
  const [admin,queue]=await Promise.all([requireAdminSession(),adminCatalogFetch<Queue>("/admin/community/queue")]);
  return <StudioShell admin={admin} active="community" eyebrow="Trust & safety" title="Community moderation">
    <section className="editor-panel"><div className="section-heading"><div><p className="eyebrow">Fail-closed publication</p><h2>Pending reviews</h2></div><span className="catalog-badge">{queue.reviews.length}</span></div><div className="moderation-stack">{queue.reviews.map(item=><article key={item.id}><p className="eyebrow">{item.contains_spoilers?"Spoiler flagged":"No spoiler flag"}</p><h3>{item.headline||"Untitled review"}</h3><p>{item.body}</p><div className="moderation-actions"><DecisionForm action={moderateReview.bind(null,item.id,"approved")} /><DecisionForm action={moderateReview.bind(null,item.id,"rejected")} approve={false} /></div></article>)}{!queue.reviews.length?<p className="empty-inline">No pending reviews.</p>:null}</div></section>
    <section className="editor-panel"><div className="section-heading"><div><p className="eyebrow">Public list review</p><h2>Pending lists</h2></div><span className="catalog-badge">{queue.lists.length}</span></div><div className="moderation-stack">{queue.lists.map(item=><article key={item.id}><h3>{item.title}</h3><p>{item.description}</p><small>{item.owner_profile_name} · {item.visibility} · {item.items.length} titles</small><div className="moderation-actions"><DecisionForm action={moderateList.bind(null,item.id,"approved")} /><DecisionForm action={moderateList.bind(null,item.id,"rejected")} approve={false} /></div></article>)}{!queue.lists.length?<p className="empty-inline">No pending public lists.</p>:null}</div></section>
    <section className="editor-panel"><div className="section-heading"><div><p className="eyebrow">Abuse reports</p><h2>Open reports</h2></div><span className="catalog-badge">{queue.reports.length}</span></div><div className="moderation-stack">{queue.reports.map(item=><article key={item.id}><h3>{item.reason}</h3><p>{item.details||"No additional details."}</p><small>Target {item.review_id?"review":"list"}</small><div className="moderation-actions"><DecisionForm action={moderateReport.bind(null,item.id,"resolved")} /><DecisionForm action={moderateReport.bind(null,item.id,"dismissed")} approve={false} /></div></article>)}{!queue.reports.length?<p className="empty-inline">No open reports.</p>:null}</div></section>
  </StudioShell>;
}
