"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import type { ViewerAccount, ViewerProfile } from "@/app/lib/customer-session";

const apiOrigin = process.env.NEXT_PUBLIC_API_ORIGIN ?? "http://localhost:8000";

export function ProfileSelector({ account }: { account: ViewerAccount }) {
  const router = useRouter();
  const [profiles, setProfiles] = useState(account.profiles);
  const [active, setActive] = useState(account.active_profile_id);
  const [error, setError] = useState("");

  async function switchTo(profile: ViewerProfile) {
    setError("");
    const response = await fetch(`${apiOrigin}/profiles/${profile.id}/switch`, { method: "POST", credentials: "include" });
    if (!response.ok) { setError("That profile could not be selected."); return; }
    setActive(profile.id);
    router.refresh();
  }

  async function createProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    const response = await fetch(`${apiOrigin}/profiles`, {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: data.get("name"), is_kids: data.get("is_kids") === "on", maturity_level: data.get("is_kids") === "on" ? "kids" : "adult" }),
    });
    if (!response.ok) { setError("The profile could not be created."); return; }
    const profile = await response.json() as ViewerProfile;
    setProfiles((current) => [...current, profile]);
    form.reset();
  }

  return (
    <>
      <div className="profile-grid">
        {profiles.map((profile, index) => <button className={active === profile.id ? "profile-card active" : "profile-card"} key={profile.id} onClick={() => switchTo(profile)} type="button"><span className={`avatar avatar-${index % 5}`}>{profile.name.slice(0, 1).toUpperCase()}</span><strong>{profile.name}</strong><small>{profile.is_kids ? "Kids" : profile.preference.cinephile_mode ? "Cinephile Mode" : "Normal Mode"}</small></button>)}
      </div>
      {profiles.length < 5 && <form className="add-profile" onSubmit={createProfile}><label htmlFor="new-profile">Add another profile</label><div><input id="new-profile" name="name" maxLength={50} placeholder="Profile name" required /><label className="check"><input name="is_kids" type="checkbox" /> Kids</label><button type="submit">Add profile</button></div></form>}
      {error && <p className="form-error" role="alert">{error}</p>}
    </>
  );
}

