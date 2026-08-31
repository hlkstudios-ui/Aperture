import type { ReactNode } from "react";
import Link from "next/link";

import { SiteHeader } from "@/app/components/site-header";
import { customerAccountFetch, type AccountDashboard } from "@/app/lib/account";
import { requireCustomerSession, type ViewerProfile } from "@/app/lib/customer-session";
import { getSiteBrand } from "@/app/lib/site-brand-server";

import { AccountSubmitButton } from "./account-submit-button";
import {
  openBillingPortal,
  revokeOtherSessions,
  revokeSession,
  setLanguagePreferences,
  setPrivacyPreferences,
  setRewatchIntelligence,
  startCheckout,
} from "./actions";
import { PasswordForm } from "./password-form";

export const metadata = { title: "The Projection Ledger" };

const languages = [
  ["en", "English"],
  ["fr", "Français"],
  ["es", "Español"],
  ["ar", "العربية"],
  ["ja", "日本語"],
];
const timezones = ["UTC", "America/Toronto", "America/New_York", "America/Los_Angeles", "Europe/London", "Europe/Paris", "Asia/Tokyo"];

function deviceName(agent: string | null) {
  if (!agent) return "Unknown device";
  if (/mobile|android|iphone/i.test(agent)) return "Mobile browser";
  if (/tv/i.test(agent)) return "TV device";
  return "Desktop browser";
}

function DeviceIcon({ agent }: { agent: string | null }) {
  if (/mobile|android|iphone/i.test(agent ?? "")) {
    return <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="7" y="2.5" width="10" height="19" rx="2.3" /><path d="M10.5 5h3M11 18.5h2" /></svg>;
  }
  if (/tv/i.test(agent ?? "")) {
    return <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="2.5" y="5" width="19" height="13" rx="2.2" /><path d="m8.5 2 3.5 3 3.5-3M9 21h6" /></svg>;
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="2.5" y="3.5" width="19" height="13" rx="2.2" /><path d="M8 20.5h8M12 16.5v4" /></svg>;
}

function SectionHeading({
  id,
  number,
  eyebrow,
  title,
  description,
  action,
}: {
  id: string;
  number: string;
  eyebrow: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="account-section-heading">
      <span aria-hidden="true" className="account-section-number">{number}</span>
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2 id={id}>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="account-section-action">{action}</div>}
    </header>
  );
}

function ProfileFormHeading({ profile, index, label }: { profile: ViewerProfile; index: number; label: string }) {
  return (
    <header className="preference-profile-heading">
      <span aria-hidden="true" className={`mini-avatar avatar-tone-${index % 5}`}>{profile.name.slice(0, 1).toUpperCase()}</span>
      <div><small>{label} {String(index + 1).padStart(2, "0")}</small><h3>{profile.name}</h3></div>
    </header>
  );
}

