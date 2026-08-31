"use client";

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import styles from "./ball-interface.module.css";
import { useSiteBrand } from "@/app/components/site-brand-provider";

export type BallGameMode =
  | "idle"
  | "countdown"
  | "resuming"
  | "running"
  | "paused"
  | "crashed"
  | "extracted";

export type BallGameStatus = "running" | "crashed" | "extracted";

export interface BallGameSnapshot {
  score: number;
  distance: number;
  contractRemaining: number;
  speed: number;
  pace: number | string;
  integrity: number;
  combo: number;
  gatesCleared: number;
  nearMisses: number;
  impacts: number;
  overdriveCharge: number;
  overdriveRemaining: number;
  status: BallGameStatus;
}

export interface BallInterfaceProps {
  snapshot: BallGameSnapshot;
  mode: BallGameMode;
  ready: boolean;
  bestScore: number;
  isNewBest?: boolean;
  countdown?: number;
  announcement?: string;
  muted: boolean;
  comfortMode: boolean;
  assistMode: boolean;
  primedDirection?: string | null;
  children?: ReactNode;
  onPlay(): void;
  onPause(): void;
  onResume(): void;
  onRestart(): void;
  onExit(): void;
  onToggleMuted(): void;
  onToggleComfort(): void;
  onToggleAssist(): void;
}

const SHIELDS = [0, 1, 2] as const;
const OVERDRIVE_STEPS = [0, 1, 2, 3] as const;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function formatScore(value: number): string {
  return Math.max(0, Math.floor(Number.isFinite(value) ? value : 0)).toLocaleString(
    "en-CA",
  );
}

function formatDistance(value: number): string {
  return `${Math.max(0, Math.floor(Number.isFinite(value) ? value : 0)).toLocaleString(
    "en-CA",
  )} m`;
}

function formatRemaining(value: number): string {
  const seconds = Math.max(0, Math.ceil(Number.isFinite(value) ? value : 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function paceLabel(value: number | string): string {
  if (typeof value === "string") return value;
  return (["Calm", "Flow", "Rush", "Redline"] as const)[
    clamp(Math.round(value), 1, 4) - 1
  ];
}

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute("hidden"));
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M5 12h13M13 6l6 6-6 6" />
    </svg>
  );
}

function BackIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="m11 5-7 7 7 7M4 12h16" />
    </svg>
  );
}

interface OptionButtonsProps {
  muted: boolean;
  comfortMode: boolean;
  assistMode: boolean;
  onToggleMuted(): void;
  onToggleComfort(): void;
  onToggleAssist(): void;
}

function OptionButtons({
  muted,
  comfortMode,
  assistMode,
  onToggleMuted,
  onToggleComfort,
  onToggleAssist,
}: OptionButtonsProps) {
  return (
    <div className={styles.optionButtons} aria-label="Game options">
      <button
        type="button"
        className={styles.optionButton}
        onClick={onToggleMuted}
        aria-pressed={muted}
        aria-label={muted ? "Turn sound on" : "Turn sound off"}
      >
        <span>Sound</span>
        <strong>{muted ? "Off" : "On"}</strong>
      </button>
      <button
        type="button"
        className={styles.optionButton}
        onClick={onToggleComfort}
        aria-pressed={comfortMode}
        aria-label={`Steady camera ${comfortMode ? "on" : "off"}`}
      >
        <span>Steady camera</span>
        <strong>{comfortMode ? "On" : "Off"}</strong>
      </button>
      <button
        type="button"
        className={styles.optionButton}
        onClick={onToggleAssist}
        aria-pressed={assistMode}
        aria-label={`Assist mode ${assistMode ? "on" : "off"}`}
      >
        <span>Assist</span>
        <strong>{assistMode ? "On" : "Off"}</strong>
      </button>
    </div>
  );
}

