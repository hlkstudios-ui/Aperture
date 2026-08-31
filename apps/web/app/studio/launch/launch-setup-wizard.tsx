"use client";

import Image from "next/image";
import { useMemo, useState, useTransition, type CSSProperties } from "react";
import isoCountries from "i18n-iso-countries";
import englishCountries from "i18n-iso-countries/langs/en.json";

import {
  assistBrandCopyAction,
  mutateLaunchSetupAction,
  type LaunchSetupFormState,
} from "./actions";
import { GeneratedLogo } from "@/app/components/generated-logo";
import { createGeneratedLogoRecipe, generatedLogoGlyphFrom, type GeneratedLogoGlyph } from "@/app/lib/generated-logo";
import { LogoAtelier } from "./logo-atelier";
import {
  type BrandCopySuggestion,
  type BrandCopyTone,
  launchSteps,
  type EditableSiteBrand,
  type EditableSiteBrandPalette,
  type LaunchSetupRecord,
  type LaunchStep,
} from "./launch-setup-types";
import styles from "./launch-setup.module.css";

isoCountries.registerLocale(englishCountries);

const colorPattern = /^#[0-9a-f]{6}$/i;

const copyToneOptions: ReadonlyArray<{ value: BrandCopyTone; label: string }> = [
  { value: "cinematic", label: "Cinematic" },
  { value: "warm", label: "Warm & inviting" },
  { value: "bold", label: "Bold" },
  { value: "refined", label: "Refined" },
  { value: "playful", label: "Playful" },
  { value: "mysterious", label: "Mysterious" },
];

const palettes: ReadonlyArray<{ name: string; note: string; values: EditableSiteBrandPalette }> = [
  {
    name: "Premiere",
    note: "Warm projection red",
    values: {
      accent: "#e7684d",
      accent_hover: "#ff8268",
      surface: "#0b0b0a",
      surface_elevated: "#181614",
      text: "#f3ece3",
      text_muted: "#b6ada5",
    },
  },
  {
    name: "Nocturne",
    note: "Midnight blue and silver",
    values: {
      accent: "#73a7d8",
      accent_hover: "#91bce4",
      surface: "#080b11",
      surface_elevated: "#121925",
      text: "#f1f4f8",
      text_muted: "#aeb8c5",
    },
  },
  {
    name: "Velvet",
    note: "Plum, rose and smoke",
    values: {
      accent: "#cf789d",
      accent_hover: "#e294b4",
      surface: "#0d090d",
      surface_elevated: "#1c131b",
      text: "#f7edf2",
      text_muted: "#c0aeb8",
    },
  },
  {
    name: "Archive",
    note: "Celluloid gold and ink",
    values: {
      accent: "#d1a85f",
      accent_hover: "#e2bd78",
      surface: "#0c0b08",
      surface_elevated: "#1a1710",
      text: "#f4efe2",
      text_muted: "#bdb4a2",
    },
  },
] as const;

const localeOptions = [
  ["en-CA", "English · Canada"],
  ["en-US", "English · United States"],
  ["en-GB", "English · United Kingdom"],
  ["fr-CA", "Français · Canada"],
  ["fr-FR", "Français · France"],
  ["es-ES", "Español · España"],
  ["de-DE", "Deutsch · Deutschland"],
  ["hi-IN", "हिन्दी · भारत"],
] as const;

const marketOptions = Object.entries(isoCountries.getNames("en", { select: "official" }))
  .map(([code, name]) => [code, name] as const)
  .toSorted((left, right) => left[1].localeCompare(right[1]));

const fallbackCurrencies = ["AUD", "CAD", "EUR", "GBP", "INR", "JPY", "USD"];
const supportedCurrencies = typeof Intl.supportedValuesOf === "function"
  ? Intl.supportedValuesOf("currency")
  : fallbackCurrencies;
const currencyDisplay = new Intl.DisplayNames(["en"], { type: "currency" });
const currencyOptions = supportedCurrencies
  .map((code) => [code, `${code} · ${currencyDisplay.of(code) ?? code}`] as const)
  .toSorted((left, right) => left[1].localeCompare(right[1]));

function editable(record: LaunchSetupRecord): EditableSiteBrand {
  return {
    business_name: record.config.business_name,
    short_name: record.config.short_name,
    tagline: record.config.tagline ?? "",
    description: record.config.description ?? "",
    logo_mark: record.config.logo_mark ?? (record.config.logo_url
      ? null
      : createGeneratedLogoRecipe(
        generatedLogoGlyphFrom(record.config.short_name || record.config.business_name).toUpperCase() as GeneratedLogoGlyph,
        "iris",
      )),
    palette: {
      accent: record.config.palette.accent,
      accent_hover: record.config.palette.accent_hover,
      surface: record.config.palette.surface,
      surface_elevated: record.config.palette.surface_elevated,
      text: record.config.palette.text,
      text_muted: record.config.palette.text_muted,
    },
    locale: record.config.locale,
  };
}

