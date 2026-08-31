import { useId } from "react";

import {
  generatedLogoDefinitionPrefix,
  generatedLogoVariantMeta,
  isGeneratedLogoRecipe,
  type GeneratedLogoGlyph,
  type GeneratedLogoRecipe,
  type GeneratedLogoVariant,
} from "@/app/lib/generated-logo";
import { generatedLogoGlyphOutline } from "@/app/lib/generated-logo-glyph-paths";

export type GeneratedLogoProps = {
  recipe: GeneratedLogoRecipe;
  label?: string;
  decorative?: boolean;
  className?: string;
  size?: number;
  instanceKey?: string;
  /** Explicit paint for server image renderers; browser marks normally inherit currentColor. */
  color?: string;
};

type DefinitionIds = {
  linear: string;
  eclipseMask: string;
  stencilMask: string;
};

const marqueeLights = [18, 31, 44, 56, 69, 82];
const sprockets = [22, 38, 54, 70, 86];

function renderLetter({ glyph, offsetX = 0, offsetY = 0, opacity = 1, fill = "currentColor" }: {
  glyph: GeneratedLogoGlyph;
  offsetX?: number;
  offsetY?: number;
  opacity?: number;
  fill?: "currentColor" | "black";
}) {
  const outline = generatedLogoGlyphOutline(glyph);
  const transform = offsetX || offsetY ? `translate(${offsetX} ${offsetY})` : undefined;
  return (
    <path
      d={outline.d}
      fill={fill}
      opacity={opacity}
      transform={transform}
      data-logo-letter={glyph}
    />
  );
}

function renderDefinitions({ glyph, ids }: {
  glyph: GeneratedLogoGlyph;
  ids: DefinitionIds;
}) {
  return (
    <defs>
      <linearGradient id={ids.linear} x1="12" y1="8" x2="92" y2="96" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor="currentColor" stopOpacity="1" />
        <stop offset="1" stopColor="currentColor" stopOpacity="0.3" />
      </linearGradient>
      <mask id={ids.eclipseMask} maskUnits="userSpaceOnUse" x="0" y="0" width="104" height="104">
        <rect width="104" height="104" fill="white" />
        <circle cx="65" cy="43" r="34" fill="black" />
      </mask>
      <mask id={ids.stencilMask} maskUnits="userSpaceOnUse" x="0" y="0" width="104" height="104">
        <rect width="104" height="104" fill="white" />
        {renderLetter({ glyph, fill: "black" })}
      </mask>
    </defs>
  );
}

