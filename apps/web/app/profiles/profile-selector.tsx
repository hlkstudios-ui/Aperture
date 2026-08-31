"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import type { ViewerAccount, ViewerProfile } from "@/app/lib/customer-session";
import { apiGatewayPath } from "@/app/lib/api-gateway";

function CheckIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m6.5 12.4 3.4 3.4 7.6-8" />
    </svg>
  );
}

function KidsIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 32 32">
      <path d="M10.5 11.2 8.1 6.6M21.5 11.2l2.4-4.6M8.7 6.4l-2 .4M23.3 6.4l2 .4" />
      <path d="M6.5 17.2c0-5.2 3.8-8.7 9.5-8.7s9.5 3.5 9.5 8.7c0 5.1-4 8.3-9.5 8.3s-9.5-3.2-9.5-8.3Z" />
      <path d="M12.2 16.4h.1M19.7 16.4h.1M12.4 20.2c2.1 1.6 5.1 1.6 7.2 0" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function ProfileSelector({ account }: { account: ViewerAccount }) {
  const router = useRouter();
  const [profiles, setProfiles] = useState(account.profiles);
  const [active, setActive] = useState(account.active_profile_id);
  const [error, setError] = useState("");
  const [switchingProfileId, setSwitchingProfileId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  async function switchTo(profile: ViewerProfile) {
    if (profile.id === active || switchingProfileId !== null) return;
    setError("");
    setSwitchingProfileId(profile.id);
    try {
      const response = await fetch(apiGatewayPath(`/profiles/${profile.id}/switch`), { method: "POST", credentials: "include" });
      if (!response.ok) { setError("That profile could not be selected."); return; }
      setActive(profile.id);
      try { sessionStorage.removeItem("aperture:document-locale"); } catch { /* optional cache */ }
      router.refresh();
    } catch {
      setError("That profile could not be selected.");
    } finally {
      setSwitchingProfileId(null);
    }
  }

  async function createProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsCreating(true);
    const form = event.currentTarget;
    const data = new FormData(form);
    const isKids = data.get("is_kids") === "on";
    try {
      const response = await fetch(apiGatewayPath("/profiles"), {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: data.get("name"), is_kids: isKids, maturity_level: isKids ? "kids" : "adult" }),
      });
      if (!response.ok) { setError("The profile could not be created."); return; }
      const profile = await response.json() as ViewerProfile;
      setProfiles((current) => [...current, profile]);
      form.reset();
    } catch {
      setError("The profile could not be created.");
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <>
      <div className="profile-grid">
        {profiles.map((profile, index) => {
          const isActive = active === profile.id;
          const isSwitching = switchingProfileId === profile.id;
          return (
            <button
              aria-busy={isSwitching}
              aria-pressed={isActive}
              className={isActive ? "profile-card active" : "profile-card"}
              disabled={switchingProfileId !== null}
              key={profile.id}
              onClick={() => switchTo(profile)}
              type="button"
            >
              <span aria-hidden="true" className={`avatar avatar-${index % 5}`}>
                {profile.name.slice(0, 1).toUpperCase()}
                {isActive && <span className="active-profile-mark"><CheckIcon /></span>}
              </span>
              <span className="profile-card-copy">
                <strong>{profile.name}</strong>
                <small>{isSwitching ? "Opening profile…" : profile.is_kids ? "Kids profile" : profile.preference.cinephile_mode ? "Cinephile Mode" : "Normal Mode"}</small>
              </span>
              {isActive && <span className="active-profile-label">Watching now</span>}
            </button>
          );
        })}
      </div>
      {profiles.length < 5 && (
        <form aria-labelledby="add-profile-title" className="add-profile" onSubmit={createProfile}>
          <header className="add-profile-header">
            <span className="add-profile-icon"><PlusIcon /></span>
            <div>
              <p>New viewer</p>
              <h2 id="add-profile-title">Create a profile</h2>
              <span>Give every viewer their own watchlist and recommendations.</span>
            </div>
            <span className="profile-limit">{profiles.length} of 5 used</span>
          </header>

          <div className="profile-form-fields">
            <label className="profile-name-field" htmlFor="new-profile">
              <span>Profile name</span>
              <span className="profile-input-shell">
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 20c.7-3.5 3.3-5.5 7-5.5s6.3 2 7 5.5" />
                </svg>
                <input autoComplete="off" id="new-profile" name="name" maxLength={50} placeholder="Enter a name" required />
              </span>
            </label>

            <label className="kids-profile-option">
              <input name="is_kids" type="checkbox" />
              <span className="kids-profile-control">
                <span className="kids-profile-icon"><KidsIcon /></span>
                <span className="kids-profile-copy">
                  <strong>Kids profile</strong>
                  <small>Age-appropriate titles and a simpler experience</small>
                </span>
                <span aria-hidden="true" className="kids-profile-switch"><i /></span>
              </span>
            </label>
          </div>

          <footer className="profile-form-actions">
            <p>
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 3 5.5 5.5v5.8c0 4.2 2.5 7.6 6.5 9.7 4-2.1 6.5-5.5 6.5-9.7V5.5L12 3Z" /><path d="m9 12 2 2 4-4" /></svg>
              Profile settings can be changed later.
            </p>
            <button aria-busy={isCreating} className="profile-submit" disabled={isCreating} type="submit">
              <span><PlusIcon /></span>
              {isCreating ? "Creating profile…" : "Add profile"}
              <svg aria-hidden="true" className="profile-submit-arrow" viewBox="0 0 24 24"><path d="M5 12h14M14 7l5 5-5 5" /></svg>
            </button>
          </footer>
        </form>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </>
  );
}

