"use client";

import { useActionState } from "react";
import isoCountries from "i18n-iso-countries";
import englishCountries from "i18n-iso-countries/langs/en.json";

import { saveLegalPolicyDraftAction, type LegalPolicyFormState } from "./actions";
import type { LegalPolicyRecord } from "./legal-policy-types";
import styles from "./legal-policy.module.css";

isoCountries.registerLocale(englishCountries);

const countryOptions = Object.entries(isoCountries.getNames("en", { select: "official" }))
  .map(([code, name]) => [code, name] as const)
  .toSorted((left, right) => left[1].localeCompare(right[1]));

function formattedSavedAt(value: string | null): string {
  if (!value) return "Last private save: Not saved yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Last private save: Unavailable";
  const month = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ][date.getUTCMonth()];
  const day = String(date.getUTCDate()).padStart(2, "0");
  const hours = String(date.getUTCHours()).padStart(2, "0");
  const minutes = String(date.getUTCMinutes()).padStart(2, "0");
  return `Last private save: ${month} ${day}, ${date.getUTCFullYear()} at ${hours}:${minutes} UTC`;
}

function Optional() {
  return <small className={styles.optional}>Optional draft field</small>;
}

export function LegalPolicyForm({ initialRecord }: { initialRecord: LegalPolicyRecord }) {
  const initialState: LegalPolicyFormState = {
    sequence: 0,
    revision: initialRecord.revision,
    updatedAt: initialRecord.updated_at,
    error: "",
    notice: "",
  };
  const [state, action, pending] = useActionState(saveLegalPolicyDraftAction, initialState);

  return (
    <div className={styles.workspace}>
      <form action={action} aria-busy={pending} className={styles.form}>
        <input name="revision" type="hidden" value={state.revision} />

        <div className={styles.formHeading}>
          <div>
            <p className="eyebrow">Owner facts</p>
            <h2>Record the details policies may need.</h2>
          </div>
          <span>{formattedSavedAt(state.updatedAt)}</span>
        </div>

        <fieldset disabled={pending}>
          <legend>Legal identity and jurisdiction</legend>
          <p className={styles.sectionIntro}>Save what you know now. Empty fields remain part of this private draft and can be completed later.</p>
          <div className={styles.fieldGrid}>
            <label className={styles.fullField} htmlFor="legal-operator-name">
              <span>Legal operator or business name <Optional /></span>
              <input
                autoComplete="organization"
                defaultValue={initialRecord.legal_operator_name ?? ""}
                id="legal-operator-name"
                maxLength={200}
                name="legal_operator_name"
                aria-describedby="legal-operator-name-help"
              />
              <small id="legal-operator-name-help">Use the registered person or business that operates the service.</small>
            </label>

            <label htmlFor="legal-country">
              <span>Country <Optional /></span>
              <select
                autoComplete="country"
                defaultValue={initialRecord.country_code ?? ""}
                id="legal-country"
                name="country_code"
                aria-describedby="legal-country-help"
              >
                <option value="">Choose when ready</option>
                {countryOptions.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
              </select>
              <small id="legal-country-help">The country where the operator is legally based.</small>
            </label>

            <label htmlFor="legal-region">
              <span>Province or state <Optional /></span>
              <input
                autoComplete="address-level1"
                defaultValue={initialRecord.region ?? ""}
                id="legal-region"
                maxLength={120}
                name="region"
                aria-describedby="legal-region-help"
              />
              <small id="legal-region-help">Enter the full regional name, if applicable.</small>
            </label>

            <label className={styles.fullField} htmlFor="legal-governing-law">
              <span>Governing-law jurisdiction <Optional /></span>
              <input
                defaultValue={initialRecord.governing_law_jurisdiction ?? ""}
                id="legal-governing-law"
                maxLength={200}
                name="governing_law_jurisdiction"
                aria-describedby="legal-governing-law-help"
                placeholder="For example, Ontario, Canada"
              />
              <small id="legal-governing-law-help">Record the jurisdiction you intend to have reviewed for the terms. This form does not choose it for you.</small>
            </label>
          </div>
        </fieldset>

        <fieldset disabled={pending}>
          <legend>Public contact points</legend>
          <p className={styles.sectionIntro}>These addresses may later appear in customer-facing notices. They stay private until a separate policy approval and publication process.</p>
          <div className={styles.fieldGrid}>
            <label htmlFor="legal-support-email">
              <span>Support email <Optional /></span>
              <input
                autoCapitalize="none"
                autoComplete="email"
                defaultValue={initialRecord.support_email ?? ""}
                id="legal-support-email"
                inputMode="email"
                maxLength={320}
                name="support_email"
                spellCheck={false}
                type="email"
                aria-describedby="legal-support-email-help"
              />
              <small id="legal-support-email-help">For general service and account questions.</small>
            </label>

            <label htmlFor="legal-privacy-email">
              <span>Privacy email <Optional /></span>
              <input
                autoCapitalize="none"
                autoComplete="email"
                defaultValue={initialRecord.privacy_email ?? ""}
                id="legal-privacy-email"
                inputMode="email"
                maxLength={320}
                name="privacy_email"
                spellCheck={false}
                type="email"
                aria-describedby="legal-privacy-email-help"
              />
              <small id="legal-privacy-email-help">For privacy questions and data requests.</small>
            </label>

            <label className={styles.fullField} htmlFor="legal-copyright-email">
              <span>Copyright and takedown email <Optional /></span>
              <input
                autoCapitalize="none"
                autoComplete="email"
                defaultValue={initialRecord.copyright_email ?? ""}
                id="legal-copyright-email"
                inputMode="email"
                maxLength={320}
                name="copyright_email"
                spellCheck={false}
                type="email"
                aria-describedby="legal-copyright-email-help"
              />
              <small id="legal-copyright-email-help">For rights-holder notices and takedown requests.</small>
            </label>
          </div>
        </fieldset>

        <fieldset disabled={pending}>
          <legend>Audience baseline</legend>
          <p className={styles.sectionIntro}>Leave this blank until you have chosen and reviewed an age rule. Aperture does not assume one.</p>
          <div className={styles.ageField}>
            <label htmlFor="legal-minimum-age">
              <span>Minimum user age <Optional /></span>
              <input
                defaultValue={initialRecord.minimum_user_age ?? ""}
                id="legal-minimum-age"
                inputMode="numeric"
                max={120}
                min={0}
                name="minimum_user_age"
                type="number"
                aria-describedby="legal-minimum-age-help"
              />
              <small id="legal-minimum-age-help">Whole number from 0 to 120, or blank. This records your choice; it does not provide legal advice.</small>
            </label>
          </div>
        </fieldset>

        <div className={styles.feedback} aria-live="polite" aria-atomic="true">
          {state.error ? <p key={`error-${state.sequence}`} className={styles.error} role="alert">{state.error}</p> : null}
          {state.notice ? <p key={`notice-${state.sequence}`} className={styles.success} role="status">{state.notice}</p> : null}
        </div>

        <footer className={styles.actions}>
          <span>Private owner draft</span>
          <button className="studio-primary" disabled={pending} type="submit">
            {pending ? "Saving private draft..." : "Save private draft"}
          </button>
        </footer>
      </form>

      <aside className={styles.boundary} aria-labelledby="legal-policy-boundary-title">
        <span aria-hidden="true" className={styles.lock}>Private</span>
        <h2 id="legal-policy-boundary-title">This does not approve or publish policies.</h2>
        <p>The form stores factual owner input only. Editing it does not generate legal text, change approval status, automatically update or invalidate separately approved policy documents, or make this draft customer-facing.</p>
        <ol>
          <li><span>01</span><p><strong>Enter facts</strong><small>Save a partial draft whenever you are ready.</small></p></li>
          <li><span>02</span><p><strong>Prepare documents separately</strong><small>Each required policy still needs substantive text.</small></p></li>
          <li><span>03</span><p><strong>Review outside this draft</strong><small>Any approval or publication decision remains separate and explicit.</small></p></li>
        </ol>
      </aside>
    </div>
  );
}
