"use client";

import Script from "next/script";
import {
  type FormEvent,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { apiGatewayPath } from "@/app/lib/api-gateway";
import {
  formatTemplatePrice,
  isPlatformAccount,
  isPlatformRegistration,
  isPlatformRental,
  isPlatformVerificationDelivery,
  parseTemplateDetail,
  rentalMatchesIntent,
  templateFeatures,
  type MarketplaceLoadState,
  type PlatformAccount,
  type PlatformRegistration,
  type PlatformRental,
  type PlatformTemplate,
  type PlatformTemplateDetail,
} from "./platform-marketplace";
import styles from "./marketplace.module.css";

type FlowStep = "agreement" | "checking-account" | "auth" | "verification" | "configure" | "complete";
type AuthMode = "login" | "register";
type CaptchaConfiguration = { captcha: { required: boolean; test_mode: boolean } };
type VerificationDelivery = PlatformRegistration["verification_delivery"] | "already_verified";

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

type ApiResponseProblem = { code: string | null; message: string };

async function responseProblem(response: Response, fallback: string): Promise<ApiResponseProblem> {
  const body: unknown = await response.json().catch(() => null);
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return { code: null, message: fallback };
  }
  if (typeof body.detail === "string" && body.detail.trim()) {
    return { code: null, message: body.detail };
  }
  if (
    typeof body.detail === "object"
    && body.detail !== null
    && "message" in body.detail
    && typeof body.detail.message === "string"
    && body.detail.message.trim()
  ) {
    return {
      code: "code" in body.detail && typeof body.detail.code === "string" ? body.detail.code : null,
      message: body.detail.message,
    };
  }
  if (Array.isArray(body.detail)) {
    const messages = body.detail.flatMap((item) => {
      if (typeof item !== "object" || item === null || !("msg" in item)) return [];
      return typeof item.msg === "string" ? [item.msg] : [];
    });
    if (messages.length) return { code: null, message: messages.join(" ") };
  }
  return { code: null, message: fallback };
}