function renderArtwork({ glyph, variant, ids }: {
  glyph: GeneratedLogoGlyph;
  variant: GeneratedLogoVariant;
  ids: DefinitionIds;
}) {
  if (variant === "marquee") {
    return (
      <g>
        <rect x="7" y="7" width="90" height="90" rx="22" fill="currentColor" opacity="0.08" />
        <rect x="11" y="11" width="82" height="82" rx="19" fill="none" stroke="currentColor" strokeWidth="3" />
        <g fill="currentColor">
          {marqueeLights.map((position) => <circle key={`top-${position}`} cx={position} cy="17" r="1.8" />)}
          {marqueeLights.map((position) => <circle key={`bottom-${position}`} cx={position} cy="87" r="1.8" />)}
        </g>
        <g fill="none" stroke="currentColor" strokeWidth="0.8" opacity="0.4">
          {marqueeLights.map((position) => <circle key={`top-halo-${position}`} cx={position} cy="17" r="3.1" />)}
          {marqueeLights.map((position) => <circle key={`bottom-halo-${position}`} cx={position} cy="87" r="3.1" />)}
        </g>
        {renderLetter({ glyph })}
      </g>
    );
  }
  if (variant === "prism") {
    return (
      <g>
        <rect x="7" y="7" width="90" height="90" rx="18" fill="none" stroke="currentColor" strokeWidth="2" />
        <polygon points="7,8 95,8 95,43 7,78" fill={`url(#${ids.linear})`} opacity="0.3" />
        <polygon points="7,78 95,43 95,96 7,96" fill="currentColor" opacity="0.08" />
        {renderLetter({ glyph })}
        <line x1="15" y1="86" x2="90" y2="18" stroke="currentColor" strokeWidth="1.5" opacity="0.7" />
      </g>
    );
  }
  if (variant === "orbit") {
    return (
      <g>
        <circle cx="52" cy="52" r="36" fill="currentColor" opacity="0.1" />
        <circle cx="52" cy="52" r="35" fill="none" stroke="currentColor" strokeWidth="3" />
        <ellipse cx="52" cy="52" rx="47" ry="25" fill="none" stroke="currentColor" strokeWidth="1.5" transform="rotate(-24 52 52)" opacity="0.7" />
        <circle cx="91" cy="34" r="4" fill="currentColor" />
        <circle cx="91" cy="34" r="7" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.35" />
        {renderLetter({ glyph })}
      </g>
    );
  }
  if (variant === "film-frame") {
    return (
      <g>
        <rect x="6" y="10" width="92" height="84" rx="13" fill="currentColor" opacity="0.07" />
        <rect x="6" y="10" width="92" height="84" rx="13" fill="none" stroke="currentColor" strokeWidth="2" />
        <g fill="currentColor" opacity="0.72">
          {sprockets.map((position) => <rect key={`top-${position}`} x={position} y="14" width="7" height="4" rx="1" />)}
          {sprockets.map((position) => <rect key={`bottom-${position}`} x={position} y="86" width="7" height="4" rx="1" />)}
        </g>
        {renderLetter({ glyph })}
        <line x1="20" y1="76" x2="84" y2="76" stroke="currentColor" strokeWidth="2" />
      </g>
    );
  }
  if (variant === "eclipse") {
    return (
      <g>
        <circle cx="49" cy="50" r="43" fill="currentColor" opacity="0.24" mask={`url(#${ids.eclipseMask})`} />
        <circle cx="52" cy="52" r="43" fill="none" stroke="currentColor" strokeWidth="2" />
        <ellipse cx="52" cy="75" rx="35" ry="13" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.58" />
        {renderLetter({ glyph })}
      </g>
    );
  }
  if (variant === "stencil") {
    return (
      <g>
        <rect x="7" y="7" width="90" height="90" rx="15" fill="currentColor" mask={`url(#${ids.stencilMask})`} />
        <line x1="14" y1="84" x2="90" y2="84" stroke="currentColor" strokeWidth="1.5" opacity="0.58" />
      </g>
    );
  }
  if (variant === "signal") {
    return (
      <g>
        <rect x="7" y="7" width="90" height="90" rx="25" fill="none" stroke="currentColor" strokeWidth="2" opacity="0.28" />
        {renderLetter({ glyph, offsetX: -7, opacity: 0.18 })}
        {renderLetter({ glyph, offsetX: -3, opacity: 0.42 })}
        {renderLetter({ glyph, offsetX: 2 })}
        <line x1="18" y1="80" x2="86" y2="80" stroke="currentColor" strokeWidth="2" opacity="0.7" />
        <line x1="22" y1="86" x2="82" y2="86" stroke="currentColor" strokeWidth="2" opacity="0.35" />
      </g>
    );
  }
  if (variant === "monolith") {
    return (
      <g>
        <rect x="24" y="5" width="56" height="94" rx="8" fill="currentColor" opacity="0.09" />
        <rect x="24" y="5" width="56" height="94" rx="8" fill="none" stroke="currentColor" strokeWidth="3" />
        <line x1="31" y1="20" x2="73" y2="20" stroke="currentColor" strokeWidth="1.5" opacity="0.55" />
        <line x1="31" y1="84" x2="73" y2="84" stroke="currentColor" strokeWidth="1.5" opacity="0.55" />
        {renderLetter({ glyph })}
      </g>
    );
  }
  if (variant === "beam") {
    return (
      <g>
        <polygon points="32,7 72,7 95,96 9,96" fill={`url(#${ids.linear})`} opacity="0.22" />
        <ellipse cx="52" cy="89" rx="42" ry="9" fill="currentColor" opacity="0.18" />
        <circle cx="52" cy="50" r="31" fill="none" stroke="currentColor" strokeWidth="2" />
        {renderLetter({ glyph, offsetY: -2 })}
      </g>
    );
  }
  if (variant === "portal") {
    return (
      <g>
        <rect x="17" y="18" width="70" height="57" rx="8" fill="currentColor" opacity="0.08" />
        <rect x="17" y="18" width="70" height="57" rx="8" fill="none" stroke="currentColor" strokeWidth="3" />
        <line x1="23" y1="82" x2="8" y2="92" stroke="currentColor" strokeWidth="2" opacity="0.48" />
        <line x1="52" y1="82" x2="52" y2="99" stroke="currentColor" strokeWidth="2" opacity="0.48" />
        <line x1="81" y1="82" x2="96" y2="92" stroke="currentColor" strokeWidth="2" opacity="0.48" />
        {renderLetter({ glyph, offsetY: -5.5 })}
      </g>
    );
  }
  if (variant === "ribbon") {
    return (
      <g>
        <ellipse cx="52" cy="52" rx="45" ry="27" fill="none" stroke="currentColor" strokeWidth="4" transform="rotate(28 52 52)" opacity="0.36" />
        <ellipse cx="52" cy="52" rx="45" ry="27" fill="none" stroke="currentColor" strokeWidth="2" transform="rotate(-28 52 52)" opacity="0.72" />
        <circle cx="52" cy="52" r="34" fill="currentColor" opacity="0.08" />
        {renderLetter({ glyph })}
      </g>
    );
  }
  return (
    <g>
      <circle cx="52" cy="52" r="39" fill="none" stroke={`url(#${ids.linear})`} strokeWidth="9" strokeDasharray="45 12" />
      <polygon points="52,13 75,25 91,49 80,76 55,91 28,80 13,56 24,29" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.54" />
      <circle cx="52" cy="52" r="28" fill="currentColor" opacity="0.08" />
      {renderLetter({ glyph })}
    </g>
  );
}

