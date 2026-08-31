"use client";

import type { CSSProperties } from "react";

import { GeneratedLogo } from "@/app/components/generated-logo";
import {
  createGeneratedLogoRecipe,
  generatedLogoGlyphFrom,
  generatedLogoGlyphs,
  generatedLogoVariantMeta,
  generatedLogoVariants,
  type GeneratedLogoGlyph,
  type GeneratedLogoRecipe,
} from "@/app/lib/generated-logo";
import type { EditableSiteBrandPalette } from "./launch-setup-types";
import styles from "./launch-setup.module.css";

type LogoAtelierProps = {
  value: GeneratedLogoRecipe | null;
  suggestedGlyph: string;
  palette: EditableSiteBrandPalette;
  legacyLogoActive: boolean;
  disabled: boolean;
  onChange: (recipe: GeneratedLogoRecipe) => void;
};

const uppercaseGlyphs = generatedLogoGlyphs.slice(0, 26);
const lowercaseGlyphs = generatedLogoGlyphs.slice(26);

function glyphCase(glyph: GeneratedLogoGlyph): "upper" | "lower" {
  return glyph === glyph.toUpperCase() ? "upper" : "lower";
}

function changeCase(glyph: GeneratedLogoGlyph, nextCase: "upper" | "lower"): GeneratedLogoGlyph {
  return generatedLogoGlyphFrom(nextCase === "upper" ? glyph.toUpperCase() : glyph.toLowerCase());
}

