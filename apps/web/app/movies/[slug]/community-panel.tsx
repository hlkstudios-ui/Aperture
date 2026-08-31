"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGatewayPath } from "@/app/lib/api-gateway";

type Review = { id:string; profile_id:string; profile_name:string|null; headline:string|null; body:string; contains_spoilers:boolean; status:string };
export type Community = { rating_count:number; average_rating:number|null; viewer_rating:number|null; reviews:Review[]; moderation_required:boolean };

export function CommunityPanel({ movieId, authenticated, initialCommunity }: { movieId:string; authenticated:boolean; initialCommunity:Community|null }) {
  const router = useRouter();
  const [community, setCommunity] = useState<Community|null>(initialCommunity);
  const [notice, setNotice] = useState("");
  const load = async () => {
    if (!authenticated) return;
    const response = await fetch(apiGatewayPath(`/community/movies/${movieId}`), { credentials:"include" });
    if (response.ok) setCommunity(await response.json() as Community);
  };
  const requireSignIn = () => { if (!authenticated) router.push("/login?next=community"); return authenticated; };
  const rate = async (score:number) => {
    if (!requireSignIn()) return;
    const response = await fetch(apiGatewayPath(`/community/movies/${movieId}/rating`), { method:"PUT", credentials:"include", headers:{"Content-Type":"application/json"}, body:JSON.stringify({score}) });
    setNotice(response.ok ? "Rating saved privately to this profile." : "Rating could not be saved.");
    if (response.ok) await load();
  };
  const submitReview = async (event:FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (!requireSignIn()) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const response = await fetch(apiGatewayPath(`/community/movies/${movieId}/review`), { method:"PUT", credentials:"include", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ headline:String(form.get("headline")??"" )||null, body:String(form.get("body")??""), contains_spoilers:form.get("spoilers")==="on" }) });
    setNotice(response.ok ? "Review submitted for moderation. It is not public yet." : "Review could not be submitted.");
    if (response.ok) formElement.reset();
  };
  const protect = async (review:Review, action:"report"|"follow"|"mute"|"block") => {
    if (!requireSignIn()) return;
    const response = action === "report"
      ? await fetch(apiGatewayPath("/community/reports"), { method:"POST", credentials:"include", headers:{"Content-Type":"application/json"}, body:JSON.stringify({review_id:review.id,reason:"other",details:"Reported from the movie community panel."}) })
      : action === "follow" ? await fetch(apiGatewayPath(`/community/follows/${review.profile_id}`), {method:"PUT",credentials:"include"})
      : await fetch(apiGatewayPath(`/community/safety/${review.profile_id}/${action}`), { method:"PUT", credentials:"include" });
    setNotice(response.ok ? (action === "report" ? "Report sent to moderation." : action === "follow" ? "Following this profile." : `${action === "mute" ? "Muted" : "Blocked"} this profile.`) : "Safety action could not be completed.");
    if (response.ok && (action === "mute" || action === "block")) await load();
  };
  return <section className="community-panel" aria-labelledby="community-heading">
    <div className="section-heading"><div><p className="eyebrow">Moderated community</p><h2 id="community-heading">Ratings & reviews</h2></div><p>{community?.rating_count ? `${community.average_rating} / 5 · ${community.rating_count} rating${community.rating_count===1?"":"s"}` : "No ratings yet"}</p></div>
    {!authenticated ? <div className="community-gate"><p>Sign in and select a profile to rate, review, report, mute, or block.</p><button onClick={()=>requireSignIn()} className="secondary">Sign in for community</button></div> : <>
      <div className="rating-control" aria-label="Rate this movie">{[1,2,3,4,5].map(score=><button key={score} type="button" aria-label={`Rate ${score} out of 5`} className={community?.viewer_rating===score?"selected":undefined} onClick={()=>void rate(score)}>{score}★</button>)}</div>
      <form className="review-form" onSubmit={submitReview}><label>Review headline<input name="headline" maxLength={140} /></label><label>Your review<textarea name="body" minLength={1} maxLength={5000} required /></label><label className="check-line"><input type="checkbox" name="spoilers" /> Contains spoilers</label><button className="primary">Submit for moderation</button></form>
    </>}
    {notice ? <p className="community-notice" role="status">{notice}</p> : null}
    <div className="review-list">{community?.reviews.map(review=><article key={review.id}><div><strong>{review.headline||"Review"}</strong><small>{review.profile_name}</small></div>{review.contains_spoilers?<details><summary>Spoiler-tagged review — reveal</summary><p>{review.body}</p></details>:<p>{review.body}</p>}<div className="compact-actions"><button onClick={()=>void protect(review,"follow")}>Follow</button><button onClick={()=>void protect(review,"report")}>Report</button><button onClick={()=>void protect(review,"mute")}>Mute</button><button onClick={()=>void protect(review,"block")}>Block</button></div></article>)}</div>
  </section>;
}