type GeneratedLogoSvgProps = GeneratedLogoProps & { definitionPrefix: string };

function renderGeneratedLogoSvg({
  recipe,
  label,
  decorative = false,
  className,
  size = 104,
  color,
  definitionPrefix,
}: GeneratedLogoSvgProps) {
  if (!isGeneratedLogoRecipe(recipe)) return null;
  const safeSize = Number.isFinite(size) ? Math.min(2048, Math.max(16, Math.round(size))) : 104;
  const titleId = `${definitionPrefix}-title`;
  const ids = {
    linear: `${definitionPrefix}-linear`,
    eclipseMask: `${definitionPrefix}-eclipse-mask`,
    stencilMask: `${definitionPrefix}-stencil-mask`,
  };
  const accessibleName = label?.trim() || `${recipe.glyph} · ${generatedLogoVariantMeta(recipe.variant).name} generated logo`;

  return (
    <svg
      className={className}
      width={safeSize}
      height={safeSize}
      viewBox="0 0 104 104"
      preserveAspectRatio="xMidYMid meet"
      xmlns="http://www.w3.org/2000/svg"
      style={color ? { color } : undefined}
      focusable="false"
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-labelledby={decorative ? undefined : titleId}
      data-logo-renderer-version={recipe.renderer_version}
      data-logo-glyph={recipe.glyph}
      data-logo-variant={recipe.variant}
    >
      {!decorative && <title id={titleId}>{accessibleName}</title>}
      {renderDefinitions({ glyph: recipe.glyph, ids })}
      <g aria-hidden="true">
        {renderArtwork({ glyph: recipe.glyph, variant: recipe.variant, ids })}
      </g>
    </svg>
  );
}

/** A recipe-only, code-native SVG used consistently across private and public UI. */
export function GeneratedLogo({
  recipe,
  instanceKey = "mark",
  ...props
}: GeneratedLogoProps) {
  const reactId = useId();
  if (!isGeneratedLogoRecipe(recipe)) return null;
  const definitionPrefix = generatedLogoDefinitionPrefix(recipe, `${instanceKey}:${reactId}`);
  return renderGeneratedLogoSvg({ ...props, recipe, instanceKey, definitionPrefix });
}

/** Hook-free renderer for Next ImageResponse. Uses the same trusted paths as browser SVGs. */
export function StaticGeneratedLogo({
  recipe,
  instanceKey = "static-mark",
  ...props
}: GeneratedLogoProps) {
  if (!isGeneratedLogoRecipe(recipe)) return null;
  const definitionPrefix = generatedLogoDefinitionPrefix(recipe, `static:${instanceKey}`);
  return renderGeneratedLogoSvg({ ...props, recipe, instanceKey, definitionPrefix });
}
