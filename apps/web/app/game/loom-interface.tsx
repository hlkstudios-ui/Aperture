"use client";

import {
  useEffect,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import type {
  LoomGameSnapshot,
  LoomPrimedInputFeedback,
  LoomRunMode,
} from "./loom-game-types";
import styles from "./loom-interface.module.css";
import { useSiteBrand } from "@/app/components/site-brand-provider";

export type LoomTouchDirection = "up" | "left" | "down" | "right";

export interface LoomEventNotice {
  id: number;
  tone: "miss" | "break" | "iris-clear" | "iris-hit";
  eyebrow: string;
  title: string;
  detail: string;
}

export interface LoomInterfaceProps {
  snapshot: LoomGameSnapshot;
  mode: LoomRunMode;
  ready: boolean;
  countdown?: number;
  primedInput: LoomPrimedInputFeedback;
  announcement?: string;
  eventNotice?: LoomEventNotice | null;
  error?: string | null;
  muted: boolean;
  comfortMode: boolean;
  fullscreenAvailable: boolean;
  fullscreenActive: boolean;
  bestScore?: number;
  isNewBest?: boolean;
  leftHanded?: boolean;
  children?: ReactNode;
  onBegin(): void;
  onPause(): void;
  onResume(): void;
  onEnd(): void;
  onTogglePhase(): void;
  onSetReel(active: boolean): void;
  onActivateResonance(): void;
  onTouchDirection(direction: LoomTouchDirection, pressed: boolean): void;
  onToggleSound(): void;
  onToggleComfort(): void;
  onToggleFullscreen(): void;
  onExit(): void;
}

const ARC_LABELS = {
  1: "Threading",
  2: "Refraction",
  3: "Iris",
  4: "Extraction",
} as const;

const ENCOUNTER_LABELS = {
  "opening-thread": "Opening thread",
  "quiet-splice": "Quiet splice",
  "wide-exposure": "Wide exposure",
  "phase-lattice": "Phase lattice",
  counterturn: "Counterturn",
  "iris-approach": "Iris approach",
  "extraction-mark": "Extraction mark",
} as const;

const DIRECTIONS: readonly {
  direction: LoomTouchDirection;
  label: string;
  glyph: string;
}[] = [
  { direction: "up", label: "Steer up", glyph: "↑" },
  { direction: "left", label: "Steer left", glyph: "←" },
  { direction: "down", label: "Steer down", glyph: "↓" },
  { direction: "right", label: "Steer right", glyph: "→" },
] as const;

const RESONANCE_PIPS = [0, 1, 2] as const;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function formatClock(seconds: number): string {
  const whole = Math.max(0, Math.ceil(Number.isFinite(seconds) ? seconds : 0));
  const minutes = Math.floor(whole / 60);
  return `${String(minutes).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

function formatScore(score: number): string {
  return Math.max(0, Math.floor(Number.isFinite(score) ? score : 0)).toLocaleString(
    "en-CA",
  );
}

function phaseLabel(phase: LoomGameSnapshot["phase"]): string {
  return phase === "ember" ? "Ember" : "Cobalt";
}

function joinClasses(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute("hidden"));
}

export function LoomInterface({
  snapshot,
  mode,
  ready,
  countdown = 3,
  primedInput,
  announcement = "",
  eventNotice = null,
  error = null,
  muted,
  comfortMode,
  fullscreenAvailable,
  fullscreenActive,
  bestScore = 0,
  isNewBest = false,
  leftHanded = false,
  children,
  onBegin,
  onPause,
  onResume,
  onEnd,
  onTogglePhase,
  onSetReel,
  onActivateResonance,
  onTouchDirection,
  onToggleSound,
  onToggleComfort,
  onToggleFullscreen,
  onExit,
}: LoomInterfaceProps) {
  const brand = useSiteBrand();
  const dialogRef = useRef<HTMLElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const suppressDirectionClickRef = useRef(false);
  const suppressReelClickRef = useRef(false);
  const isResult = mode === "finished";
  const modalOpen = mode === "paused" || isResult || Boolean(error);
  const isStaging = mode === "countdown" || mode === "resuming";
  const isLive = mode === "running";
  const controlsEnabled = isLive || isStaging;
  const showRunChrome = mode !== "idle" && !isResult;
  const displayedPhase = isStaging && primedInput.phase
    ? primedInput.phase
    : snapshot.phase;
  const phase = phaseLabel(displayedPhase);
  const actualPhase = phaseLabel(snapshot.phase);
  const nextPhase = phaseLabel(snapshot.phase === "ember" ? "cobalt" : "ember");
  const phaseActionLabel = primedInput.phase
    ? `${phase} phase armed. Activate again to remain ${actualPhase}.`
    : `${actualPhase} phase active. Shift to ${nextPhase}.`;
  const tensionPercent = Math.round(clamp(snapshot.threadTension, 0, 1) * 100);
  const contractPercent = Math.round(clamp(snapshot.contractProgress, 0, 1) * 100);
  const activeEncounter = snapshot.activeEncounter;
  const resonanceActive = snapshot.resonanceRemaining > 0;
  const resonanceRecovering =
    !resonanceActive && snapshot.resonanceCooldownRemaining > 0;
  const resonanceAvailable =
    snapshot.resonanceReady && !resonanceActive && !resonanceRecovering;
  const compactResonance = resonanceActive
    ? `2× ${snapshot.resonanceRemaining.toFixed(1)}s`
    : resonanceRecovering
      ? `REC ${Math.ceil(snapshot.resonanceCooldownRemaining)}s`
      : `RES ${snapshot.resonanceCharge}/3`;
  const resonanceControlLabel = resonanceActive
    ? `Resonance multiplier active, ${snapshot.resonanceRemaining.toFixed(1)} seconds remaining.`
    : resonanceRecovering
      ? `Resonance recovering, ${Math.ceil(snapshot.resonanceCooldownRemaining)} seconds remaining.`
      : `Resonance charge ${snapshot.resonanceCharge} of 3.`;
  const phaseControlLabel = `${phaseActionLabel} ${resonanceControlLabel}`;
  const extraction = snapshot.extraction;
  const irisIncoming =
    snapshot.iris.active &&
    snapshot.iris.stage !== "dormant" &&
    snapshot.iris.stage !== "recovery";
  const irisSecondsToContact = snapshot.iris.secondsToContact ?? 0;

  useEffect(() => {
    if (!modalOpen) return;
    returnFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => dialogRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      returnFocusRef.current?.focus({ preventScroll: true });
    };
  }, [modalOpen, mode]);

  const keepDialogFocus = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape" && mode === "paused" && !error) {
      event.preventDefault();
      onResume();
      return;
    }
    if (event.key !== "Tab") return;
    const elements = focusableElements(event.currentTarget);
    if (elements.length === 0) {
      event.preventDefault();
      event.currentTarget.focus();
      return;
    }
    const first = elements[0];
    const last = elements[elements.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const beginDirection = (
    event: ReactPointerEvent<HTMLButtonElement>,
    direction: LoomTouchDirection,
  ) => {
    event.preventDefault();
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // A cancelled touch can invalidate capture before this event completes.
    }
    onTouchDirection(direction, true);
  };

  const endDirection = (direction: LoomTouchDirection) => {
    onTouchDirection(direction, false);
  };

  const directionKey = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
    direction: LoomTouchDirection,
    pressed: boolean,
  ) => {
    if (event.key !== " " && event.key !== "Enter") return;
    event.preventDefault();
    if (event.repeat && pressed) return;
    suppressDirectionClickRef.current = true;
    onTouchDirection(direction, pressed);
    if (!pressed) {
      window.requestAnimationFrame(() => {
        suppressDirectionClickRef.current = false;
      });
    }
  };

  const accessibleDirectionClick = (
    event: ReactMouseEvent<HTMLButtonElement>,
    direction: LoomTouchDirection,
  ) => {
    if (event.detail !== 0) return;
    if (suppressDirectionClickRef.current) {
      suppressDirectionClickRef.current = false;
      return;
    }
    onTouchDirection(direction, true);
    window.requestAnimationFrame(() => onTouchDirection(direction, false));
  };

  const beginReel = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Pointer capture is best-effort on older touch browsers.
    }
    onSetReel(true);
  };

  const endReel = () => onSetReel(false);

  const reelKey = (event: ReactKeyboardEvent<HTMLButtonElement>, pressed: boolean) => {
    if (event.key !== " " && event.key !== "Enter") return;
    event.preventDefault();
    if (event.repeat && pressed) return;
    suppressReelClickRef.current = true;
    onSetReel(pressed);
    if (!pressed) {
      window.requestAnimationFrame(() => {
        suppressReelClickRef.current = false;
      });
    }
  };

  const stagedParts = [
    primedInput.direction ? `${primedInput.direction} line` : null,
    primedInput.phase ? `${phaseLabel(primedInput.phase)} phase` : null,
    primedInput.reel ? "Reel held" : null,
    primedInput.resonance ? "Resonance release" : null,
  ].filter((part): part is string => Boolean(part));
  const stagedStatus = stagedParts.length > 0
    ? `${stagedParts.join(" · ")} armed`
    : mode === "resuming"
      ? "Choose a line before re-entry"
      : "Hold the opening thread";

  const resonanceStatus = resonanceActive
    ? `Resonance active for ${Math.ceil(snapshot.resonanceRemaining)} seconds`
    : resonanceRecovering
      ? `Resonance recovering for ${Math.ceil(snapshot.resonanceCooldownRemaining)} seconds`
      : resonanceAvailable
        ? "Resonance stored and ready for manual release"
        : `Resonance charge ${snapshot.resonanceCharge} of 3`;

  return (
    <div
      className={joinClasses(styles.root, leftHanded && styles.leftHanded)}
      data-mode={mode}
      data-arc={snapshot.arc}
      data-phase={displayedPhase}
      data-phase-armed={primedInput.phase ? "true" : "false"}
      data-left-handed={leftHanded ? "true" : "false"}
      data-iris-active={irisIncoming ? "true" : "false"}
      data-resonance={
        resonanceActive ? "active" : resonanceAvailable ? "ready" : "charging"
      }
    >
      <div className={styles.viewport} aria-hidden={modalOpen ? "true" : undefined}>
        {children}
      </div>
      <div className={styles.atmosphere} aria-hidden="true" />

      <div className={styles.chrome} inert={modalOpen ? true : undefined}>
        <header className={styles.header}>
          <button
            type="button"
            className={styles.exitButton}
            onClick={onExit}
            aria-label="Exit Signal Loom"
          >
            <span aria-hidden="true">←</span>
            <span>Exit</span>
          </button>

          <div className={styles.identity} aria-label="Signal Loom, Archive Contract Six">
            <span className={styles.apertureMark} aria-hidden="true"><i /></span>
            <span className={styles.identityCopy}>
              <strong>SIGNAL LOOM</strong>
              <small>ARCHIVE CONTRACT / 06:00</small>
            </span>
          </div>

          <div className={styles.utilityActions}>
            <button
              type="button"
              className={styles.utilityButton}
              onClick={onToggleSound}
              aria-pressed={muted}
              aria-label={muted ? "Turn sound on" : "Turn sound off"}
              title={muted ? "Sound off" : "Sound on"}
            >
              <span aria-hidden="true">{muted ? "S−" : "S+"}</span>
            </button>
            <button
              type="button"
              className={styles.utilityButton}
              onClick={onToggleComfort}
              aria-pressed={comfortMode}
              aria-label={`Comfort camera ${comfortMode ? "on" : "off"}`}
              title={`Comfort camera ${comfortMode ? "on" : "off"}`}
            >
              <span aria-hidden="true">C</span>
            </button>
            {fullscreenAvailable && (
              <button
                type="button"
                className={styles.utilityButton}
                onClick={onToggleFullscreen}
                aria-pressed={fullscreenActive}
                aria-label={fullscreenActive ? "Exit fullscreen" : "Enter fullscreen"}
                title={fullscreenActive ? "Exit fullscreen" : "Enter fullscreen"}
              >
                <span aria-hidden="true">{fullscreenActive ? "□" : "⌗"}</span>
              </button>
            )}
          </div>
        </header>

        {showRunChrome && (
          <main className={styles.runChrome} aria-label="Signal Loom contract status">
            <section className={styles.contractRail} aria-label="Six-minute contract progress">
              <div className={styles.contractHeading}>
                <span>Arc {String(snapshot.arc).padStart(2, "0")}</span>
                <strong>{ARC_LABELS[snapshot.arc]}</strong>
              </div>
              <progress
                className={styles.progressTrack}
                aria-label="Contract completion"
                max={100}
                value={contractPercent}
              />
              <time dateTime={`PT${Math.ceil(snapshot.contractRemaining)}S`}>
                {formatClock(snapshot.contractRemaining)}
              </time>
            </section>

            <section className={styles.scorePlate} aria-label="Current run score">
              <span>Exposure score</span>
              <strong>{formatScore(snapshot.score)}</strong>
              <small>
                {Math.floor(snapshot.distance).toLocaleString("en-CA")} m woven
                {bestScore > 0 ? ` · best ${formatScore(bestScore)}` : ""}
              </small>
            </section>

            <section className={styles.threadPlate} aria-label="Thread state">
              <div className={styles.plateHeading}>
                <span>Thread tension</span>
                <strong>{tensionPercent}%</strong>
              </div>
              <div
                className={styles.tensionTrack}
              >
                <meter
                  aria-label="Thread tension"
                  min={0}
                  max={100}
                  high={78}
                  optimum={35}
                  value={tensionPercent}
                />
                <b aria-hidden="true" />
              </div>
              <div className={styles.threadStats}>
                <span><small>Chain</small><strong>{snapshot.stitchChain}</strong></span>
                <span><small>Length</small><strong>{snapshot.threadLength.toFixed(1)} m</strong></span>
                <span><small>Stitches</small><strong>{snapshot.stitches}</strong></span>
              </div>
            </section>

            <section
              className={styles.encounterPlate}
              aria-label={irisIncoming ? "Approaching Iris aperture" : "Approaching anchor"}
              data-iris={irisIncoming ? snapshot.iris.stage : undefined}
            >
              <p>{irisIncoming ? "Machine aperture" : "Next stitch"}</p>
              {irisIncoming ? (
                <>
                  <div className={styles.encounterTitle}>
                    <strong>Iris aperture</strong>
                    <time>
                      {snapshot.iris.stage === "contact"
                        ? "NOW"
                        : `${irisSecondsToContact.toFixed(1)}s`}
                    </time>
                  </div>
                  <div className={styles.anchorTags}>
                    <span data-route="safe">Needle + Echo</span>
                    <span>Illuminated gap</span>
                    <span>Cycle {snapshot.iris.cycle}</span>
                  </div>
                </>
              ) : activeEncounter ? (
                <>
                  <div className={styles.encounterTitle}>
                    <strong>{ENCOUNTER_LABELS[activeEncounter.kind]}</strong>
                    <time>{Math.max(0, activeEncounter.secondsToContact).toFixed(1)}s</time>
                  </div>
                  <div className={styles.anchorTags}>
                    <span data-route={activeEncounter.route}>
                      {activeEncounter.route === "expressive" ? "Overexposure" : "Safe splice"}
                    </span>
                    <span data-phase-chip={activeEncounter.phase}>
                      <i aria-hidden="true" />
                      {phaseLabel(activeEncounter.phase)}
                    </span>
                    <span>Beat {activeEncounter.beat}</span>
                  </div>
                </>
              ) : (
                <strong className={styles.scanning}>Scanning the next anchor</strong>
              )}
            </section>

            <section className={styles.resonancePlate} aria-label={resonanceStatus}>
              <div className={styles.plateHeading}>
                <span>Stored Resonance</span>
                <strong>{resonanceActive ? "2×" : `${snapshot.resonanceCharge}/3`}</strong>
              </div>
              <div className={styles.resonancePips} aria-hidden="true">
                {RESONANCE_PIPS.map((pip) => (
                  <i
                    key={pip}
                    data-live={pip < snapshot.resonanceCharge ? "true" : "false"}
                  />
                ))}
              </div>
              <small>{resonanceStatus}</small>
              {resonanceAvailable && (
                <button
                  type="button"
                  className={styles.resonanceButton}
                  onClick={onActivateResonance}
                  disabled={!controlsEnabled}
                >
                  <span>Release Resonance</span>
                  <kbd>R</kbd>
                </button>
              )}
            </section>

            <section className={styles.phasePlate} aria-label={phaseControlLabel}>
              <button
                type="button"
                className={styles.phaseButton}
                onClick={onTogglePhase}
                disabled={!controlsEnabled}
                aria-label={phaseControlLabel}
                aria-pressed={Boolean(primedInput.phase)}
              >
                <span className={styles.phaseGlyph} aria-hidden="true"><i /></span>
                <span><small>Phase</small><strong>{phase}</strong></span>
                <kbd>Space</kbd>
              </button>
            </section>

            {isLive && (
              <button type="button" className={styles.pauseButton} onClick={onPause}>
                <span aria-hidden="true">Ⅱ</span>
                <span>Pause</span>
              </button>
            )}

            <div className={styles.desktopLegend} aria-label="Desktop controls">
              <span><kbd>WASD</kbd><small>or drag</small><strong>Steer</strong></span>
              <span><kbd>Shift</kbd><small>hold</small><strong>Reel</strong></span>
              <span><kbd>Space</kbd><small>tap</small><strong>Phase</strong></span>
              <span><kbd>R</kbd><small>when stored</small><strong>Release</strong></span>
            </div>
          </main>
        )}

        {controlsEnabled && (
          <section className={styles.touchControls} aria-label="Touch controls">
            <div className={styles.dpad} aria-label="Directional controls">
              {DIRECTIONS.map(({ direction, label, glyph }) => (
                <button
                  type="button"
                  key={direction}
                  data-direction={direction}
                  aria-label={label}
                  onPointerDown={(event) => beginDirection(event, direction)}
                  onPointerUp={() => endDirection(direction)}
                  onPointerCancel={() => endDirection(direction)}
                  onLostPointerCapture={() => endDirection(direction)}
                  onKeyDown={(event) => directionKey(event, direction, true)}
                  onKeyUp={(event) => directionKey(event, direction, false)}
                  onBlur={() => {
                    suppressDirectionClickRef.current = false;
                    endDirection(direction);
                  }}
                  onClick={(event) => accessibleDirectionClick(event, direction)}
                >
                  <span aria-hidden="true">{glyph}</span>
                </button>
              ))}
            </div>

            <div className={styles.touchActions}>
              <button
                type="button"
                className={styles.touchReel}
                aria-pressed={snapshot.reeling || primedInput.reel}
                aria-label="Reel Thread. Press and hold to shorten and stabilize."
                onPointerDown={beginReel}
                onPointerUp={endReel}
                onPointerCancel={endReel}
                onLostPointerCapture={endReel}
                onKeyDown={(event) => reelKey(event, true)}
                onKeyUp={(event) => reelKey(event, false)}
                onBlur={endReel}
                onClick={(event) => {
                  if (event.detail !== 0) return;
                  if (suppressReelClickRef.current) {
                    suppressReelClickRef.current = false;
                    return;
                  }
                  onSetReel(!snapshot.reeling);
                }}
              >
                <span>Hold</span>
                <strong>REEL</strong>
                <small>{snapshot.reeling || primedInput.reel ? "Thread secured" : "Shorten thread"}</small>
                <meter
                  className={styles.touchTension}
                  aria-label={`Thread tension ${tensionPercent} percent`}
                  min={0}
                  max={100}
                  high={78}
                  optimum={35}
                  value={tensionPercent}
                />
              </button>
              <button
                type="button"
                className={styles.touchPhase}
                onClick={onTogglePhase}
                aria-pressed={Boolean(primedInput.phase)}
                aria-label={phaseControlLabel}
              >
                <span className={styles.phaseGlyph} aria-hidden="true"><i /></span>
                <strong>PHASE</strong>
                <small>{phase}</small>
                <span className={styles.touchCharge} aria-hidden="true">
                  <b>{compactResonance}</b>
                  {!resonanceActive && !resonanceRecovering &&
                    RESONANCE_PIPS.map((pip) => (
                      <i
                        key={pip}
                        data-live={pip < snapshot.resonanceCharge ? "true" : "false"}
                      />
                    ))}
                </span>
              </button>
              {resonanceAvailable && (
                <button
                  type="button"
                  className={styles.touchResonance}
                  onClick={onActivateResonance}
                  aria-pressed={primedInput.resonance}
                >
                  <span>Stored</span>
                  <strong>RELEASE</strong>
                  <small>Resonance 2×</small>
                </button>
              )}
            </div>
            <p className={styles.dragHint}>Drag the field for analog steering</p>
          </section>
        )}
      </div>

      {mode === "idle" && !error && (
        <section className={styles.intro} aria-labelledby="loom-title">
          <div className={styles.introIndex} aria-hidden="true">A / 06</div>
          <div className={styles.introCopy}>
            <p>Archive contract 01</p>
            <h1 id="loom-title"><span>Signal</span> Loom</h1>
            <strong className={styles.tagline}>Draw light through a machine that remembers.</strong>
            <p className={styles.story}>
              Guide the Needle. Tow its Echo through opposing anchors. Hold Reel for
              control, extend the Thread for exposure, and choose when to release the
              Resonance you have earned.
            </p>
            <button
              type="button"
              className={styles.primaryAction}
              onClick={onBegin}
              disabled={!ready}
            >
              <span>{ready ? "Begin six-minute contract" : "Preparing the Loom"}</span>
              <i aria-hidden="true">→</i>
            </button>
          </div>
          <aside className={styles.contractBrief} aria-label="Contract brief">
            <p>One contract. Four movements.</p>
            <ol>
              <li><span>01</span><strong>Threading</strong><small>Learn the line</small></li>
              <li><span>02</span><strong>Refraction</strong><small>Choose exposure</small></li>
              <li><span>03</span><strong>Iris</strong><small>Hold the machine</small></li>
              <li><span>04</span><strong>Extraction</strong><small>Bank the archive</small></li>
            </ol>
            <div className={styles.briefRules}>
              <span><i data-phase-swatch="ember" />Ember</span>
              <span><i data-phase-swatch="cobalt" />Cobalt</span>
              <span>Safe line or overexposure</span>
            </div>
            <div className={styles.archiveRecord}>
              <span>Personal archive record</span>
              <strong>{bestScore > 0 ? formatScore(bestScore) : "Unbanked"}</strong>
            </div>
          </aside>
        </section>
      )}

      {eventNotice && isLive && !error && (
        <aside
          key={eventNotice.id}
          className={styles.eventNotice}
          data-tone={eventNotice.tone}
          aria-hidden="true"
        >
          <span>{eventNotice.eyebrow}</span>
          <strong>{eventNotice.title}</strong>
          <small>{eventNotice.detail}</small>
        </aside>
      )}

      {isStaging && !error && (
        <section
          className={styles.countdown}
          role="status"
          aria-live="assertive"
          aria-atomic="true"
          aria-label={`${mode === "resuming" ? "Contract resumes" : "Contract begins"} in ${countdown}`}
        >
          <span>{mode === "resuming" ? "Thread reacquiring" : "Needle synchronized"}</span>
          <strong key={countdown}>{countdown}</strong>
          <small>{stagedStatus}</small>
          <div className={styles.countdownLine} aria-hidden="true"><i /></div>
        </section>
      )}

      {mode === "paused" && !error && (
        <section
          ref={dialogRef}
          className={styles.modal}
          role="dialog"
          aria-modal="true"
          aria-labelledby="loom-pause-title"
          tabIndex={-1}
          onKeyDown={keepDialogFocus}
        >
          <div className={styles.modalCard}>
            <p>Thread held / {formatClock(snapshot.contractRemaining)} remains</p>
            <h2 id="loom-pause-title">Contract suspended</h2>
            <p>Your exact score, anchor state, and stored Resonance are held.</p>
            <dl className={styles.pauseStats}>
              <div><dt>Score</dt><dd>{formatScore(snapshot.score)}</dd></div>
              <div><dt>Chain</dt><dd>{snapshot.stitchChain}</dd></div>
              <div><dt>Tension</dt><dd>{tensionPercent}%</dd></div>
            </dl>
            <div className={styles.modalActions}>
              <button type="button" className={styles.primaryAction} onClick={onResume}>
                <span>Resume contract</span><i aria-hidden="true">→</i>
              </button>
              <button type="button" className={styles.secondaryAction} onClick={onEnd}>
                End and extract
              </button>
            </div>
          </div>
        </section>
      )}

      {isResult && !error && (
        <section
          ref={dialogRef}
          className={styles.modal}
          role="dialog"
          aria-modal="true"
          aria-labelledby="loom-result-title"
          tabIndex={-1}
          onKeyDown={keepDialogFocus}
        >
          <div className={joinClasses(styles.modalCard, styles.resultCard)}>
            <p>
              {isNewBest
                ? "New archive record / personal best"
                : extraction
                  ? "Archive secured / six-minute contract"
                  : "Contract closed / archive banked"}
            </p>
            <h2 id="loom-result-title">
              {snapshot.stitches > 0 ? "The Thread holds." : "The archive remains dark."}
            </h2>
            <p>
              {snapshot.stitches === 0
                ? "No anchor was woven. Hold Reel through the opening splice, then steer the Thread across each signal anchor."
                : snapshot.expressiveStitches > snapshot.safeStitches
                ? "You chose exposure and carried the Echo through the wider line."
                : "You protected the line and brought the archive home intact."}
            </p>
            <dl className={styles.resultGrid}>
              <div><dt>Exposure score</dt><dd>{formatScore(extraction?.finalScore ?? snapshot.score)}</dd></div>
              <div><dt>Archive record</dt><dd data-new-record={isNewBest ? "true" : "false"}>{formatScore(bestScore)}</dd></div>
              <div><dt>Stitches</dt><dd>{snapshot.stitches}</dd></div>
              <div><dt>Expressive</dt><dd>{snapshot.expressiveStitches}</dd></div>
              <div><dt>Best chain</dt><dd>{snapshot.bestStitchChain}</dd></div>
              <div><dt>Near passes</dt><dd>{snapshot.nearMisses}</dd></div>
              <div><dt>Thread breaks</dt><dd>{snapshot.threadBreaks}</dd></div>
              <div><dt>Releases</dt><dd>{snapshot.resonanceActivations}</dd></div>
            </dl>
            <div className={styles.modalActions}>
              <button type="button" className={styles.primaryAction} onClick={onBegin}>
                <span>Weave another contract</span><i aria-hidden="true">→</i>
              </button>
              <button type="button" className={styles.secondaryAction} onClick={onExit}>
                Return to {brand.short_name}
              </button>
            </div>
          </div>
        </section>
      )}

      {error && (
        <section
          ref={dialogRef}
          className={styles.modal}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="loom-error-title"
          aria-describedby="loom-error-copy"
          tabIndex={-1}
          onKeyDown={keepDialogFocus}
        >
          <div className={styles.modalCard}>
            <p>Projection interrupted</p>
            <h2 id="loom-error-title">The Loom could not open.</h2>
            <p id="loom-error-copy">{error}</p>
            <div className={styles.modalActions}>
              <button type="button" className={styles.secondaryAction} onClick={onExit}>
                Return to {brand.short_name}
              </button>
            </div>
          </div>
        </section>
      )}

      <p className={styles.liveRegion} role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>
    </div>
  );
}

export default LoomInterface;