export function LogoAtelier({
  value,
  suggestedGlyph,
  palette,
  legacyLogoActive,
  disabled,
  onChange,
}: LogoAtelierProps) {
  const suggested = generatedLogoGlyphFrom(suggestedGlyph).toUpperCase() as GeneratedLogoGlyph;
  const active = value ?? createGeneratedLogoRecipe(suggested, "iris");
  const activeCase = glyphCase(active.glyph);
  const alphabet = activeCase === "upper" ? uppercaseGlyphs : lowercaseGlyphs;
  const meta = generatedLogoVariantMeta(active.variant);
  const paletteStyle = {
    "--atelier-accent": palette.accent,
    "--atelier-ink": palette.text,
    "--atelier-muted": palette.text_muted,
    "--atelier-surface": palette.surface,
    "--atelier-elevated": palette.surface_elevated,
  } as CSSProperties;
  const differsFromName = active.glyph.toLowerCase() !== suggested.toLowerCase();

  function selectGlyph(glyph: GeneratedLogoGlyph) {
    onChange(createGeneratedLogoRecipe(glyph, active.variant));
  }

  return (
    <section className={styles.logoAtelier} style={paletteStyle} aria-labelledby="logo-atelier-title">
      <header className={styles.logoAtelierHeader}>
        <p><span>Logo atelier</span><span>Code-built SVG</span></p>
        <h3 id="logo-atelier-title">Choose a mark that survives every screen.</h3>
        <p>Start with any uppercase or lowercase letter, then audition twelve curated constructions. The chosen recipe stays editable and automatically follows the published brand palette.</p>
      </header>

      {legacyLogoActive && !value ? (
        <p className={styles.legacyLogoNotice} role="status">
          Your existing uploaded logo remains active. Choosing a Studio mark below will replace it only after you save this stage.
        </p>
      ) : null}

      <div className={styles.logoAtelierControls}>
        <fieldset className={styles.logoCasePicker}>
          <legend>Letter case</legend>
          <label>
            <input
              type="radio"
              name="logo-letter-case"
              checked={activeCase === "upper"}
              disabled={disabled}
              onChange={() => selectGlyph(changeCase(active.glyph, "upper"))}
            />
            <span>Uppercase</span><small>A–Z</small>
          </label>
          <label>
            <input
              type="radio"
              name="logo-letter-case"
              checked={activeCase === "lower"}
              disabled={disabled}
              onChange={() => selectGlyph(changeCase(active.glyph, "lower"))}
            />
            <span>Lowercase</span><small>a–z</small>
          </label>
        </fieldset>

        <fieldset className={styles.logoGlyphPicker}>
          <legend>Monogram letter</legend>
          <div>
            {alphabet.map((glyph) => (
              <label key={glyph}>
                <input
                  type="radio"
                  name="logo-glyph"
                  value={glyph}
                  checked={Boolean(value) && active.glyph === glyph}
                  disabled={disabled}
                  aria-label={`${activeCase === "upper" ? "Uppercase" : "Lowercase"} ${glyph}`}
                  onChange={() => selectGlyph(glyph)}
                />
                <span aria-hidden="true">{glyph}</span>
              </label>
            ))}
          </div>
          <button type="button" disabled={disabled} onClick={() => selectGlyph(suggested)}>
            Use name initial <span aria-hidden="true">{suggested}</span>
          </button>
        </fieldset>
      </div>

      <fieldset className={styles.logoVariantPicker}>
        <legend>Choose a construction</legend>
        <p>Twelve systems, one active letter. Effects are made only from trusted SVG geometry—no imported code or external assets.</p>
        <div>
          {generatedLogoVariants.map((variant) => {
            const recipe = createGeneratedLogoRecipe(active.glyph, variant.id);
            const checked = Boolean(value) && active.variant === variant.id;
            return (
              <label key={variant.id}>
                <input
                  type="radio"
                  name="logo-variant"
                  value={variant.id}
                  checked={checked}
                  disabled={disabled}
                  aria-label={`${variant.name}, ${activeCase === "upper" ? "uppercase" : "lowercase"} ${active.glyph}`}
                  onChange={() => onChange(recipe)}
                />
                <span className={styles.logoVariantArt}><GeneratedLogo recipe={recipe} decorative size={96} instanceKey={`atelier-${variant.id}`} /></span>
                <span className={styles.logoVariantCopy}><strong>{variant.name}</strong><small>{variant.note}</small></span>
                <b aria-hidden="true">{checked ? "Selected" : "Preview"}</b>
              </label>
            );
          })}
        </div>
      </fieldset>

      <section className={styles.logoProofs} aria-labelledby="logo-proof-title">
        <div className={styles.logoProofHero}>
          <p><span>Selected study</span><span>{active.glyph} · {meta.name}</span></p>
          <GeneratedLogo
            recipe={active}
            label={`${meta.name} logo using ${activeCase === "upper" ? "uppercase" : "lowercase"} ${active.glyph}`}
            size={176}
            instanceKey="atelier-selected"
          />
          <h4 id="logo-proof-title">{meta.name}</h4>
          <p>{meta.note}</p>
        </div>
        <div className={styles.logoContextProofs}>
          <article><small>Navbar · 31 px</small><span><GeneratedLogo recipe={active} decorative size={31} instanceKey="proof-navbar" /><b>{suggestedGlyph || "Your brand"}</b></span></article>
          <article><small>App icon · 64 px</small><span><GeneratedLogo recipe={active} decorative size={64} instanceKey="proof-app" /></span></article>
          <article><small>Favicon · 16 px</small><span><GeneratedLogo recipe={active} decorative size={16} instanceKey="proof-favicon" /></span></article>
          <article className={styles.logoStampProof}><small>One-colour stamp</small><span><GeneratedLogo recipe={active} decorative size={52} instanceKey="proof-stamp" /></span></article>
        </div>
      </section>

      <div className={styles.logoAtelierLedger} aria-live="polite">
        <p><strong>{value ? "Studio mark selected" : "Previewing a replacement"}</strong><span>{activeCase === "upper" ? "Uppercase" : "Lowercase"} {active.glyph} · {meta.name}</span></p>
        {differsFromName ? <p>That letter differs from the current compact-name initial ({suggested}). Choose intentionally or reset it above.</p> : null}
        <p>These construction systems are shared starting points, not trademark clearance. Review the final identity before publication.</p>
      </div>
    </section>
  );
}
