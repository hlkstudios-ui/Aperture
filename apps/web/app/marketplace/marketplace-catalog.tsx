"use client";

import Script from "next/script";
import {
  type FormEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import { apiGatewayPath } from "@/app/lib/api-gateway";
import {
  formatTemplatePrice,
  isPlatformAccount,
  isPlatformRental,
  parseTemplateDetail,
  rentalMatchesIntent,
  templateFeatures,
  type MarketplaceLoadState,
  type PlatformAccount,
  type PlatformRental,
  type PlatformTemplate,
  type PlatformTemplateDetail,
} from "./platform-marketplace";
import styles from "./marketplace.module.css";

type FlowStep = "agreement" | "checking-account" | "auth" | "configure" | "complete";
type AuthMode = "login" | "register";
type CaptchaConfiguration = { captcha: { required: boolean; test_mode: boolean } };

const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function isCaptchaConfiguration(value: unknown): value is CaptchaConfiguration {
  if (typeof value !== "object" || value === null || !("captcha" in value)) return false;
  const captcha = value.captcha;
  return typeof captcha === "object"
    && captcha !== null
    && "required" in captcha
    && typeof captcha.required === "boolean"
    && "test_mode" in captcha
    && typeof captcha.test_mode === "boolean";
}

async function responseDetail(response: Response, fallback: string): Promise<string> {
  const body: unknown = await response.json().catch(() => null);
  if (typeof body !== "object" || body === null || !("detail" in body)) return fallback;
  if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  if (Array.isArray(body.detail)) {
    const messages = body.detail.flatMap((item) => {
      if (typeof item !== "object" || item === null || !("msg" in item)) return [];
      return typeof item.msg === "string" ? [item.msg] : [];
    });
    if (messages.length) return messages.join(" ");
  }
  return fallback;
}

function artworkFor(template: PlatformTemplate): { url: string; alt: string } | null {
  if (template.thumbnail_url) return { url: template.thumbnail_url, alt: `${template.name} preview` };
  const image = template.preview_assets.find((asset) => asset.kind === "image");
  return image ? { url: image.url, alt: image.alt } : null;
}

function TemplateArtwork({ template }: { template: PlatformTemplate }) {
  const artwork = artworkFor(template);
  return (
    <div className={styles.artwork}>
      {artwork
        // The platform API admits only application-relative or HTTPS preview assets.
        // eslint-disable-next-line @next/next/no-img-element
        ? <img src={artwork.url} alt={artwork.alt} loading="lazy" />
        : <div className={styles.artworkFallback} aria-label={`${template.name} preview artwork is not available`}>
          <span aria-hidden="true"><i /><i /><i /><i /><i /><i /></span>
          <strong>APERTURES</strong><small>Preview artwork pending</small>
        </div>}
      <span className={styles.category}>{template.category}</span>
      <span className={template.status === "published" ? styles.releasePublished : styles.releasePreview}>
        {template.status === "published" ? "Published" : "Preview"}
      </span>
    </div>
  );
}

function TemplateCard({ template, onRent }: { template: PlatformTemplate; onRent: (template: PlatformTemplate) => void }) {
  const features = templateFeatures(template);
  const price = formatTemplatePrice(template.starting_price);
  const reasonId = `rental-reason-${template.id}`;
  const unavailableReason = template.unavailable_reason?.trim() || "This release is not available to rent.";
  return (
    <article className={styles.card}>
      <TemplateArtwork template={template} />
      <div className={styles.cardBody}>
        <header>
          <div><p>{template.current_version ? `Release ${template.current_version.version}` : "Release pending"}</p><h3>{template.name}</h3></div>
          <span className={styles.price}>{price ? <><strong>{price.split(" / ")[0]}</strong><small>/ {price.split(" / ")[1]}</small></> : "Pricing not published"}</span>
        </header>
        <p className={styles.summary}>{template.description}</p>
        {features.length
          ? <ul className={styles.features} aria-label={`${template.name} features`}>{features.map((feature) => <li key={feature}>{feature}</li>)}</ul>
          : <p className={styles.featurePending}>Feature manifest not published</p>}
        {!template.rental_available ? <p className={styles.unavailable} id={reasonId}><span aria-hidden="true">!</span>{unavailableReason}</p> : null}
        <footer>
          {template.demo_url
            ? <a className={styles.previewButton} href={template.demo_url}>View preview <span aria-hidden="true">↗</span></a>
            : <button className={styles.previewButton} type="button" disabled>Preview unavailable</button>}
          <button
            className={styles.rentButton}
            type="button"
            disabled={!template.rental_available}
            aria-describedby={!template.rental_available ? reasonId : undefined}
            onClick={() => onRent(template)}
          >
            Rent {template.name}<span aria-hidden="true">→</span>
          </button>
        </footer>
      </div>
    </article>
  );
}

function freshIdempotencyKey(): string {
  return globalThis.crypto.randomUUID();
}

export function MarketplaceCatalog({ initialState }: { initialState: MarketplaceLoadState }) {
  const [selected, setSelected] = useState<PlatformTemplate | null>(null);
  const [detail, setDetail] = useState<PlatformTemplateDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailPending, setDetailPending] = useState(false);
  const [step, setStep] = useState<FlowStep>("agreement");
  const [accepted, setAccepted] = useState(false);
  const [account, setAccount] = useState<PlatformAccount | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [captchaConfiguration, setCaptchaConfiguration] = useState<CaptchaConfiguration | null>(null);
  const [captchaError, setCaptchaError] = useState("");
  const [authError, setAuthError] = useState("");
  const [authPending, setAuthPending] = useState(false);
  const [businessName, setBusinessName] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [rental, setRental] = useState<PlatformRental | null>(null);
  const [rentalError, setRentalError] = useState("");
  const [rentalPending, setRentalPending] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const submittedRequest = useRef<{ fingerprint: string; key: string } | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const flowGeneration = useRef(0);
  const requestControllers = useRef<Set<AbortController>>(new Set());

  function abortOutstandingRequests() {
    for (const controller of requestControllers.current) controller.abort();
    requestControllers.current.clear();
  }

  function startRequest(generation: number): AbortController {
    const controller = new AbortController();
    if (generation !== flowGeneration.current) controller.abort();
    else requestControllers.current.add(controller);
    return controller;
  }

  function requestIsCurrent(generation: number, controller: AbortController): boolean {
    return generation === flowGeneration.current && !controller.signal.aborted;
  }

  function finishRequest(controller: AbortController) {
    requestControllers.current.delete(controller);
  }

  function closeDialog() {
    flowGeneration.current += 1;
    abortOutstandingRequests();
    setSelected(null);
  }

  function openRental(template: PlatformTemplate) {
    flowGeneration.current += 1;
    abortOutstandingRequests();
    setDetail(null);
    setDetailError("");
    setDetailPending(true);
    setStep("agreement");
    setAccepted(false);
    setAccount(null);
    setAuthMode("login");
    setCaptchaConfiguration(null);
    setAuthError("");
    setCaptchaError("");
    setAuthPending(false);
    setBusinessName("");
    setTenantSlug("");
    setRental(null);
    setRentalError("");
    setRentalPending(false);
    setIdempotencyKey(freshIdempotencyKey());
    submittedRequest.current = null;
    setSelected(template);
  }

  useEffect(() => () => {
    flowGeneration.current += 1;
    for (const controller of requestControllers.current) controller.abort();
    requestControllers.current.clear();
  }, []);

  useEffect(() => {
    if (!selected) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = dialogRef.current;
    dialog?.querySelector<HTMLElement>(focusableSelector)?.focus();
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        flowGeneration.current += 1;
        for (const controller of requestControllers.current) controller.abort();
        requestControllers.current.clear();
        setSelected(null);
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const items = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector));
      if (!items.length) return;
      const first = items[0];
      const last = items.at(-1)!;
      if (!dialog.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [selected]);

  useEffect(() => {
    if (!selected) return;
    const preferred = dialogRef.current?.querySelector<HTMLElement>("[data-marketplace-autofocus]");
    const first = dialogRef.current?.querySelector<HTMLElement>(focusableSelector);
    (preferred ?? first)?.focus();
  }, [detail, selected, step]);

  useEffect(() => {
    if (!selected) return;
    const generation = flowGeneration.current;
    const controller = startRequest(generation);
    void fetch(apiGatewayPath(`/platform/templates/${encodeURIComponent(selected.slug)}`), {
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(await responseDetail(response, "The release details could not be loaded."));
      const parsed = parseTemplateDetail(await response.json());
      if (!requestIsCurrent(generation, controller)) return;
      if (!parsed) throw new Error("The release details were invalid, so this rental has been paused safely.");
      if (!parsed.rental_available || !parsed.current_version || !parsed.starting_price || !parsed.rental_agreement) {
        throw new Error(parsed.unavailable_reason?.trim() || "This release is not ready to rent.");
      }
      setDetail(parsed);
    }).catch((error: unknown) => {
      if (!requestIsCurrent(generation, controller)) return;
      setDetailError(error instanceof Error ? error.message : "The release details could not be loaded.");
    }).finally(() => {
      if (requestIsCurrent(generation, controller)) setDetailPending(false);
      finishRequest(controller);
    });
    return () => {
      controller.abort();
      finishRequest(controller);
    };
  }, [selected]);

  useEffect(() => {
    if (step !== "auth" || captchaConfiguration || captchaError) return;
    const generation = flowGeneration.current;
    const controller = startRequest(generation);
    void fetch(apiGatewayPath("/platform/auth/config"), {
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error();
      const value: unknown = await response.json();
      if (!requestIsCurrent(generation, controller)) return;
      if (!isCaptchaConfiguration(value)) throw new Error();
      setCaptchaConfiguration(value);
    }).catch(() => {
      if (requestIsCurrent(generation, controller)) {
        setCaptchaError("Security verification is unavailable. Account access is paused safely.");
      }
    }).finally(() => {
      finishRequest(controller);
    });
    return () => {
      controller.abort();
      finishRequest(controller);
    };
  }, [captchaConfiguration, captchaError, step]);

  async function continueAfterAgreement() {
    if (!accepted || !detail) return;
    const generation = flowGeneration.current;
    const controller = startRequest(generation);
    setStep("checking-account");
    setAuthError("");
    try {
      const response = await fetch(apiGatewayPath("/platform/auth/me"), {
        credentials: "include",
        cache: "no-store",
        signal: controller.signal,
      });
      if (!requestIsCurrent(generation, controller)) return;
      if (response.status === 401) {
        setStep("auth");
        return;
      }
      if (!response.ok) {
        const detailMessage = await responseDetail(response, "Platform sign-in could not be checked. Try again.");
        if (!requestIsCurrent(generation, controller)) return;
        setAuthError(detailMessage);
        setStep("agreement");
        return;
      }
      const value: unknown = await response.json();
      if (!requestIsCurrent(generation, controller)) return;
      if (!isPlatformAccount(value)) {
        setAuthError("Platform sign-in returned an invalid response. Try again.");
        setStep("agreement");
        return;
      }
      setAccount(value);
      setStep("configure");
    } catch {
      if (requestIsCurrent(generation, controller)) {
        setAuthError("Platform sign-in could not be reached. Try again.");
        setStep("agreement");
      }
    } finally {
      finishRequest(controller);
    }
  }

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!captchaConfiguration) return;
    const generation = flowGeneration.current;
    const controller = startRequest(generation);
    setAuthPending(true);
    setAuthError("");
    const data = new FormData(event.currentTarget);
    const captchaToken = captchaConfiguration.captcha.test_mode
      ? "local-captcha-pass"
      : data.get("cf-turnstile-response");
    if (captchaConfiguration.captcha.required && (typeof captchaToken !== "string" || !captchaToken)) {
      setAuthError("Complete the security check before continuing.");
      setAuthPending(false);
      finishRequest(controller);
      return;
    }
    try {
      const response = await fetch(apiGatewayPath(`/platform/auth/${authMode}`), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          email: data.get("email"),
          password: data.get("password"),
          captcha_token: typeof captchaToken === "string" ? captchaToken : null,
        }),
      });
      if (!requestIsCurrent(generation, controller)) return;
      if (!response.ok) {
        const detailMessage = await responseDetail(response, "Platform account access could not be completed.");
        if (!requestIsCurrent(generation, controller)) return;
        setAuthError(detailMessage);
        return;
      }
      const value: unknown = await response.json();
      if (!requestIsCurrent(generation, controller)) return;
      if (!isPlatformAccount(value)) {
        setAuthError("Platform account access returned an invalid response.");
        return;
      }
      setAccount(value);
      setStep("configure");
    } catch {
      if (requestIsCurrent(generation, controller)) {
        setAuthError("The platform account service is unavailable. Try again shortly.");
      }
    } finally {
      if (requestIsCurrent(generation, controller)) setAuthPending(false);
      finishRequest(controller);
    }
  }

  async function submitRental(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail?.current_version || !detail.rental_agreement || !accepted) return;
    const generation = flowGeneration.current;
    const controller = startRequest(generation);
    const payload = {
      template_slug: detail.slug,
      template_version_id: detail.current_version.id,
      agreement_version_id: detail.rental_agreement.id,
      agreement_version: detail.rental_agreement.version,
      agreement_sha256: detail.rental_agreement.content_sha256,
      business_name: businessName,
      requested_tenant_slug: tenantSlug,
      accepted: true as const,
    };
    const fingerprint = JSON.stringify(payload);
    let requestKey = idempotencyKey;
    if (!requestKey || (submittedRequest.current && submittedRequest.current.fingerprint !== fingerprint)) {
      requestKey = freshIdempotencyKey();
      setIdempotencyKey(requestKey);
    }
    submittedRequest.current = { fingerprint, key: requestKey };
    setRentalPending(true);
    setRentalError("");
    try {
      const response = await fetch(apiGatewayPath("/platform/rental-intents"), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": requestKey,
        },
        signal: controller.signal,
        body: JSON.stringify(payload),
      });
      if (!requestIsCurrent(generation, controller)) return;
      if (!response.ok) {
        const detailMessage = await responseDetail(response, "The rental request could not be reserved.");
        if (!requestIsCurrent(generation, controller)) return;
        setRentalError(detailMessage);
        return;
      }
      const value: unknown = await response.json();
      if (!requestIsCurrent(generation, controller)) return;
      if (
        !isPlatformRental(value)
        || !rentalMatchesIntent(value, detail, businessName, tenantSlug)
      ) {
        setRentalError("The rental service returned an invalid or mismatched response, so no launch state is being claimed.");
        return;
      }
      setRental(value);
      setStep("complete");
    } catch {
      if (requestIsCurrent(generation, controller)) {
        setRentalError("The rental service is unavailable. Retry this same request safely.");
      }
    } finally {
      if (requestIsCurrent(generation, controller)) setRentalPending(false);
      finishRequest(controller);
    }
  }

  function downloadTerms() {
    if (!detail?.rental_agreement) return;
    const agreement = detail.rental_agreement;
    const documentText = [
      agreement.title,
      `Version: ${agreement.version}`,
      `SHA-256: ${agreement.content_sha256}`,
      "",
      agreement.content,
    ].join("\n");
    const url = URL.createObjectURL(new Blob([documentText], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${detail.slug}-rental-terms-${agreement.version.replace(/[^a-z0-9._-]+/gi, "-")}.txt`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  if (initialState.status === "unavailable") {
    return <div className={styles.catalogUnavailable} role="alert"><span aria-hidden="true">!</span><div><h3>Marketplace temporarily unavailable</h3><p>{initialState.reason}</p></div></div>;
  }
  if (!initialState.templates.length) {
    return <div className={styles.catalogEmpty}><span aria-hidden="true">◎</span><h3>No templates are published yet.</h3><p>Nothing has been represented as rentable while the registry is empty.</p></div>;
  }

  return (
    <>
      <div className={styles.grid}>{initialState.templates.map((template) => <TemplateCard key={template.id} template={template} onRent={openRental} />)}</div>
      {selected ? <div className={styles.modalLayer}>
        <button className={styles.scrim} type="button" tabIndex={-1} aria-label="Close rental dialog" onClick={closeDialog} />
        <div
          ref={dialogRef}
          className={styles.modal}
          role="dialog"
          aria-modal="true"
          aria-labelledby="rental-dialog-title"
          aria-describedby="rental-dialog-description"
        >
          <header className={styles.modalHeader}>
            <div><p>{step === "complete" ? "Reservation recorded" : "Rent this template"}</p><h2 id="rental-dialog-title">{selected.name}</h2></div>
            <button type="button" onClick={closeDialog} aria-label="Close rental dialog">×</button>
          </header>
          <p className={styles.modalDescription} id="rental-dialog-description">
            This process reserves a request only. It cannot charge, provision, activate, or create a domain.
          </p>

          {detailPending ? <div className={styles.modalLoading} role="status"><span /><p>Loading the pinned release and agreement…</p></div> : null}
          {detailError ? <div className={styles.modalError} role="alert"><strong>Rental unavailable</strong><p>{detailError}</p><button type="button" onClick={closeDialog}>Close</button></div> : null}

          {detail && step === "agreement" ? <section className={styles.agreementStep} aria-labelledby="agreement-title">
            <div className={styles.releaseLedger}>
              <span><small>Template release</small><strong>{detail.current_version?.version}</strong></span>
              <span><small>Agreement</small><strong>{detail.rental_agreement?.version}</strong></span>
              <span><small>Starting price</small><strong>{formatTemplatePrice(detail.starting_price)}</strong></span>
            </div>
            <header className={styles.agreementHeader}>
              <div><p>Read the complete document</p><h3 id="agreement-title">{detail.rental_agreement?.title}</h3></div>
              <button type="button" data-marketplace-autofocus onClick={downloadTerms}>Download terms</button>
            </header>
            <div className={styles.terms} tabIndex={0} aria-label="Rental agreement text">{detail.rental_agreement?.content}</div>
            <p className={styles.hash}>Document SHA-256 <code>{detail.rental_agreement?.content_sha256}</code></p>
            <label className={styles.consent}>
              <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
              <span><strong>I have read and accept this exact rental agreement.</strong><small>The accepted version and SHA-256 hash will be recorded with the reservation.</small></span>
            </label>
            {authError ? <p className={styles.inlineError} role="alert">{authError}</p> : null}
            <footer className={styles.modalActions}>
              <button type="button" onClick={closeDialog}>Cancel</button>
              <button type="button" disabled={!accepted} onClick={() => void continueAfterAgreement()}>Continue securely <span aria-hidden="true">→</span></button>
            </footer>
          </section> : null}

          {detail && step === "checking-account" ? <div className={styles.modalLoading} role="status"><span /><p>Checking your Apertures platform account…</p></div> : null}

          {detail && step === "auth" ? <section className={styles.authStep} aria-labelledby="platform-auth-title">
            <p className={styles.stepLabel}>Apertures platform account</p>
            <h3 id="platform-auth-title">{authMode === "login" ? "Continue your rental request." : "Create your renter account."}</h3>
            <p>This identity is separate from every tenant storefront viewer and Studio administrator.</p>
            <div className={styles.authTabs} role="group" aria-label="Platform account action">
              <button type="button" aria-pressed={authMode === "login"} onClick={() => { setAuthMode("login"); setAuthError(""); }}>Sign in</button>
              <button type="button" aria-pressed={authMode === "register"} onClick={() => { setAuthMode("register"); setAuthError(""); }}>Create account</button>
            </div>
            <form className={styles.authForm} onSubmit={submitAuth}>
              <label htmlFor="platform-email">Email address</label>
              <input id="platform-email" name="email" type="email" autoComplete="email" data-marketplace-autofocus required />
              <label htmlFor="platform-password">Password</label>
              <input id="platform-password" name="password" type="password" minLength={authMode === "register" ? 12 : 1} autoComplete={authMode === "register" ? "new-password" : "current-password"} required />
              {authMode === "register" ? <small>Use at least 12 characters with uppercase, lowercase, and a number.</small> : null}
              {!captchaConfiguration && !captchaError ? <p className={styles.securityStatus} role="status">Checking security requirements…</p> : null}
              {captchaConfiguration?.captcha.required && captchaConfiguration.captcha.test_mode ? <div className={styles.localCaptcha}><span aria-hidden="true">✓</span><div><strong>Local security check</strong><small>Test mode — production uses Turnstile</small></div></div> : null}
              {captchaConfiguration?.captcha.required && !captchaConfiguration.captcha.test_mode ? <>
                <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" strategy="afterInteractive" />
                {process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY
                  ? <div className="cf-turnstile" data-sitekey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY} data-theme="dark" />
                  : <p className={styles.inlineError} role="alert">Security verification is not configured. Account access is paused.</p>}
              </> : null}
              {captchaError ? <p className={styles.inlineError} role="alert">{captchaError}</p> : null}
              {authError ? <p className={styles.inlineError} role="alert">{authError}</p> : null}
              <button className={styles.authSubmit} type="submit" disabled={authPending || !captchaConfiguration || Boolean(captchaError) || Boolean(captchaConfiguration?.captcha.required && !captchaConfiguration.captcha.test_mode && !process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY)}>
                {authPending ? "Please wait…" : authMode === "login" ? "Sign in and continue" : "Create account and continue"}
              </button>
            </form>
            <button className={styles.backButton} type="button" onClick={() => setStep("agreement")}>← Return to agreement</button>
          </section> : null}

          {detail && account && step === "configure" ? <section className={styles.configureStep} aria-labelledby="configure-title">
            <p className={styles.stepLabel}>Tenant reservation</p>
            <h3 id="configure-title">Name your front door.</h3>
            <p>Signed in as <strong>{account.email}</strong>. The hosted address is reserved only; no application or domain is created in this step.</p>
            <form onSubmit={submitRental}>
              <label htmlFor="platform-business-name">Business name</label>
              <input id="platform-business-name" value={businessName} onChange={(event) => setBusinessName(event.target.value)} minLength={2} maxLength={120} autoComplete="organization" data-marketplace-autofocus required />
              <label htmlFor="platform-tenant-slug">Desired Apertures-hosted address</label>
              <div className={styles.slugField}><input id="platform-tenant-slug" value={tenantSlug} onChange={(event) => setTenantSlug(event.target.value.toLowerCase())} minLength={2} maxLength={63} pattern="[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?" autoComplete="off" spellCheck={false} required /><span>.apertures.online</span></div>
              <small>Use lowercase letters, numbers, and internal hyphens. A custom domain remains optional later.</small>
              <div className={styles.reservationTruth}>
                <span aria-hidden="true">i</span><p><strong>Billing is not connected.</strong> Submitting records an awaiting-payment rental and reserves the slug. It does not charge you or start provisioning.</p>
              </div>
              {rentalError ? <p className={styles.inlineError} role="alert">{rentalError}</p> : null}
              <footer className={styles.modalActions}>
                <button type="button" onClick={() => setStep("agreement")}>Back</button>
                <button type="submit" disabled={rentalPending}>{rentalPending ? "Reserving request…" : "Reserve rental request"}</button>
              </footer>
            </form>
          </section> : null}

          {detail && rental && step === "complete" ? <section className={styles.completeStep} aria-labelledby="reservation-title">
            <span className={styles.completeMark} aria-hidden="true">✓</span>
            <p className={styles.stepLabel}>Awaiting payment</p>
            <h3 id="reservation-title">Your rental request is reserved.</h3>
            <p>No charge was attempted. Checkout is unavailable, provisioning has not started, and no custom domain has been created.</p>
            <dl>
              <div><dt>Business</dt><dd>{rental.tenant.business_name}</dd></div>
              <div><dt>Reserved address</dt><dd>{rental.tenant.hosted_hostname}</dd></div>
              <div><dt>Template release</dt><dd>{rental.template.name} · {rental.template.version}</dd></div>
              <div><dt>Status</dt><dd>Awaiting payment</dd></div>
            </dl>
            <div className={styles.checkoutUnavailable}><strong>Checkout unavailable</strong><p>Platform billing must be reviewed and enabled before this request can move forward.</p></div>
            <footer className={styles.modalActions}><button type="button" data-marketplace-autofocus onClick={closeDialog}>Done</button></footer>
          </section> : null}
        </div>
      </div> : null}
    </>
  );
}