export function BallInterface({
  snapshot,
  mode,
  ready,
  bestScore,
  isNewBest = false,
  countdown = 3,
  announcement = "",
  muted,
  comfortMode,
  assistMode,
  primedDirection = null,
  children,
  onPlay,
  onPause,
  onResume,
  onRestart,
  onExit,
  onToggleMuted,
  onToggleComfort,
  onToggleAssist,
}: BallInterfaceProps) {
  const brand = useSiteBrand();
  const dialogRef = useRef<HTMLElement>(null);
  const primaryDialogActionRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const previousPaceRef = useRef(snapshot.pace);
  const paceTimerRef = useRef<number | null>(null);
  const [showPace, setShowPace] = useState(false);

  const modalOpen = mode === "paused" || mode === "crashed" || mode === "extracted";
  const staging = mode === "countdown" || mode === "resuming";
  const showHud = mode !== "idle" && mode !== "crashed" && mode !== "extracted";
  const overdriveActive = snapshot.overdriveRemaining > 0;
  const score = formatScore(snapshot.score);
  const safeBest = Math.max(bestScore, snapshot.score);
  const shieldCount = clamp(Math.floor(snapshot.integrity), 0, SHIELDS.length);
  const overdriveCharge = clamp(
    Math.floor(snapshot.overdriveCharge),
    0,
    OVERDRIVE_STEPS.length,
  );
  const currentPace = paceLabel(snapshot.pace);
  const remainingSeconds = Math.max(0, snapshot.contractRemaining);
  const remainingLabel = formatRemaining(remainingSeconds);
  const finishUrgent = remainingSeconds > 0 && remainingSeconds <= 15;

  useEffect(() => {
    const paceChanged = previousPaceRef.current !== snapshot.pace;
    previousPaceRef.current = snapshot.pace;

    if (paceTimerRef.current !== null) {
      window.clearTimeout(paceTimerRef.current);
      paceTimerRef.current = null;
    }

    if (mode !== "running" || (!paceChanged && !showPace)) return;
    setShowPace(true);
    paceTimerRef.current = window.setTimeout(() => {
      paceTimerRef.current = null;
      setShowPace(false);
    }, 2_400);

    return () => {
      if (paceTimerRef.current !== null) {
        window.clearTimeout(paceTimerRef.current);
        paceTimerRef.current = null;
      }
    };
  }, [mode, showPace, snapshot.pace]);

  useEffect(() => {
    if (!modalOpen) return;
    returnFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      primaryDialogActionRef.current?.focus({ preventScroll: true });
    });
    return () => {
      window.cancelAnimationFrame(frame);
      returnFocusRef.current?.focus({ preventScroll: true });
    };
  }, [modalOpen, mode]);

  useEffect(() => () => {
    if (paceTimerRef.current !== null) window.clearTimeout(paceTimerRef.current);
  }, []);

  const keepDialogFocus = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape" && mode === "paused") {
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

  const options = (
    <OptionButtons
      muted={muted}
      comfortMode={comfortMode}
      assistMode={assistMode}
      onToggleMuted={onToggleMuted}
      onToggleComfort={onToggleComfort}
      onToggleAssist={onToggleAssist}
    />
  );

  return (
    <div
      className={styles.root}
      data-mode={mode}
      data-pace={String(snapshot.pace)}
      data-assist={assistMode ? "true" : "false"}
      data-comfort={comfortMode ? "true" : "false"}
    >
      <div className={styles.viewport} inert={modalOpen ? true : undefined}>
        {children}
      </div>
      <div className={styles.atmosphere} aria-hidden="true" />

      <div className={styles.chrome} inert={modalOpen ? true : undefined}>
        {mode === "idle" && (
          <header className={styles.introHeader}>
            <button type="button" className={styles.exitButton} onClick={onExit}>
              <BackIcon />
              <span>Exit game</span>
            </button>
            <div className={styles.wordmark} aria-label={`${brand.business_name} interactive`}>
              <span aria-hidden="true"><i /></span>
              <strong>{brand.short_name}</strong>
              <small>INTERACTIVE</small>
            </div>
          </header>
        )}

        {showHud && (
          <header className={styles.hud} aria-label="Signal Run status">
            <section
              className={styles.shields}
              aria-label={`Shields ${shieldCount} of ${SHIELDS.length}`}
            >
              <span>Shields</span>
              <div aria-hidden="true">
                {SHIELDS.map((shield) => (
                  <i key={shield} data-active={shield < shieldCount ? "true" : "false"} />
                ))}
              </div>
            </section>

            <section className={styles.score}>
              <div className={styles.scoreLabels}>
                <span>Score</span>
                <time
                  className={styles.finishClock}
                  dateTime={`PT${Math.ceil(remainingSeconds)}S`}
                  data-urgent={finishUrgent ? "true" : "false"}
                  aria-label={`${Math.ceil(remainingSeconds)} seconds to finish`}
                >
                  <small>Finish</small>
                  <strong>{remainingLabel}</strong>
                </time>
              </div>
              <output aria-label={`Score ${score}`}>{score}</output>
              <div className={styles.scoreMeta}>
                {snapshot.combo > 1 && (
                  <strong data-active="true">{snapshot.combo}x combo</strong>
                )}
                {!overdriveActive && (
                  <span
                    className={styles.overdrivePips}
                    aria-label={`Overdrive charge ${overdriveCharge} of ${OVERDRIVE_STEPS.length}`}
                  >
                    {OVERDRIVE_STEPS.map((step) => (
                      <i
                        key={step}
                        aria-hidden="true"
                        data-active={step < overdriveCharge ? "true" : "false"}
                      />
                    ))}
                  </span>
                )}
              </div>
            </section>

            {mode === "running" ? (
              <button
                type="button"
                className={styles.pauseButton}
                onClick={onPause}
                aria-label="Pause game"
              >
                <span className={styles.pauseIcon} aria-hidden="true"><i /><i /></span>
                <strong>Pause</strong>
              </button>
            ) : (
              <span className={styles.hudBalance} aria-hidden="true" />
            )}
          </header>
        )}

        {(showPace || overdriveActive) && mode === "running" && (
          <aside
            className={styles.paceNotice}
            data-overdrive={overdriveActive ? "true" : "false"}
            aria-hidden="true"
          >
            <span>{overdriveActive ? "Overdrive" : "Pace up"}</span>
            <strong>
              {overdriveActive
                ? `2x / ${snapshot.overdriveRemaining.toFixed(1)}s`
                : currentPace}
            </strong>
            <small>{Math.max(0, Math.round(snapshot.speed))} km/h</small>
          </aside>
        )}
      </div>

      {mode === "idle" && (
        <main className={styles.intro} aria-labelledby="signal-run-title">
          <div className={styles.heroStage} aria-hidden="true">
            <div className={styles.heroOrbit}><i /><i /><i /></div>
            <div className={styles.heroBall}><i /></div>
            <div className={styles.heroTrail} />
          </div>

          <section className={styles.introCopy}>
            <p className={styles.eyebrow}>A kinetic {brand.short_name} experiment</p>
            <h1 id="signal-run-title">Signal Run</h1>
            <p className={styles.promise}>
              Move the ball. Fly through light. Avoid solid shapes.
            </p>
            <p id="signal-run-controls" className={styles.controlHint}>
              <span className={styles.desktopHint}>WASD or arrow keys to move</span>
              <span className={styles.touchHint}>Drag anywhere to move</span>
            </p>
            <button
              type="button"
              className={styles.primaryAction}
              onClick={onPlay}
              disabled={!ready}
              aria-label="Play Signal Run"
            >
              <span>{ready ? "Play Signal Run" : "Preparing Signal Run"}</span>
              <ArrowIcon />
            </button>
            {options}
          </section>
        </main>
      )}

      {staging && (
        <section className={styles.countdown} aria-label="Run starting">
          <div className={styles.countdownBall} aria-hidden="true"><i /></div>
          <p>{mode === "resuming" ? "Back in" : "Ready"}</p>
          <strong aria-hidden="true">{Math.max(1, Math.ceil(countdown))}</strong>
          <small>
            {primedDirection ? `${primedDirection} ready` : "Choose your line"}
          </small>
          <span className={styles.countdownControl}>
            <i className={styles.desktopHint}>WASD / arrows</i>
            <i className={styles.touchHint}>Drag to move</i>
          </span>
        </section>
      )}

      {mode === "paused" && (
        <section
          ref={dialogRef}
          className={styles.modal}
          role="dialog"
          aria-modal="true"
          aria-labelledby="ball-pause-title"
          aria-describedby="ball-pause-description"
          tabIndex={-1}
          onKeyDown={keepDialogFocus}
        >
          <div className={styles.modalCard}>
            <div className={styles.modalLead}>
              <p className={styles.eyebrow}>Run paused</p>
              <h2 id="ball-pause-title">Take a breath.</h2>
              <p id="ball-pause-description">
                Your score and exact position are safe.
              </p>
              <div className={styles.pauseReadout} aria-label="Current run">
                <span><small>Score</small><strong>{score}</strong></span>
                <span><small>Distance</small><strong>{formatDistance(snapshot.distance)}</strong></span>
                <span><small>Finish</small><strong>{remainingLabel}</strong></span>
              </div>
            </div>
            <div className={styles.dialogOptions}>{options}</div>
            <div className={styles.modalActions}>
              <button
                ref={primaryDialogActionRef}
                type="button"
                className={styles.primaryAction}
                onClick={onResume}
              >
                <span>Resume game</span>
                <ArrowIcon />
              </button>
              <button type="button" className={styles.secondaryAction} onClick={onRestart}>
                Restart run
              </button>
              <button type="button" className={styles.textAction} onClick={onExit}>
                Exit game
              </button>
            </div>
          </div>
        </section>
      )}

      {(mode === "crashed" || mode === "extracted") && (
        <section
          ref={dialogRef}
          className={styles.modal}
          role="dialog"
          aria-modal="true"
          aria-labelledby="ball-result-title"
          aria-describedby="ball-result-description"
          tabIndex={-1}
          onKeyDown={keepDialogFocus}
        >
          <div
            className={`${styles.modalCard} ${styles.resultCard}`}
            data-result={mode}
          >
            <div className={styles.modalLead}>
              <p className={styles.eyebrow}>
                {mode === "extracted"
                  ? isNewBest ? "Run cleared / New personal best" : "Run cleared"
                  : isNewBest ? "New personal best" : "Run over"}
              </p>
              <h2 id="ball-result-title">
                {mode === "extracted"
                  ? "You made it through."
                  : isNewBest
                    ? "You found the flow."
                    : "Ready for another line?"}
              </h2>
              <p id="ball-result-description">
                {mode === "extracted"
                  ? "You held the line from calm launch to the final rush."
                  : "Every run starts calm, then asks you to hold on a little longer."}
              </p>
            </div>

            <dl className={styles.resultStats}>
              <div className={styles.resultScore}>
                <dt>Score</dt>
                <dd>{score}</dd>
              </div>
              <div>
                <dt>Best</dt>
                <dd>{formatScore(safeBest)}</dd>
              </div>
              <div>
                <dt>Distance</dt>
                <dd>{formatDistance(snapshot.distance)}</dd>
              </div>
              <div>
                <dt>Gates</dt>
                <dd>{Math.max(0, Math.floor(snapshot.gatesCleared))}</dd>
              </div>
            </dl>

            <div className={styles.modalActions}>
              <button
                ref={primaryDialogActionRef}
                type="button"
                className={styles.primaryAction}
                onClick={onRestart}
              >
                <span>{mode === "extracted" ? "Run it again" : "Play again"}</span>
                <ArrowIcon />
              </button>
              <button type="button" className={styles.secondaryAction} onClick={onExit}>
                Exit game
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

export default BallInterface;