function hexToRgb(value: string) {
  if (!colorPattern.test(value)) return null;
  return [1, 3, 5].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16));
}

function luminance(value: string) {
  const rgb = hexToRgb(value);
  if (!rgb) return null;
  const channels = rgb.map((channel) => {
    const normalized = channel / 255;
    return normalized <= 0.03928
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

function contrast(foreground: string, background: string) {
  const first = luminance(foreground);
  const second = luminance(background);
  if (first === null || second === null) return 0;
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

export function onAccentColor(palette: EditableSiteBrandPalette): "#000000" | "#ffffff" | null {
  const candidates = ["#000000", "#ffffff"] as const;
  const usable = candidates.filter((candidate) =>
    contrast(candidate, palette.accent) >= 4.5
    && contrast(candidate, palette.accent_hover) >= 4.5,
  );
  return usable.toSorted((left, right) =>
    Math.min(contrast(right, palette.accent), contrast(right, palette.accent_hover))
    - Math.min(contrast(left, palette.accent), contrast(left, palette.accent_hover)),
  )[0] ?? null;
}

function initials(value: string) {
  const words = value.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "A";
  return words.slice(0, 2).map((word) => word[0]).join("").toLocaleUpperCase();
}

function formatSavedAt(value: string | null) {
  if (!value) return "Not saved yet";
  return `Saved ${new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value))}`;
}

function stageError(step: LaunchStep, brand: EditableSiteBrand) {
  if (step === 1) {
    if (brand.business_name.trim().length < 2) return "Enter a business name with at least two characters.";
    if (brand.business_name.trim().length > 60) return "Keep the business name to 60 characters or fewer.";
    if (brand.tagline.trim().length > 120) return "Keep the tagline to 120 characters or fewer.";
    if (brand.description.trim().length > 280) return "Keep the description to 280 characters or fewer.";
  }
  if (step === 2 && (brand.short_name.trim().length < 2 || brand.short_name.trim().length > 24)) {
    return "Enter a compact name between 2 and 24 characters.";
  }
  if (step === 3) {
    if (Object.values(brand.palette).some((value) => !colorPattern.test(value))) {
      return "Every color must use the six-digit format #RRGGBB.";
    }
    if (contrast(brand.palette.text, brand.palette.surface) < 4.5) {
      return "Primary text needs at least 4.5:1 contrast against the main surface.";
    }
    if (contrast(brand.palette.text_muted, brand.palette.surface) < 4.5) {
      return "Supporting text needs at least 4.5:1 contrast against the main surface.";
    }
    if (contrast(brand.palette.accent, brand.palette.surface) < 4.5) {
      return "The accent needs at least 4.5:1 contrast against the main surface.";
    }
    if (contrast(brand.palette.accent_hover, brand.palette.surface) < 4.5) {
      return "The hover accent needs at least 4.5:1 contrast against the main surface.";
    }
    if (!onAccentColor(brand.palette)) {
      return "Accent and hover accent need the same readable black or white button text.";
    }
    if (contrast(brand.palette.text, brand.palette.surface_elevated) < 4.5
      || contrast(brand.palette.text_muted, brand.palette.surface_elevated) < 4.5
      || contrast(brand.palette.accent, brand.palette.surface_elevated) < 4.5
      || contrast(brand.palette.accent_hover, brand.palette.surface_elevated) < 4.5) {
      return "Text and accents must stay readable against the elevated card surface.";
    }
  }
  if (step === 4 && (!brand.locale.default_locale || !brand.locale.home_market || !brand.locale.currency)) {
    return "Choose a language, home market, and billing currency.";
  }
  return "";
}

function StepIcon({ number }: { number: LaunchStep }) {
  const paths: Record<LaunchStep, React.ReactNode> = {
    1: <><circle cx="12" cy="8" r="3" /><path d="M5 20c.8-4 3.1-6 7-6s6.2 2 7 6" /></>,
    2: <><path d="M5 19 19 5M8 5h11v11" /><path d="M5 9v10h10" /></>,
    3: <><circle cx="12" cy="12" r="8" /><path d="M12 4a8 8 0 0 1 0 16c2-3 2-13 0-16Z" /></>,
    4: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" /></>,
    5: <><path d="m5 12 4 4L19 6" /><circle cx="12" cy="12" r="9" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{paths[number]}</svg>;
}

function SparklesIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2.8c.5 4.3 2.9 6.7 7.2 7.2-4.3.5-6.7 2.9-7.2 7.2-.5-4.3-2.9-6.7-7.2-7.2 4.3-.5 6.7-2.9 7.2-7.2Z" />
      <path d="M19 16.5c.2 1.6 1.1 2.5 2.7 2.7-1.6.2-2.5 1.1-2.7 2.7-.2-1.6-1.1-2.5-2.7-2.7 1.6-.2 2.5-1.1 2.7-2.7ZM5 2.5c.2 1.2.8 1.8 2 2-1.2.2-1.8.8-2 2-.2-1.2-.8-1.8-2-2 1.2-.2 1.8-.8 2-2Z" />
    </svg>
  );
}

function PaletteField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className={styles.colorField}>
      <span>{label}</span>
      <span className={styles.colorControl}>
        <input
          aria-label={`${label} color picker`}
          type="color"
          value={colorPattern.test(value) ? value : "#000000"}
          onChange={(event) => onChange(event.target.value)}
        />
        <input
          aria-label={`${label} hex value`}
          value={value}
          maxLength={7}
          spellCheck={false}
          onChange={(event) => onChange(event.target.value)}
        />
      </span>
    </label>
  );
}

function BrandPreview({ brand, logoSrc }: { brand: EditableSiteBrand; logoSrc: string | null }) {
  const name = brand.business_name.trim() || "Your cinema";
  const shortName = brand.short_name.trim() || name;
  const tagline = brand.tagline.trim() || "Stories, chosen with a point of view.";
  const onAccent = onAccentColor(brand.palette) ?? "#000000";
  const previewStyle = {
    "--launch-accent": brand.palette.accent,
    "--launch-accent-hover": brand.palette.accent_hover,
    "--launch-on-accent": onAccent,
    "--launch-surface": brand.palette.surface,
    "--launch-elevated": brand.palette.surface_elevated,
    "--launch-text": brand.palette.text,
    "--launch-muted": brand.palette.text_muted,
  } as React.CSSProperties;

  return (
    <section className={styles.previewPanel} aria-label="Live brand preview">
      <div className={styles.previewLabel}>
        <span><i /> Live brand preview</span>
        <small>Customer view</small>
      </div>
      <div className={styles.browserFrame} style={previewStyle}>
        <div className={styles.browserBar} aria-hidden="true">
          <span /><span /><span />
          <small>{shortName.toLocaleLowerCase().replace(/[^a-z0-9]+/g, "") || "yourcinema"}.watch</small>
        </div>
        <div className={styles.previewSite}>
          <header>
            <div className={styles.previewBrand}>
              {logoSrc
                ? <span className={styles.previewLogo}><Image alt="" src={logoSrc} width={92} height={36} unoptimized /></span>
                : brand.logo_mark
                  ? <span className={styles.previewGeneratedLogo}><GeneratedLogo recipe={brand.logo_mark} decorative size={28} instanceKey="launch-browser-preview" /></span>
                : <span aria-hidden="true">{initials(shortName)}</span>}
              <strong>{shortName}</strong>
            </div>
            <nav aria-label="Preview navigation"><span>Browse</span><span>Movies</span><span>Series</span></nav>
          </header>
          <div className={styles.previewHero}>
            <div>
              <small>AN ORIGINAL SELECTION</small>
              <h3>Tonight belongs to {name}.</h3>
              <p>{tagline}</p>
              <span className={styles.previewButton}>Enter the collection</span>
            </div>
          </div>
          <div className={styles.previewRail} aria-hidden="true">
            <strong>Now showing</strong>
            <div><span /><span /><span /></div>
          </div>
        </div>
      </div>
      <dl className={styles.previewFacts}>
        <div><dt>Wordmark</dt><dd>{shortName}</dd></div>
        <div><dt>Compact mark</dt><dd>{brand.logo_mark ? `${brand.logo_mark.glyph} · ${brand.logo_mark.variant}` : initials(shortName)}</dd></div>
        <div><dt>Locale</dt><dd>{brand.locale.default_locale}</dd></div>
      </dl>
    </section>
  );
}

export function LaunchSetupWizard({ initialSetup }: { initialSetup: LaunchSetupRecord }) {
  const initialActionState: LaunchSetupFormState = {
    sequence: 0,
    error: "",
    notice: "",
    setup: null,
  };
  const [result, setResult] = useState(initialActionState);
  const [pending, startSaveTransition] = useTransition();
  const [record, setRecord] = useState(initialSetup);
  const [brand, setBrand] = useState<EditableSiteBrand>(() => editable(initialSetup));
  const [activeStep, setActiveStep] = useState<LaunchStep>(initialSetup.current_step);
  const [clientError, setClientError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [assistantAudience, setAssistantAudience] = useState("");
  const [assistantTone, setAssistantTone] = useState<BrandCopyTone>("cinematic");
  const [assistantDirection, setAssistantDirection] = useState("");
  const [assistantSuggestions, setAssistantSuggestions] = useState<BrandCopySuggestion[]>([]);
  const [assistantError, setAssistantError] = useState("");
  const [assistantNotice, setAssistantNotice] = useState("");
  const [assistantPending, startAssistantTransition] = useTransition();

  const completed = useMemo(() => new Set(record.completed_steps), [record.completed_steps]);
  const progress = Math.round((completed.size / launchSteps.length) * 100);
  const selectedPalette = palettes.find((preset) =>
    Object.entries(preset.values).every(([key, value]) => brand.palette[key as keyof EditableSiteBrandPalette] === value),
  )?.name;
  const savedLogoSrc = record.config.logo_url
    ? `/studio/launch/logo?revision=${record.config.logo_revision}`
    : null;
  const logoSrc = brand.logo_mark ? null : savedLogoSrc;

  function update<Key extends keyof EditableSiteBrand>(key: Key, value: EditableSiteBrand[Key]) {
    setBrand((current) => ({ ...current, [key]: value }));
    setConfirmed(false);
    setClientError("");
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const intent = activeStep === 5 ? "publish" : "save";
    const error = stageError(activeStep, brand);
    if (error) {
      setClientError(error);
      return;
    }
    if (intent === "publish" && !confirmed) {
      setClientError("Confirm that the preview is ready to become the public identity.");
      return;
    }
    const form = new FormData(event.currentTarget);
    const nextActiveStep = Math.min(5, activeStep + 1) as LaunchStep;
    startSaveTransition(async () => {
      const next = await mutateLaunchSetupAction(result, form);
      setResult(next);
      if (!next.setup) return;
      setRecord(next.setup);
      setBrand(editable(next.setup));
      setConfirmed(false);
      setActiveStep(nextActiveStep);
      setClientError("");
    });
  }

  function goBack() {
    setActiveStep((step) => Math.max(1, step - 1) as LaunchStep);
    setClientError("");
  }

  function openStep(step: LaunchStep) {
    setActiveStep(step);
    setClientError("");
  }

  function requestCopySuggestions() {
    const businessName = brand.business_name.trim();
    if (businessName.length < 2 || businessName.length > 60) {
      setAssistantError("Enter a business name between 2 and 60 characters before asking for ideas.");
      setAssistantNotice("");
      return;
    }
    if (assistantAudience.trim().length > 160 || assistantDirection.trim().length > 240) {
      setAssistantError("Keep the audience to 160 characters and the extra direction to 240 characters.");
      setAssistantNotice("");
      return;
    }
    setAssistantError("");
    setAssistantNotice("Opening the writing room…");
    startAssistantTransition(async () => {
      const next = await assistBrandCopyAction({
        business_name: businessName,
        short_name: brand.short_name.trim() || null,
        existing_tagline: brand.tagline.trim() || null,
        existing_description: brand.description.trim() || null,
        audience: assistantAudience.trim() || null,
        tone: assistantTone,
        additional_direction: assistantDirection.trim() || null,
      });
      if (next.error) {
        setAssistantError(next.error);
        setAssistantNotice("");
        return;
      }
      setAssistantSuggestions(next.suggestions);
      setAssistantError("");
      setAssistantNotice("Three editable directions are ready. Your draft has not changed.");
    });
  }

  function editCopySuggestion(
    index: number,
    key: "short_name" | "tagline" | "description",
    value: string,
  ) {
    setAssistantSuggestions((current) => current.map((suggestion, suggestionIndex) =>
      suggestionIndex === index ? { ...suggestion, [key]: value } : suggestion,
    ));
    setAssistantError("");
    setAssistantNotice("");
  }

  function applyCopySuggestion(index: number) {
    const suggestion = assistantSuggestions[index];
    if (!suggestion) return;
    const shortName = suggestion.short_name.trim();
    if (shortName.length < 2 || shortName.length > 24) {
      setAssistantError("Keep the compact name between 2 and 24 characters before applying this direction.");
      setAssistantNotice("");
      return;
    }
    setBrand((current) => ({
      ...current,
      short_name: shortName,
      tagline: suggestion.tagline.trim(),
      description: suggestion.description.trim(),
    }));
    setConfirmed(false);
    setAssistantError("");
    setClientError("");
    setAssistantNotice(`Direction ${String(index + 1).padStart(2, "0")} is in your unsaved draft. Review it, then choose Save & continue.`);
  }

  const payload = JSON.stringify(brand);

  return (
    <section className={styles.experience} aria-labelledby="launch-file-title">
      <div className={styles.ambient} aria-hidden="true"><span /><span /><span /></div>
      <header className={styles.fileHeader}>
        <div>
          <p className={styles.overline}>Private launch file · Revision {String(record.revision).padStart(2, "0")}</p>
          <h2 id="launch-file-title">Turn the template into <em>your</em> screen.</h2>
          <p>Nothing here is shown publicly until you approve the final frame.</p>
        </div>
        <div className={styles.saveState}>
          <span className={record.status === "published" ? styles.live : styles.draft}>
            <i /> {record.status === "published" ? "Brand live" : "Private draft"}
          </span>
          <small>{formatSavedAt(record.updated_at)}</small>
        </div>
      </header>

      <div className={styles.progressTrack} aria-label={`${progress}% of launch setup complete`}>
        <span style={{ width: `${progress}%` }} />
      </div>

      <div className={styles.workspace}>
        <nav className={styles.stageNav} aria-label="Launch setup stages">
          <p>{progress}% ready</p>
          <ol>
            {launchSteps.map((step) => {
              const isComplete = completed.has(step.number);
              const available = isComplete || step.number <= record.current_step || step.number === activeStep;
              return (
                <li key={step.number} data-active={activeStep === step.number} data-complete={isComplete}>
                  <button
                    type="button"
                    disabled={!available || pending || assistantPending}
                    aria-current={activeStep === step.number ? "step" : undefined}
                    onClick={() => openStep(step.number)}
                  >
                    <span className={styles.stageIcon}>{isComplete ? "✓" : <StepIcon number={step.number} />}</span>
                    <span><strong>{step.label}</strong><small>{step.note}</small></span>
                    <b>{String(step.number).padStart(2, "0")}</b>
                  </button>
                </li>
              );
            })}
          </ol>
          <div className={styles.privacyNote}>
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
            <p><strong>Owner-only workspace</strong><span>Saved drafts stay private. AI is contacted only when you invoke the writing room.</span></p>
          </div>
        </nav>

        <form className={styles.formPanel} onSubmit={submit}>
          <input type="hidden" name="revision" value={record.revision} />
          <input type="hidden" name="step" value={activeStep} />
          <input type="hidden" name="current_step" value={record.current_step} />
          <input type="hidden" name="completed_steps" value={JSON.stringify(record.completed_steps)} />
          <input type="hidden" name="payload" value={payload} />
          <input type="hidden" name="intent" value={activeStep === 5 ? "publish" : "save"} />

          <div className={styles.stepCounter}>Stage {String(activeStep).padStart(2, "0")} <span>/ 05</span></div>

          {activeStep === 1 && (
            <fieldset>
              <legend>Give the screen a name.</legend>
              <p className={styles.stepIntro}>This replaces “Aperture” anywhere a customer meets the business. Write it as it should appear in the opening frame.</p>
              <label className={styles.field}>
                <span>Business name <b>Required</b></span>
                <input
                  autoComplete="organization"
                  value={brand.business_name}
                  maxLength={60}
                  disabled={assistantPending}
                  placeholder="Northstar Cinema"
                  onChange={(event) => update("business_name", event.target.value)}
                />
                <small>{brand.business_name.length}/60 · Used in the header, account pages and customer messages.</small>
              </label>
              <label className={styles.field}>
                <span>Tagline <i>Optional</i></span>
                <input
                  aria-label="Tagline"
                  value={brand.tagline}
                  maxLength={120}
                  disabled={assistantPending}
                  placeholder="Films that leave the light on."
                  onChange={(event) => update("tagline", event.target.value)}
                />
                <small>One memorable thought. It may appear in high-attention brand moments.</small>
              </label>
              <label className={styles.field}>
                <span>Short introduction <i>Optional</i></span>
                <textarea
                  rows={4}
                  value={brand.description}
                  maxLength={280}
                  disabled={assistantPending}
                  placeholder="An independent streaming home for daring cinema and essential television."
                  onChange={(event) => update("description", event.target.value)}
                />
                <small>{brand.description.length}/280 · Useful for metadata and future brand surfaces.</small>
              </label>

              <section
                className={styles.writingRoom}
                aria-labelledby="writing-room-title"
                aria-busy={assistantPending}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && event.target instanceof HTMLInputElement) event.preventDefault();
                }}
              >
                <header className={styles.writingRoomHeader}>
                  <span className={styles.writingRoomIcon}><SparklesIcon /></span>
                  <div>
                    <p>AI writing room</p>
                    <h3 id="writing-room-title">Find the words behind the name.</h3>
                  </div>
                  <span className={styles.assistantBadge}>Owner invoked</span>
                </header>

                <p className={styles.writingRoomIntro}>Shape a brief and ask for three distinct directions. Every result stays editable and outside your draft until you choose one.</p>

                <div className={styles.assistantBrief}>
                  <label className={styles.assistantField}>
                    <span>Who is this for?</span>
                    <input
                      aria-label="Who is this for?"
                      value={assistantAudience}
                      maxLength={160}
                      disabled={assistantPending}
                      placeholder="Independent-film devotees, families, genre fans…"
                      onChange={(event) => setAssistantAudience(event.target.value)}
                    />
                    <small>{assistantAudience.length}/160 · Audience, community, or viewing occasion.</small>
                  </label>
                  <label className={styles.assistantField}>
                    <span>Voice</span>
                    <select aria-label="Voice" value={assistantTone} disabled={assistantPending} onChange={(event) => setAssistantTone(event.target.value as BrandCopyTone)}>
                      {copyToneOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                    <small>The emotional temperature of the writing.</small>
                  </label>
                  <label className={`${styles.assistantField} ${styles.assistantDirection}`}>
                    <span>One more note <i>Optional</i></span>
                    <textarea
                      aria-label="One more note"
                      rows={2}
                      value={assistantDirection}
                      maxLength={240}
                      disabled={assistantPending}
                      placeholder="Avoid clichés. Make it feel intimate, contemporary, and international."
                      onChange={(event) => setAssistantDirection(event.target.value)}
                    />
                    <small>{assistantDirection.length}/240 · Themes, words to avoid, or a feeling to preserve.</small>
                  </label>
                </div>

                <p className={styles.assistantDisclosure}>
                  <span aria-hidden="true">i</span>
                  <span>
                    When you ask for ideas, your business name, current compact name, tagline, introduction, audience, voice, and optional note are sent to OpenAI. Studio does not add the generation request or returned options to your saved brand record. Only an option you apply and later save becomes part of your private draft. Do not enter personal data, credentials, unreleased catalog details, or rights and licensing information. OpenAI says API data is not used for model training by default unless the account opts in; abuse-monitoring logs may retain prompts and responses for up to 30 days, depending on the account&apos;s data controls. <a href="https://developers.openai.com/api/docs/guides/your-data" target="_blank" rel="noreferrer">Read OpenAI data controls</a>.
                  </span>
                </p>

                <div className={styles.assistantCommand}>
                  <button
                    type="button"
                    disabled={assistantPending || brand.business_name.trim().length < 2 || brand.business_name.trim().length > 60}
                    onClick={requestCopySuggestions}
                  >
                    <SparklesIcon />
                    {assistantPending ? "Writing three directions…" : assistantSuggestions.length ? "Create three new directions" : "Create three directions"}
                  </button>
                  <span>{brand.business_name.trim().length >= 2 && brand.business_name.trim().length <= 60
                    ? "Uses the business name and current copy above as context."
                    : "Enter a valid business name above to open the writing room."}</span>
                </div>

                <div className={styles.assistantMessages} aria-live="polite" aria-atomic="true">
                  {assistantNotice && <p className={styles.assistantNotice} role="status">{assistantNotice}</p>}
                  {assistantError && (
                    <div className={styles.assistantError} role="alert">
                      <p>{assistantError}</p>
                      <button type="button" disabled={assistantPending} onClick={requestCopySuggestions}>Try again</button>
                    </div>
                  )}
                </div>

                {assistantSuggestions.length > 0 && (
                  <div className={styles.suggestionGallery} aria-label="AI writing directions">
                    {assistantSuggestions.map((suggestion, index) => (
                      <article
                        className={styles.suggestionCard}
                        key={`${suggestion.tone_direction}-${index}`}
                        aria-labelledby={`copy-direction-${index + 1}`}
                      >
                        <header>
                          <span>Direction {String(index + 1).padStart(2, "0")}</span>
                          <h4 id={`copy-direction-${index + 1}`}>{suggestion.tone_direction}</h4>
                        </header>
                        <div className={styles.suggestionFields}>
                          <label>
                            <span>Compact name</span>
                            <input
                              aria-label={`Compact name, direction ${index + 1}`}
                              value={suggestion.short_name}
                              maxLength={24}
                              disabled={assistantPending}
                              onChange={(event) => editCopySuggestion(index, "short_name", event.target.value)}
                            />
                          </label>
                          <label>
                            <span>Tagline</span>
                            <input
                              aria-label={`Tagline, direction ${index + 1}`}
                              value={suggestion.tagline}
                              maxLength={120}
                              disabled={assistantPending}
                              onChange={(event) => editCopySuggestion(index, "tagline", event.target.value)}
                            />
                          </label>
                          <label>
                            <span>Short introduction</span>
                            <textarea
                              aria-label={`Short introduction, direction ${index + 1}`}
                              rows={3}
                              value={suggestion.description}
                              maxLength={280}
                              disabled={assistantPending}
                              onChange={(event) => editCopySuggestion(index, "description", event.target.value)}
                            />
                          </label>
                        </div>
                        <footer>
                          <span>Review every word before using it.</span>
                          <button type="button" disabled={assistantPending} onClick={() => applyCopySuggestion(index)}>Apply this direction</button>
                        </footer>
                      </article>
                    ))}
                  </div>
                )}

              </section>
            </fieldset>
          )}

          {activeStep === 2 && (
            <fieldset>
              <legend>Shape the signature.</legend>
              <p className={styles.stepIntro}>A compact name keeps the identity legible on phones, profile selectors and small browser icons.</p>
              <label className={styles.field}>
                <span>Compact brand name <b>Required</b></span>
                <input
                  value={brand.short_name}
                  maxLength={24}
                  placeholder={brand.business_name || "Northstar"}
                  onChange={(event) => update("short_name", event.target.value)}
                />
                <small>2–24 characters. The wordmark stays typographic; the Logo Atelier below shapes its compact companion.</small>
              </label>
              <div
                className={styles.signatureStudy}
                aria-label="Generated signature study"
                style={{
                  "--atelier-accent": brand.palette.accent,
                  "--atelier-ink": brand.palette.text,
                  "--atelier-muted": brand.palette.text_muted,
                  "--atelier-surface": brand.palette.surface,
                  "--atelier-elevated": brand.palette.surface_elevated,
                } as CSSProperties}
              >
                <article>
                  <small>Primary wordmark</small>
                  <strong>{brand.short_name || brand.business_name || "Your cinema"}</strong>
                </article>
                <article>
                  <small>{brand.logo_mark ? "Studio mark" : logoSrc ? "Existing uploaded mark" : "Compact mark"}</small>
                  {brand.logo_mark
                    ? <span className={styles.signatureGeneratedLogo}><GeneratedLogo recipe={brand.logo_mark} decorative size={104} instanceKey="signature-study" /></span>
                    : logoSrc
                      ? <span className={styles.signatureLogo}><Image alt="" src={logoSrc} width={120} height={120} unoptimized /></span>
                      : <strong>{initials(brand.short_name || brand.business_name)}</strong>}
                </article>
              </div>
              <LogoAtelier
                value={brand.logo_mark}
                suggestedGlyph={brand.short_name || brand.business_name}
                palette={brand.palette}
                legacyLogoActive={Boolean(record.config.logo_url)}
                disabled={pending}
                onChange={(logoMark) => update("logo_mark", logoMark)}
              />
            </fieldset>
          )}

          {activeStep === 3 && (
            <fieldset>
              <legend>Choose how the room is lit.</legend>
              <p className={styles.stepIntro}>Start from a designed palette, then tune every role. Contrast is checked before the draft can continue.</p>
              <div className={styles.palettePresets}>
                {palettes.map((preset) => (
                  <button
                    key={preset.name}
                    type="button"
                    aria-pressed={selectedPalette === preset.name}
                    onClick={() => update("palette", preset.values)}
                  >
                    <span aria-hidden="true">
                      <i style={{ background: preset.values.surface }} />
                      <i style={{ background: preset.values.accent }} />
                      <i style={{ background: preset.values.text }} />
                    </span>
                    <strong>{preset.name}</strong>
                    <small>{preset.note}</small>
                  </button>
                ))}
              </div>
              <details className={styles.advancedColors}>
                <summary>Fine-tune the six color roles</summary>
                <div>
                  <PaletteField label="Accent" value={brand.palette.accent} onChange={(value) => update("palette", { ...brand.palette, accent: value })} />
                  <PaletteField label="Accent hover" value={brand.palette.accent_hover} onChange={(value) => update("palette", { ...brand.palette, accent_hover: value })} />
                  <PaletteField label="Main surface" value={brand.palette.surface} onChange={(value) => update("palette", { ...brand.palette, surface: value })} />
                  <PaletteField label="Raised surface" value={brand.palette.surface_elevated} onChange={(value) => update("palette", { ...brand.palette, surface_elevated: value })} />
                  <PaletteField label="Primary text" value={brand.palette.text} onChange={(value) => update("palette", { ...brand.palette, text: value })} />
                  <PaletteField label="Supporting text" value={brand.palette.text_muted} onChange={(value) => update("palette", { ...brand.palette, text_muted: value })} />
                </div>
              </details>
              <div className={styles.contrastLedger}>
                <span data-pass={contrast(brand.palette.text, brand.palette.surface) >= 4.5}>Text {contrast(brand.palette.text, brand.palette.surface).toFixed(1)}:1</span>
                <span data-pass={contrast(brand.palette.text_muted, brand.palette.surface) >= 4.5}>Supporting {contrast(brand.palette.text_muted, brand.palette.surface).toFixed(1)}:1</span>
                <span data-pass={contrast(brand.palette.accent, brand.palette.surface) >= 4.5}>Accent {contrast(brand.palette.accent, brand.palette.surface).toFixed(1)}:1</span>
                <span data-pass={Boolean(onAccentColor(brand.palette))}>Button text {onAccentColor(brand.palette) ?? "none"}</span>
              </div>
            </fieldset>
          )}

          {activeStep === 4 && (
            <fieldset>
              <legend>Set the home market.</legend>
              <p className={styles.stepIntro}>These defaults shape language, regional discovery and price display. Customers can still have their own preferences.</p>
              <div className={styles.marketGrid}>
                <label className={styles.field}>
                  <span>Default language</span>
                  <input aria-label="Default language" list="launch-locale-options" value={brand.locale.default_locale} onChange={(event) => update("locale", { ...brand.locale, default_locale: event.target.value })} />
                  <datalist id="launch-locale-options">{localeOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</datalist>
                  <small>Enter any valid BCP 47 tag. This is the first language shown to a new visitor.</small>
                </label>
                <label className={styles.field}>
                  <span>Home market</span>
                  <select aria-label="Home market" value={brand.locale.home_market} onChange={(event) => update("locale", { ...brand.locale, home_market: event.target.value })}>
                    {marketOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                  <small>Your business base—not a rights declaration.</small>
                </label>
                <label className={styles.field}>
                  <span>Display currency</span>
                  <select aria-label="Display currency" value={brand.locale.currency} onChange={(event) => update("locale", { ...brand.locale, currency: event.target.value })}>
                    {currencyOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                  <small>The default currency for plans and revenue reports.</small>
                </label>
              </div>
              <div className={styles.marketTicket}>
                <span>{brand.locale.home_market}</span>
                <div><small>Opening territory</small><strong>{marketOptions.find(([value]) => value === brand.locale.home_market)?.[1]}</strong></div>
                <div><small>Customer language</small><strong>{brand.locale.default_locale}</strong></div>
                <div><small>Box office</small><strong>{brand.locale.currency}</strong></div>
              </div>
            </fieldset>
          )}

          {activeStep === 5 && (
            <fieldset>
              <legend>Ready for the first frame?</legend>
              <p className={styles.stepIntro}>Publishing changes the public identity—not the catalog, subscriptions, customer accounts or playback configuration.</p>
              <dl className={styles.reviewLedger}>
                <div><dt>Public name</dt><dd>{brand.business_name || "Not set"}</dd><button type="button" onClick={() => setActiveStep(1)}>Edit</button></div>
                <div><dt>Signature</dt><dd>{brand.short_name || "Not set"} · {brand.logo_mark ? `${brand.logo_mark.glyph} / ${brand.logo_mark.variant}` : initials(brand.short_name || brand.business_name)}</dd><button type="button" onClick={() => setActiveStep(2)}>Edit</button></div>
                <div><dt>Palette</dt><dd><i style={{ background: brand.palette.surface }} /><i style={{ background: brand.palette.accent }} /><i style={{ background: brand.palette.text }} />{selectedPalette || "Custom palette"}</dd><button type="button" onClick={() => setActiveStep(3)}>Edit</button></div>
                <div><dt>Home market</dt><dd>{brand.locale.default_locale} · {brand.locale.home_market} · {brand.locale.currency}</dd><button type="button" onClick={() => setActiveStep(4)}>Edit</button></div>
              </dl>
              <label className={styles.confirmation}>
                <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                <span><strong>I approve this identity for publication.</strong><small>The current draft becomes the public brand configuration. It can be revised later in Studio.</small></span>
              </label>
            </fieldset>
          )}

          {(clientError || result.error) && <p className={styles.error} role="alert">{clientError || result.error}</p>}
          {result.notice && !result.error && <p className={styles.notice} role="status">{result.notice}</p>}

          <footer className={styles.formActions}>
            <button className={styles.backButton} type="button" onClick={goBack} disabled={activeStep === 1 || pending || assistantPending}>Back</button>
            <span>Changes are private until publication.</span>
            <button className={styles.continueButton} type="submit" disabled={pending || assistantPending}>
              {pending ? "Securing the draft…" : activeStep === 5 ? (record.status === "published" ? "Publish revision" : "Publish my brand") : "Save & continue"}
              {!pending && <span aria-hidden="true">→</span>}
            </button>
          </footer>
        </form>

        <BrandPreview brand={brand} logoSrc={logoSrc} />
      </div>
    </section>
  );
}