export default async function AccountPage() {
  const [viewer, dashboard, brand] = await Promise.all([
    requireCustomerSession(),
    customerAccountFetch<AccountDashboard>("/account"),
    getSiteBrand(),
  ]);
  const activeProfile = viewer.profiles.find((profile) => profile.id === viewer.active_profile_id) ?? viewer.profiles[0];
  const locale = activeProfile?.language ?? "en";
  const timezone = activeProfile?.preference.timezone ?? "UTC";
  const subscriptionName = dashboard.subscription?.plan.name ?? "Preview access";

  return (
    <main className="account-page">
      <SiteHeader />

      <header className="account-hero">
        <div className="account-hero-copy">
          <p className="eyebrow">Account &amp; access</p>
          <h1>The projection ledger.</h1>
          <p>Everything that follows you from screen to screen—profiles, playback, privacy, and access—tuned in one quiet place.</p>
          <div className="account-identity-row">
            <span>
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 6.5h16v11H4zM4 7l8 6 8-6" /></svg>
              {dashboard.email}
            </span>
          </div>
        </div>

        <aside className="account-pass" aria-label={`${brand.business_name} viewer pass`}>
          <header><strong>{brand.short_name.toUpperCase()}</strong><span>VIEWER PASS / {new Date().getFullYear()}</span></header>
          <div className="account-pass-owner">
            <span aria-hidden="true" className="account-iris"><i>{activeProfile?.name.slice(0, 1).toUpperCase() ?? "A"}</i></span>
            <div><small>Now projecting for</small><strong>{activeProfile?.name ?? "Viewer"}</strong><span>{dashboard.email}</span></div>
          </div>
          <dl>
            <div><dt>Film lives</dt><dd>{viewer.profiles.length.toString().padStart(2, "0")}</dd></div>
            <div><dt>Open sessions</dt><dd>{dashboard.sessions.length.toString().padStart(2, "0")}</dd></div>
            <div><dt>Access</dt><dd>{subscriptionName}</dd></div>
          </dl>
          <div aria-hidden="true" className="account-pass-strip" />
        </aside>
      </header>

      <nav aria-label="Account control index" className="account-index">
        <span>Control index</span>
        <a href="#membership"><i>01</i> Membership</a>
        <a href="#profiles"><i>02</i> Film lives</a>
        <a href="#playback"><i>03</i> Projection</a>
        <a href="#privacy"><i>04</i> House policy</a>
        <a href="#security"><i>05</i> Booth log</a>
        <a href="#plans"><i>06</i> Formats</a>
      </nav>

      <div className="account-dashboard">
        <div className="account-opening-grid">
          <section aria-labelledby="membership-title" className="account-panel account-subscription" id="membership">
            <SectionHeading id="membership-title" number="01" eyebrow="Screening access" title="Admission pass" />
            <div className="account-membership-state">
              <div className={`membership-status-disc ${dashboard.subscription ? "is-active" : ""}`} aria-hidden="true"><span>{dashboard.subscription ? "LIVE" : "STANDBY"}</span></div>
              <div className="membership-copy">
                <small>{dashboard.subscription ? "Currently screening with" : "Current status"}</small>
                <h3>{dashboard.subscription ? dashboard.subscription.plan.name : "No active subscription"}</h3>
                {dashboard.subscription ? (
                  <>
                    <span className={`catalog-badge ${dashboard.subscription.status}`}>{dashboard.subscription.status}</span>
                    <p>{dashboard.subscription.plan.description}</p>
                    <dl>
                      <div><dt>Picture</dt><dd>{dashboard.subscription.plan.max_resolution}</dd></div>
                      <div><dt>Screens</dt><dd>{dashboard.subscription.plan.max_streams}</dd></div>
                    </dl>
                    {dashboard.billing.production_ready && <form action={openBillingPortal}><AccountSubmitButton className="account-secondary-button" pendingLabel="Opening billing…">Manage billing</AccountSubmitButton></form>}
                  </>
                ) : (
                  <p>{dashboard.billing.checkout_available ? "Choose a plan to continue securely with the billing provider." : "Memberships will appear here when a production billing provider is connected. No payment has been recorded."}</p>
                )}
              </div>
            </div>
            {dashboard.billing.notice && <div className="billing-notice"><span aria-hidden="true">!</span><div><strong>Billing is waiting in the wings</strong><p>{dashboard.billing.notice}</p></div></div>}
          </section>

          <section aria-labelledby="profiles-ledger-title" className="account-panel account-profiles" id="profiles">
            <SectionHeading
              id="profiles-ledger-title"
              number="02"
              eyebrow="Distinct film lives"
              title="Profile contact sheet"
              action={<Link className="account-manage-link" href="/profiles">Manage profiles <span aria-hidden="true">↗</span></Link>}
            />
            <ul className="account-profile-list">
              {viewer.profiles.map((profile, index) => {
                const enabled = profile.preference.rewatch_intelligence_enabled;
                return (
                  <li key={profile.id}>
                    <span aria-hidden="true" className={`mini-avatar avatar-tone-${index % 5}`}>{profile.name.slice(0, 1).toUpperCase()}</span>
                    <div className="account-profile-copy">
                      <strong>{profile.name}</strong>
                      <small>{profile.is_kids ? "Kids profile" : `${profile.maturity_level} · ${profile.language}`}</small>
                      <span>Rewatch memory {enabled ? "active" : "paused"}</span>
                    </div>
                    <form action={setRewatchIntelligence.bind(null, profile.id, profile.preference, !enabled)}>
                      <AccountSubmitButton
                        aria-label={`Turn rewatch intelligence ${enabled ? "off" : "on"} for ${profile.name}`}
                        aria-pressed={enabled}
                        className={`account-memory-toggle ${enabled ? "is-on" : ""}`}
                        pendingLabel="Updating…"
                      ><i aria-hidden="true" /> Turn {enabled ? "off" : "on"}</AccountSubmitButton>
                    </form>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>

        <section aria-labelledby="playback-title" className="account-panel account-wide account-preferences" id="playback">
          <SectionHeading id="playback-title" number="03" eyebrow="Playback craft" title="Projection setup" description="Audio, captions, and local time stay private to each profile and take effect when playback begins." />
          <div className="language-preference-grid">
            {viewer.profiles.map((profile, index) => (
              <form aria-label={`${profile.name} playback preferences`} key={profile.id} className="language-preference language-settings" action={setLanguagePreferences.bind(null, profile.id, profile.preference)}>
                <ProfileFormHeading profile={profile} index={index} label="Playback card" />
                <label>Interface language<select name="language" defaultValue={profile.language}>{languages.map(([code, name]) => <option value={code} key={code}>{name}</option>)}</select></label>
                <label>Preferred audio<select name="preferred_audio_language" defaultValue={profile.preference.preferred_audio_language ?? profile.language}>{languages.map(([code, name]) => <option value={code} key={code}>{name}</option>)}</select></label>
                <label>Preferred subtitles<select name="preferred_subtitle_language" defaultValue={profile.preference.preferred_subtitle_language ?? profile.language}>{languages.map(([code, name]) => <option value={code} key={code}>{name}</option>)}</select></label>
                <label>Second subtitle<select name="preferred_secondary_subtitle_language" defaultValue={profile.preference.preferred_secondary_subtitle_language ?? ""}><option value="">Off</option>{languages.map(([code, name]) => <option value={code} key={code}>{name}</option>)}</select></label>
                <label>Caption size<select name="caption_size" defaultValue={profile.preference.caption_size}><option value="small">Small</option><option value="medium">Medium</option><option value="large">Large</option></select></label>
                <label>Caption background<select name="caption_background" defaultValue={profile.preference.caption_background}><option value="transparent">Transparent</option><option value="shadow">Text shadow</option><option value="solid">Solid</option></select></label>
                <label>Caption position<select name="caption_position" defaultValue={profile.preference.caption_position}><option value="bottom">Bottom</option><option value="top">Top</option></select></label>
                <label>Timezone<select name="timezone" defaultValue={profile.preference.timezone}>{timezones.map((zone) => <option value={zone} key={zone}>{zone.replaceAll("_", " ")}</option>)}</select></label>
                <label className="check-line"><input aria-label="Enable subtitles by default" type="checkbox" name="subtitles_enabled" defaultChecked={profile.preference.subtitles_enabled} /><span><strong>Subtitles from the first frame</strong><small>Enable subtitles automatically when a title starts.</small></span></label>
                <AccountSubmitButton className="account-save-button">Save language preferences <span aria-hidden="true">→</span></AccountSubmitButton>
              </form>
            ))}
          </div>
        </section>

        <section aria-labelledby="privacy-title" className="account-panel account-wide account-privacy" id="privacy">
          <SectionHeading id="privacy-title" number="04" eyebrow="Privacy, without fine print" title="House policy" description="Playback progress is kept only so you can resume. Optional analytics remain a separate choice you control for every profile." />
          <div className="language-preference-grid privacy-preference-grid">
            {viewer.profiles.map((profile, index) => (
              <form aria-label={`${profile.name} privacy preferences`} key={profile.id} className="language-preference privacy-preference" action={setPrivacyPreferences.bind(null, profile.id)}>
                <ProfileFormHeading profile={profile} index={index} label="Privacy card" />
                <label className="check-line"><input aria-label="Share optional usage and playback-quality analytics" type="checkbox" name="analytics_enabled" defaultChecked={profile.preference.analytics_enabled} /><span><strong>Optional product analytics</strong><small>Share usage and playback-quality signals to improve {brand.short_name}.</small></span></label>
                <label>Homepage personalization<select name="homepage_mode" defaultValue={profile.preference.homepage_mode}><option value="no_algorithm">No Algorithm</option><option value="curated">Curated profile experience</option></select></label>
                <p className="privacy-explainer">Turning analytics off stops new collection and removes retained raw events for this profile. Anonymous aggregates cannot identify you.</p>
                {profile.preference.consent_updated_at ? <small className="preference-timestamp">Last changed <time dateTime={profile.preference.consent_updated_at}>{new Intl.DateTimeFormat(locale, { dateStyle:"medium", timeStyle:"short", timeZone:timezone }).format(new Date(profile.preference.consent_updated_at))}</time></small> : <small className="preference-timestamp">No analytics consent has been recorded.</small>}
                <AccountSubmitButton className="account-save-button">Save privacy choices <span aria-hidden="true">→</span></AccountSubmitButton>
              </form>
            ))}
          </div>
        </section>

        <div className="account-security-grid">
          <section aria-labelledby="security-title" className="account-panel account-sessions" id="security">
            <SectionHeading
              id="security-title"
              number="05"
              eyebrow="The guest list"
              title="Booth log"
              description="Every open door to your account, in one view."
              action={dashboard.sessions.length > 1 && <form action={revokeOtherSessions}><AccountSubmitButton className="account-secondary-button" pendingLabel="Signing out…">Sign out other sessions</AccountSubmitButton></form>}
            />
            <ul className="session-list">
              {dashboard.sessions.map((session) => (
                <li key={session.id}>
                  <span className="session-device-icon"><DeviceIcon agent={session.user_agent} /></span>
                  <div>
                    <strong>{deviceName(session.user_agent)} {session.current && <span className="catalog-badge active">Current</span>}</strong>
                    <small>{session.user_agent ?? "User agent unavailable"}</small>
                    <small>Last active <time dateTime={session.last_seen_at}>{new Intl.DateTimeFormat(locale, { dateStyle:"medium", timeStyle:"short", timeZone:timezone }).format(new Date(session.last_seen_at))}</time> · IP {session.ip_address ?? "unavailable"}</small>
                  </div>
                  {!session.current && <form action={revokeSession.bind(null, session.id)}><AccountSubmitButton aria-label={`Sign out ${deviceName(session.user_agent)}`} className="session-signout" pendingLabel="Signing out…">Sign out</AccountSubmitButton></form>}
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="password-title" className="account-panel account-password">
            <SectionHeading id="password-title" number="05B" eyebrow="Private key" title="Change the key" description="A fresh password signs every other device out of your account." />
            <PasswordForm />
          </section>
        </div>

        <section aria-labelledby="plans-title" className="account-panel account-wide account-plans" id="plans">
          <SectionHeading id="plans-title" number="06" eyebrow="The programme" title="Admission formats" description={`Plans are provider-authoritative. ${brand.short_name} never pretends a payment succeeded.`} />
          <div className="plan-list">
            {dashboard.plans.map((plan, index) => {
              const reasonId = `plan-${plan.id}-availability`;
              const disabledReason = dashboard.subscription ? "Manage your existing membership from the admission pass above." : "Checkout opens when a production billing provider is connected.";
              return (
                <article key={plan.id}>
                  <header><span>{String(index + 1).padStart(2, "0")}</span><strong>{plan.name}</strong><small>{new Intl.NumberFormat(locale, { style:"currency", currency:plan.currency }).format(plan.price_cents / 100)} / {plan.interval}</small></header>
                  <p>{plan.description}</p>
                  <dl><div><dt>Picture</dt><dd>{plan.max_resolution}</dd></div><div><dt>Screens</dt><dd>{plan.max_streams}</dd></div></dl>
                  {dashboard.billing.checkout_available && !dashboard.subscription ? (
                    <form action={startCheckout.bind(null, plan.code)}><AccountSubmitButton pendingLabel="Opening checkout…">Choose {plan.name} <span aria-hidden="true">→</span></AccountSubmitButton></form>
                  ) : (
                    <><button aria-describedby={reasonId} disabled>{dashboard.subscription ? "Current account subscribed" : "Checkout unavailable"}</button><small className="plan-availability-note" id={reasonId}>{disabledReason}</small></>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      </div>
    </main>
  );
}