async function responseDetail(response: Response, fallback: string): Promise<string> {
  return (await responseProblem(response, fallback)).message;
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

function formatDateTime(value: string): string {
  try {
    return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  } catch {
    return value;
  }
}

function isStrongPassword(value: string): boolean {
  return value.length >= 12
    && value.length <= 128
    && /[a-z]/u.test(value)
    && /[A-Z]/u.test(value)
    && /[0-9]/u.test(value);
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
  const [verificationToken, setVerificationToken] = useState("");
  const [verificationDelivery, setVerificationDelivery] = useState<VerificationDelivery | null>(null);
  const [verificationTokenExpiresAt, setVerificationTokenExpiresAt] = useState<string | null>(null);
  const [developmentVerificationToken, setDevelopmentVerificationToken] = useState<string | null>(null);
  const [verificationError, setVerificationError] = useState("");
  const [verificationNotice, setVerificationNotice] = useState("");
  const [verificationPending, setVerificationPending] = useState(false);
  const [fragmentVerificationError, setFragmentVerificationError] = useState("");
  const [fragmentVerificationNotice, setFragmentVerificationNotice] = useState("");
  const [fragmentClaimRequired, setFragmentClaimRequired] = useState(false);
  const [fragmentClaimPassword, setFragmentClaimPassword] = useState("");
  const [fragmentClaimPending, setFragmentClaimPending] = useState(false);
  const [fragmentClaimError, setFragmentClaimError] = useState("");
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
  const verificationRequestControllers = useRef<Set<AbortController>>(new Set());
  const fragmentVerificationCandidate = useRef<{ initialized: boolean; token: string | null }>({
    initialized: false,
    token: null,
  });
  const fragmentVerificationToken = useRef("");
  const currentFlow = useRef({ selected, detail, accepted, account, step });

  useLayoutEffect(() => {
    currentFlow.current = { selected, detail, accepted, account, step };
  }, [accepted, account, detail, selected, step]);

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

  function startVerificationRequest(): AbortController {
    const controller = new AbortController();
    verificationRequestControllers.current.add(controller);
    return controller;
  }

  function verificationRequestIsCurrent(controller: AbortController): boolean {
    return !controller.signal.aborted;
  }

  function finishVerificationRequest(controller: AbortController) {
    verificationRequestControllers.current.delete(controller);
  }

  function clearFragmentVerificationToken() {
    fragmentVerificationToken.current = "";
    fragmentVerificationCandidate.current.token = null;
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
    setVerificationToken("");
    setVerificationDelivery(null);
    setVerificationTokenExpiresAt(null);
    setDevelopmentVerificationToken(null);
    setVerificationError("");
    setVerificationNotice("");
    setVerificationPending(false);
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
    for (const controller of verificationRequestControllers.current) controller.abort();
    verificationRequestControllers.current.clear();
  }, []);

  useEffect(() => {
    if (!fragmentVerificationCandidate.current.initialized) {
      if (!window.location.hash.startsWith("#verify-email=")) return;
      let token = "";
      try {
        token = decodeURIComponent(window.location.hash.slice("#verify-email=".length)).trim();
      } catch {
        token = "";
      }
      fragmentVerificationCandidate.current = { initialized: true, token: token || null };
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
    }

    const token = fragmentVerificationCandidate.current.token;
    const controller = startVerificationRequest();
    void (async () => {
      // Yield once so React Strict Mode can retire its development-only first effect
      // before the network request starts, then reuse the already-scrubbed candidate.
      await Promise.resolve();
      if (!verificationRequestIsCurrent(controller)) return;
      if (!token) {
        setFragmentVerificationError("The email verification link is invalid. Request a new link after signing in.");
        return;
      }
      fragmentVerificationToken.current = token;
      setFragmentVerificationNotice("Confirming your email verification link…");
      const response = await fetch(apiGatewayPath("/platform/auth/email-verification/confirm"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ token }),
      });
      if (!verificationRequestIsCurrent(controller)) return;
      if (response.status === 401) {
        setFragmentClaimRequired(true);
        setFragmentVerificationNotice("Set a new password to securely claim the account associated with this verification link.");
        return;
      }
      if (!response.ok) {
        const problem = await responseProblem(response, "The email verification link could not be confirmed.");
        if (!verificationRequestIsCurrent(controller)) return;
        if (response.status === 400 && problem.code === "platform_email_verification_invalid") {
          setFragmentClaimRequired(true);
          setFragmentVerificationNotice("This link belongs to a different platform account. Set a new password to securely claim that account and sign in here.");
          return;
        }
        throw new Error(problem.message);
      }
      const value: unknown = await response.json();
      if (!verificationRequestIsCurrent(controller)) return;
      if (!isPlatformAccount(value) || !value.email_verified) {
        throw new Error("Email verification returned an invalid response.");
      }
      const activeFlow = currentFlow.current;
      if (
        activeFlow.selected
        && activeFlow.detail
        && activeFlow.accepted
        && activeFlow.step === "verification"
        && activeFlow.account?.id === value.id
      ) {
        setAccount(value);
        setStep("configure");
      }
      clearFragmentVerificationToken();
      setVerificationToken("");
      setFragmentClaimRequired(false);
      setFragmentClaimPassword("");
      setFragmentVerificationError("");
      setFragmentVerificationNotice("Your platform account email is verified.");
    })().catch((error: unknown) => {
      if (!verificationRequestIsCurrent(controller)) return;
      clearFragmentVerificationToken();
      setFragmentVerificationNotice("");
      setFragmentVerificationError(
        error instanceof Error ? error.message : "The email verification link could not be confirmed.",
      );
    }).finally(() => finishVerificationRequest(controller));
    return () => {
      controller.abort();
      finishVerificationRequest(controller);
    };
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
    if ((step !== "auth" && !fragmentClaimRequired) || captchaConfiguration || captchaError) return;
    const controller = startVerificationRequest();
    void fetch(apiGatewayPath("/platform/auth/config"), {
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error();
      const value: unknown = await response.json();
      if (!verificationRequestIsCurrent(controller)) return;
      if (!isCaptchaConfiguration(value)) throw new Error();
      setCaptchaConfiguration(value);
    }).catch(() => {
      if (verificationRequestIsCurrent(controller)) {
        setCaptchaError("Security verification is unavailable. Account access is paused safely.");
      }
    }).finally(() => {
      finishVerificationRequest(controller);
    });
    return () => {
      controller.abort();
      finishVerificationRequest(controller);
    };
  }, [captchaConfiguration, captchaError, fragmentClaimRequired, step]);

  function continueWithAccount(nextAccount: PlatformAccount, registration?: PlatformRegistration) {
    setAccount(nextAccount);
    setVerificationError("");
    setVerificationNotice("");
    if (nextAccount.email_verified) {
      setVerificationToken("");
      clearFragmentVerificationToken();
      setVerificationDelivery("already_verified");
      setVerificationTokenExpiresAt(null);
      setDevelopmentVerificationToken(null);
      setStep("configure");
      return;
    }
    const developmentToken = registration?.development_verification_token ?? null;
    setVerificationDelivery(registration?.verification_delivery ?? null);
    setVerificationTokenExpiresAt(registration?.verification_token_expires_at ?? null);
    setDevelopmentVerificationToken(developmentToken);
    setVerificationToken(developmentToken ?? "");
    setStep("verification");
  }

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
      continueWithAccount(value);
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
      if (authMode === "register") {
        if (!isPlatformRegistration(value)) {
          setAuthError("Platform account access returned an invalid response.");
          return;
        }
        continueWithAccount(value, value);
        return;
      }
      if (!isPlatformAccount(value)) {
        setAuthError("Platform account access returned an invalid response.");
        return;
      }
      continueWithAccount(value);
    } catch {
      if (requestIsCurrent(generation, controller)) {
        setAuthError("The platform account service is unavailable. Try again shortly.");
      }
    } finally {
      if (requestIsCurrent(generation, controller)) setAuthPending(false);
      finishRequest(controller);
    }
  }

  async function submitVerification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = verificationToken.trim();
    if (!token || !account) return;
    const generation = flowGeneration.current;
    const controller = startRequest(generation);
    setVerificationPending(true);
    setVerificationError("");
    setVerificationNotice("");
    try {
      const response = await fetch(apiGatewayPath("/platform/auth/email-verification/confirm"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ token }),
      });
      if (!requestIsCurrent(generation, controller)) return;
      if (!response.ok) {
        const detailMessage = await responseDetail(response, "Email verification could not be completed.");
        if (!requestIsCurrent(generation, controller)) return;
        setVerificationError(detailMessage);
        return;
      }
      const value: unknown = await response.json();
      if (!requestIsCurrent(generation, controller)) return;
      if (!isPlatformAccount(value) || !value.email_verified) {
        setVerificationError("Email verification returned an invalid response.");
        return;
      }
      setAccount(value);
      setVerificationToken("");
      clearFragmentVerificationToken();
      setVerificationDelivery("already_verified");
      setVerificationTokenExpiresAt(null);
      setDevelopmentVerificationToken(null);
      setVerificationNotice("");
      setStep("configure");
    } catch {
      if (requestIsCurrent(generation, controller)) {
        setVerificationError("The email verification service is unavailable. Try again shortly.");
      }
    } finally {
      if (requestIsCurrent(generation, controller)) setVerificationPending(false);
      finishRequest(controller);
    }
  }

  async function resendVerification() {
    if (!account) return;
    const generation = flowGeneration.current;
    const controller = startRequest(generation);
    setVerificationPending(true);
    setVerificationError("");
    setVerificationNotice("");
    try {
      const response = await fetch(apiGatewayPath("/platform/auth/email-verification/resend"), {
        method: "POST",
        credentials: "include",
        signal: controller.signal,
      });
      if (!requestIsCurrent(generation, controller)) return;
      if (!response.ok) {
        const detailMessage = await responseDetail(response, "A new verification email could not be requested.");
        if (!requestIsCurrent(generation, controller)) return;
        setVerificationError(detailMessage);
        return;
      }
      const value: unknown = await response.json();
      if (!requestIsCurrent(generation, controller)) return;
      if (!isPlatformVerificationDelivery(value)) {
        setVerificationError("The verification service returned an invalid response.");
        return;
      }
      setVerificationDelivery(value.status);
      setVerificationTokenExpiresAt(value.verification_token_expires_at);
      setDevelopmentVerificationToken(value.development_verification_token);
      setVerificationToken(value.development_verification_token ?? "");
      if (value.status === "already_verified") {
        const accountResponse = await fetch(apiGatewayPath("/platform/auth/me"), {
          credentials: "include",
          cache: "no-store",
          signal: controller.signal,
        });
        if (!requestIsCurrent(generation, controller)) return;
        if (!accountResponse.ok) {
          const detailMessage = await responseDetail(accountResponse, "Verified account status could not be refreshed.");
          if (!requestIsCurrent(generation, controller)) return;
          setVerificationError(detailMessage);
          return;
        }
        const accountValue: unknown = await accountResponse.json();
        if (!requestIsCurrent(generation, controller)) return;
        if (!isPlatformAccount(accountValue) || !accountValue.email_verified) {
          setVerificationError("Verified account status returned an invalid response.");
          return;
        }
        continueWithAccount(accountValue);
        return;
      }
      setVerificationNotice(
        value.status === "sent"
          ? "A new verification email has been sent."
          : value.status === "development" && value.development_verification_token
            ? "A new development verification token is ready below."
            : "Email delivery is currently unavailable. You can try requesting another message.",
      );
    } catch {
      if (requestIsCurrent(generation, controller)) {
        setVerificationError("The email verification service is unavailable. Try again shortly.");
      }
    } finally {
      if (requestIsCurrent(generation, controller)) setVerificationPending(false);
      finishRequest(controller);
    }
  }

  async function submitFragmentClaim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = fragmentVerificationToken.current;
    if (!token || !captchaConfiguration || !isStrongPassword(fragmentClaimPassword)) return;
    const data = new FormData(event.currentTarget);
    const captchaToken = captchaConfiguration.captcha.test_mode
      ? "local-captcha-pass"
      : data.get("cf-turnstile-response");
    if (captchaConfiguration.captcha.required && (typeof captchaToken !== "string" || !captchaToken)) {
      setFragmentClaimError("Complete the security check before claiming this account.");
      return;
    }
    const controller = startVerificationRequest();
    setFragmentClaimPending(true);
    setFragmentClaimError("");
    try {
      const response = await fetch(apiGatewayPath("/platform/auth/email-verification/claim"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          token,
          password: fragmentClaimPassword,
          captcha_token: typeof captchaToken === "string" ? captchaToken : null,
        }),
      });
      if (!verificationRequestIsCurrent(controller)) return;
      if (!response.ok) {
        const detailMessage = await responseDetail(response, "The verification link could not claim this account.");
        if (!verificationRequestIsCurrent(controller)) return;
        setFragmentClaimError(detailMessage);
        return;
      }
      const value: unknown = await response.json();
      if (!verificationRequestIsCurrent(controller)) return;
      if (!isPlatformAccount(value) || !value.email_verified) {
        setFragmentClaimError("Account claim returned an invalid response.");
        return;
      }
      setAccount(value);
      clearFragmentVerificationToken();
      setFragmentClaimRequired(false);
      setFragmentClaimPassword("");
      setFragmentClaimError("");
      setFragmentVerificationError("");
      setFragmentVerificationNotice("Your platform account email is verified and this browser is signed in.");
      if (selected && detail && accepted) setStep("configure");
    } catch {
      if (verificationRequestIsCurrent(controller)) {
        setFragmentClaimError("The account claim service is unavailable. Try again shortly.");
      }
    } finally {
      if (verificationRequestIsCurrent(controller)) setFragmentClaimPending(false);
      finishVerificationRequest(controller);
    }
  }

  async function submitRental(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail?.current_version || !detail.rental_agreement || !accepted) return;
    if (!account?.email_verified) {
      setVerificationError("Verify the platform account email before reserving a template.");
      setStep("verification");
      return;
    }
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
      if (value.status === "expired" || !value.reservation_active) {
        setRental(null);
        submittedRequest.current = null;
        setIdempotencyKey(freshIdempotencyKey());
        setRentalError(
          `That rental reservation expired at ${formatDateTime(value.expired_at ?? value.reservation_expires_at)}. Submit again to start a new reservation request.`,
        );
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

  const fragmentVerificationFeedback = <>
    {fragmentVerificationNotice ? <p className={styles.securityStatus} role="status">{fragmentVerificationNotice}</p> : null}
    {fragmentVerificationError ? <p className={styles.inlineError} role="alert">{fragmentVerificationError}</p> : null}
    {fragmentClaimRequired ? <section className={styles.authStep} aria-labelledby="platform-claim-title">
      <p className={styles.stepLabel}>Secure account claim</p>
      <h2 id="platform-claim-title">Set a password to finish verification.</h2>
      <p>This verification link was opened without an authenticated platform session. Choose a new password to prove mailbox access, verify the account, and sign in this browser.</p>
      <form className={styles.authForm} onSubmit={submitFragmentClaim}>
        <label htmlFor="platform-claim-password">New platform account password</label>
        <input
          id="platform-claim-password"
          type="password"
          value={fragmentClaimPassword}
          onChange={(event) => setFragmentClaimPassword(event.target.value)}
          minLength={12}
          maxLength={128}
          autoComplete="new-password"
          aria-describedby="platform-claim-password-help"
          aria-invalid={Boolean(fragmentClaimError)}
          required
        />
        <small id="platform-claim-password-help">Use at least 12 characters with uppercase, lowercase, and a number.</small>
        {!captchaConfiguration && !captchaError ? <p className={styles.securityStatus} role="status">Checking security requirements…</p> : null}
        {captchaConfiguration?.captcha.required && captchaConfiguration.captcha.test_mode ? <div className={styles.localCaptcha}><span aria-hidden="true">✓</span><div><strong>Local security check</strong><small>Test mode — production uses Turnstile</small></div></div> : null}
        {captchaConfiguration?.captcha.required && !captchaConfiguration.captcha.test_mode ? <>
          <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" strategy="afterInteractive" />
          {process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY
            ? <div className="cf-turnstile" data-sitekey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY} data-theme="dark" />
            : <p className={styles.inlineError} role="alert">Security verification is not configured. Account claim is paused.</p>}
        </> : null}
        {captchaError ? <p className={styles.inlineError} role="alert">{captchaError}</p> : null}
        {fragmentClaimError ? <p className={styles.inlineError} role="alert">{fragmentClaimError}</p> : null}
        <button
          className={styles.authSubmit}
          type="submit"
          disabled={
            fragmentClaimPending
            || !captchaConfiguration
            || Boolean(captchaError)
            || !isStrongPassword(fragmentClaimPassword)
            || Boolean(captchaConfiguration?.captcha.required && !captchaConfiguration.captcha.test_mode && !process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY)
          }
        >
          {fragmentClaimPending ? "Claiming account…" : "Verify email, set password, and sign in"}
        </button>
      </form>
    </section> : null}
  </>;

  if (initialState.status === "unavailable") {
    return <>{fragmentVerificationFeedback}<div className={styles.catalogUnavailable} role="alert"><span aria-hidden="true">!</span><div><h3>Marketplace temporarily unavailable</h3><p>{initialState.reason}</p></div></div></>;
  }
  if (!initialState.templates.length) {
    return <>{fragmentVerificationFeedback}<div className={styles.catalogEmpty}><span aria-hidden="true">◎</span><h3>No templates are published yet.</h3><p>Nothing has been represented as rentable while the registry is empty.</p></div></>;
  }

  return (
    <>
      {fragmentVerificationFeedback}
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

          {detail && account && !account.email_verified && step === "verification" ? <section className={styles.authStep} aria-labelledby="platform-verification-title">
            <p className={styles.stepLabel}>Email verification required</p>
            <h3 id="platform-verification-title">Verify your renter account.</h3>
            <p>Signed in as <strong>{account.email}</strong>. Confirm this email before a rental request can be reserved.</p>
            {account.unverified_account_expires_at ? <p className={styles.securityStatus}>
              This unverified account remains claimable until <time dateTime={account.unverified_account_expires_at}>{formatDateTime(account.unverified_account_expires_at)}</time>.
            </p> : null}
            {verificationDelivery === "sent" ? <p className={styles.securityStatus} role="status">Check your email for the verification link or token.</p> : null}
            {verificationDelivery === "unavailable" ? <p className={styles.securityStatus} role="status">Email delivery is unavailable right now. You can request another message or enter a token you already received.</p> : null}
            {verificationTokenExpiresAt ? <p className={styles.securityStatus}>
              The current verification link and token expire at <time dateTime={verificationTokenExpiresAt}>{formatDateTime(verificationTokenExpiresAt)}</time>.
            </p> : null}
            {verificationDelivery === "development" && developmentVerificationToken ? <div className={styles.localCaptcha} role="status">
              <span aria-hidden="true">i</span><div><strong>Development verification token</strong><small><code>{developmentVerificationToken}</code></small></div>
            </div> : null}
            <form className={styles.authForm} onSubmit={submitVerification}>
              <label htmlFor="platform-verification-token">Verification token</label>
              <input
                id="platform-verification-token"
                type="text"
                value={verificationToken}
                onChange={(event) => setVerificationToken(event.target.value)}
                minLength={32}
                maxLength={256}
                autoComplete="one-time-code"
                spellCheck={false}
                aria-invalid={Boolean(verificationError)}
                data-marketplace-autofocus
                required
              />
              <small>Paste the token from your verification email. A development token appears above only when the server explicitly provides one.</small>
              {verificationNotice ? <p className={styles.securityStatus} role="status">{verificationNotice}</p> : null}
              {verificationError ? <p className={styles.inlineError} role="alert">{verificationError}</p> : null}
              <button className={styles.authSubmit} type="submit" disabled={verificationPending || verificationToken.trim().length < 32}>
                {verificationPending ? "Checking verification…" : "Confirm email and continue"}
              </button>
            </form>
            <button className={styles.backButton} type="button" disabled={verificationPending} onClick={() => void resendVerification()}>Request a new verification email</button>
            <button className={styles.backButton} type="button" disabled={verificationPending} onClick={() => { setAccount(null); setAuthMode("login"); setAuthError(""); setStep("auth"); }}>Use a different platform account</button>
          </section> : null}

          {detail && account?.email_verified && step === "configure" ? <section className={styles.configureStep} aria-labelledby="configure-title">
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
              <div><dt>Reservation expires</dt><dd><time dateTime={rental.reservation_expires_at}>{formatDateTime(rental.reservation_expires_at)}</time></dd></div>
            </dl>
            <div className={styles.checkoutUnavailable}><strong>Checkout unavailable</strong><p>Platform billing must be reviewed and enabled before this request can move forward.</p></div>
            <footer className={styles.modalActions}><button type="button" data-marketplace-autofocus onClick={closeDialog}>Done</button></footer>
          </section> : null}
        </div>
      </div> : null}
    </>
  );
}
