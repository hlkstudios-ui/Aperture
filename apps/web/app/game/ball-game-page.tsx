'use client';

import { useRouter } from 'next/navigation';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import BallInterface from './ball-interface';
import styles from './ball-interface.module.css';
import {
  commitBestScore,
  readBestScore,
} from './best-score';
import type {
  BallGameEngineOptions,
  BallGameSnapshot,
  BallPrimedInputFeedback,
  BallRunMode,
} from './ball-game-types';
import {
  BALL_CONTRACT_DURATION_SECONDS,
  createBallSimulation,
  type BallGateEvent,
  type BallImpactEvent,
  type BallPace,
  type BallSimulation,
} from './ball-simulation';
import type { BallGameEngine } from './ball-game-engine';

export const SIGNAL_RUN_BALL_BEST_KEY = 'signal-run-ball-best-v2';

const MOVEMENT_KEYS = new Set([
  'ArrowLeft',
  'ArrowRight',
  'ArrowUp',
  'ArrowDown',
  'KeyA',
  'KeyD',
  'KeyW',
  'KeyS',
]);

const INITIAL_PRIMED_INPUT: BallPrimedInputFeedback = { direction: null };

function snapshotFromSimulation(simulation: Readonly<BallSimulation>): BallGameSnapshot {
  return {
    status: simulation.status,
    score: Math.max(0, Math.floor(simulation.score)),
    exactScore: Math.max(0, simulation.score),
    distance: Math.max(0, simulation.distance),
    elapsed: Math.max(0, simulation.elapsed),
    contractRemaining: Math.max(
      0,
      BALL_CONTRACT_DURATION_SECONDS - simulation.elapsed,
    ),
    speed: Math.max(0, simulation.speed),
    pace: simulation.pace,
    integrity: Math.max(0, simulation.shields),
    combo: Math.max(1, simulation.combo),
    ball: {
      x: simulation.ball.position.x,
      y: simulation.ball.position.y,
    },
    gatesCleared: simulation.cleanGates,
    nearMisses: simulation.nearMisses,
    impacts: simulation.impacts,
    overdriveCharge: simulation.overdriveCharge,
    overdriveRemaining: simulation.overdriveRemaining,
    overdriveActivations: simulation.overdriveActivations,
  };
}

const INITIAL_SNAPSHOT = snapshotFromSimulation(
  createBallSimulation('signal-run-ball-intro'),
);

function availableStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function pulseHaptic(pattern: number | number[]): void {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    // Haptics are optional and commonly unavailable on desktop browsers.
  }
}

function runSeed(): number {
  let entropy = Math.floor(Math.random() * 0xffffffff) >>> 0;
  try {
    const values = new Uint32Array(1);
    crypto.getRandomValues(values);
    entropy ^= values[0] ?? 0;
  } catch {
    // Math.random still keeps retries visually varied in restricted contexts.
  }
  return ((Date.now() >>> 0) ^ entropy) >>> 0;
}

function paceName(pace: BallPace): string {
  return ['Calm', 'Flow', 'Rush', 'Redline'][pace - 1] ?? 'Flow';
}

function impactAnnouncement(event: Readonly<BallImpactEvent>): string {
  if (event.crashed) return 'Run over.';
  const noun = event.shieldsRemaining === 1 ? 'shield' : 'shields';
  return `Impact. ${event.shieldsRemaining} ${noun} remaining.`;
}

function gateAnnouncement(event: Readonly<BallGateEvent>): string | null {
  if (event.overdriveStarted) return null;
  // A clipped gate also emits the authoritative impact event. Keep its shield
  // warning audible instead of immediately replacing it with a softer cue.
  if (event.result === 'clipped') return null;
  if (event.sequence === 1) return 'First gate clear. Keep moving.';
  return null;
}

const FINISH_ANNOUNCEMENT_SECONDS = [15, 10, 5, 3, 2, 1] as const;

function finishAnnouncement(seconds: number): string {
  if (seconds === 15) return 'Final rush. 15 seconds to finish.';
  return `${seconds} ${seconds === 1 ? 'second' : 'seconds'} to finish.`;
}

export default function BallGamePage() {
  const router = useRouter();
  const canvasHostRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<BallGameEngine | null>(null);
  const modeRef = useRef<BallRunMode>('idle');
  const readyRef = useRef(false);
  const countdownTimersRef = useRef<number[]>([]);
  const bestScoreRef = useRef(0);
  const mutedRef = useRef(false);
  const comfortModeRef = useRef(false);
  const assistModeRef = useRef(false);
  const lastComboAnnouncementRef = useRef(1);
  const announcedFinishSecondsRef = useRef(new Set<number>());
  const lastSnapshotSignalsRef = useRef({
    impacts: INITIAL_SNAPSHOT.impacts,
    gatesCleared: INITIAL_SNAPSHOT.gatesCleared,
    overdriveActivations: INITIAL_SNAPSHOT.overdriveActivations,
    pace: INITIAL_SNAPSHOT.pace,
  });

  const [mode, setMode] = useState<BallRunMode>('idle');
  const [snapshot, setSnapshot] = useState<BallGameSnapshot>(INITIAL_SNAPSHOT);
  const [countdown, setCountdown] = useState(3);
  const [ready, setReady] = useState(false);
  const [bestScore, setBestScore] = useState(0);
  const [runWasNewBest, setRunWasNewBest] = useState(false);
  const [muted, setMuted] = useState(false);
  const [comfortMode, setComfortMode] = useState(false);
  const [assistMode, setAssistMode] = useState(false);
  const [primedInput, setPrimedInput] = useState<BallPrimedInputFeedback>(
    INITIAL_PRIMED_INPUT,
  );
  const [announcement, setAnnouncement] = useState('Signal Run is preparing.');

  const changeMode = useCallback((next: BallRunMode) => {
    modeRef.current = next;
    setMode(next);
  }, []);

  const clearCountdown = useCallback(() => {
    countdownTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    countdownTimersRef.current = [];
  }, []);

  const clearInput = useCallback(() => {
    engineRef.current?.releaseInput();
    setPrimedInput(INITIAL_PRIMED_INPUT);
  }, []);

  const persistScore = useCallback((candidate: number): number => {
    const nextBest = commitBestScore(
      availableStorage(),
      candidate,
      bestScoreRef.current,
      SIGNAL_RUN_BALL_BEST_KEY,
    );
    bestScoreRef.current = nextBest;
    setBestScore(nextBest);
    return nextBest;
  }, []);

  const ensureAudio = useCallback((engine = engineRef.current) => {
    if (!engine) return;
    void engine.unlockAudio().then((available: boolean) => {
      if (available || engineRef.current !== engine) return;
      mutedRef.current = true;
      setMuted(true);
      engine.setMuted(true);
      setAnnouncement('Sound is unavailable. Signal Run remains fully playable.');
    });
  }, []);

  const beginRun = useCallback(() => {
    const engine = engineRef.current;
    if (!engine || !readyRef.current || modeRef.current === 'countdown') return;

    clearCountdown();
    clearInput();
    ensureAudio(engine);
    lastComboAnnouncementRef.current = 1;
    announcedFinishSecondsRef.current.clear();
    setRunWasNewBest(false);
    engine.prepareRun(runSeed(), { assistMode: assistModeRef.current });
    engine.primeInput();
    setCountdown(3);
    setAnnouncement('Run starting. Choose your line.');
    changeMode('countdown');

    countdownTimersRef.current = [
      window.setTimeout(() => setCountdown(2), 650),
      window.setTimeout(() => setCountdown(1), 1_300),
      window.setTimeout(() => {
        if (modeRef.current !== 'countdown') return;
        changeMode('running');
        engine.start();
        setAnnouncement('Go. Fly through the light.');
      }, 1_950),
    ];
  }, [changeMode, clearCountdown, clearInput, ensureAudio]);

  const pauseRun = useCallback(() => {
    if (modeRef.current !== 'running') return;
    clearCountdown();
    clearInput();
    engineRef.current?.pause();
    changeMode('paused');
    setAnnouncement('Game paused.');
  }, [changeMode, clearCountdown, clearInput]);

  const resumeRun = useCallback(() => {
    if (modeRef.current !== 'paused') return;
    const engine = engineRef.current;
    if (!engine) return;

    clearCountdown();
    clearInput();
    engine.primeInput();
    setCountdown(2);
    setAnnouncement('Run resuming. Choose your line.');
    changeMode('resuming');
    countdownTimersRef.current = [
      window.setTimeout(() => setCountdown(1), 420),
      window.setTimeout(() => {
        if (modeRef.current !== 'resuming') return;
        changeMode('running');
        engine.start();
        setAnnouncement('Back in motion.');
      }, 840),
    ];
  }, [changeMode, clearCountdown, clearInput]);

  const interruptRun = useCallback(() => {
    const current = modeRef.current;
    clearInput();
    if (current === 'running') {
      pauseRun();
      return;
    }
    if (current === 'countdown') {
      clearCountdown();
      engineRef.current?.pause();
      setCountdown(3);
      changeMode('idle');
      setAnnouncement('Start cancelled while the game was out of focus.');
      return;
    }
    if (current === 'resuming') {
      clearCountdown();
      engineRef.current?.pause();
      setCountdown(2);
      changeMode('paused');
      setAnnouncement('Game paused.');
    }
  }, [changeMode, clearCountdown, clearInput, pauseRun]);

  const exitGame = useCallback(() => {
    clearCountdown();
    clearInput();
    const engine = engineRef.current;
    if (engine) {
      if (modeRef.current !== 'idle') {
        const current = engine.getSnapshot();
        if (current.score > 0) persistScore(current.score);
      }
      engine.pause();
    }
    router.push('/');
  }, [clearCountdown, clearInput, persistScore, router]);

  useEffect(() => {
    document.documentElement.classList.add('signal-run-ball-open');
    document.body.classList.add('signal-run-ball-open');
    const footer = document.querySelector<HTMLElement>('body > footer, body footer');
    const footerWasInert = footer?.hasAttribute('inert') ?? false;
    const previousFooterAriaHidden = footer?.getAttribute('aria-hidden');
    footer?.setAttribute('inert', '');
    footer?.setAttribute('aria-hidden', 'true');

    return () => {
      document.documentElement.classList.remove('signal-run-ball-open');
      document.body.classList.remove('signal-run-ball-open');
      if (!footerWasInert) footer?.removeAttribute('inert');
      if (previousFooterAriaHidden === null) footer?.removeAttribute('aria-hidden');
      else if (previousFooterAriaHidden !== undefined) {
        footer?.setAttribute('aria-hidden', previousFooterAriaHidden);
      }
    };
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const stored = readBestScore(availableStorage(), SIGNAL_RUN_BALL_BEST_KEY);
      bestScoreRef.current = stored;
      setBestScore(stored);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    const host = canvasHostRef.current;
    if (!host) return;
    let cancelled = false;
    let localEngine: BallGameEngine | null = null;

    const options: BallGameEngineOptions = {
      onReady: () => {
        if (cancelled) return;
        readyRef.current = true;
        setReady(true);
        setAnnouncement('Signal Run ready.');
      },
      onSnapshot: (current) => {
        if (cancelled) return;
        setSnapshot(current);
        const previousSignals = lastSnapshotSignalsRef.current;
        const gameplayCuePending =
          current.impacts > previousSignals.impacts ||
          current.gatesCleared > previousSignals.gatesCleared ||
          current.overdriveActivations > previousSignals.overdriveActivations ||
          current.pace !== previousSignals.pace;
        lastSnapshotSignalsRef.current = {
          impacts: current.impacts,
          gatesCleared: current.gatesCleared,
          overdriveActivations: current.overdriveActivations,
          pace: current.pace,
        };
        if (current.status !== 'running') return;
        // A gameplay cue from this frame speaks first. The unmarked countdown
        // threshold is picked up by the next 10 Hz snapshot, so neither message
        // is lost or repeated every frame.
        if (gameplayCuePending) return;
        let newestThreshold: number | null = null;
        for (const threshold of FINISH_ANNOUNCEMENT_SECONDS) {
          if (
            current.contractRemaining <= threshold &&
            !announcedFinishSecondsRef.current.has(threshold)
          ) {
            announcedFinishSecondsRef.current.add(threshold);
            newestThreshold = threshold;
          }
        }
        if (newestThreshold !== null) {
          setAnnouncement(finishAnnouncement(newestThreshold));
        }
      },
      onImpact: (event, current) => {
        if (cancelled) return;
        setSnapshot(current);
        lastComboAnnouncementRef.current = 1;
        pulseHaptic(event.crashed ? [62, 28, 92] : [38, 20, 52]);
        if (!event.crashed) setAnnouncement(impactAnnouncement(event));
      },
      onGate: (event, current) => {
        if (cancelled) return;
        setSnapshot(current);
        // A clipped gate also emits the authoritative impact event. Let that
        // single, heavier cue own the mistake instead of stacking two haptics.
        if (event.result === 'clean') pulseHaptic(8);
        const directAnnouncement = gateAnnouncement(event);
        if (directAnnouncement) {
          setAnnouncement(directAnnouncement);
          return;
        }
        const wholeCombo = Math.floor(event.combo);
        if (
          !event.overdriveStarted &&
          wholeCombo >= 2 &&
          wholeCombo > lastComboAnnouncementRef.current &&
          Math.abs(event.combo - wholeCombo) < 0.001
        ) {
          lastComboAnnouncementRef.current = wholeCombo;
          setAnnouncement(`${wholeCombo} times combo.`);
        }
      },
      onPace: (pace) => {
        if (cancelled) return;
        pulseHaptic([10, 14, 20]);
        setAnnouncement(`${paceName(pace)} pace. The tunnel is accelerating.`);
      },
      onOverdrive: (current) => {
        if (cancelled) return;
        setSnapshot(current);
        pulseHaptic([10, 16, 18, 16, 44]);
        setAnnouncement('Overdrive. Double score for five seconds.');
      },
      onCrash: (current) => {
        if (cancelled) return;
        clearCountdown();
        engineRef.current?.releaseInput();
        setPrimedInput(INITIAL_PRIMED_INPUT);
        setSnapshot(current);
        setRunWasNewBest(
          current.score > 0 && current.score > bestScoreRef.current,
        );
        persistScore(current.score);
        changeMode('crashed');
        setAnnouncement(`Run over. Score ${current.score.toLocaleString('en-CA')}.`);
      },
      onExtract: (current) => {
        if (cancelled) return;
        clearCountdown();
        engineRef.current?.releaseInput();
        setPrimedInput(INITIAL_PRIMED_INPUT);
        setSnapshot(current);
        setRunWasNewBest(
          current.score > 0 && current.score > bestScoreRef.current,
        );
        persistScore(current.score);
        changeMode('extracted');
        pulseHaptic([18, 18, 28, 18, 72]);
        setAnnouncement(
          `Run cleared. Score ${current.score.toLocaleString('en-CA')}.`,
        );
      },
      onPrimedInput: (feedback) => {
        if (!cancelled) setPrimedInput(feedback);
      },
      onPhysicsFallback: () => {
        if (cancelled) return;
        setAnnouncement(
          'Advanced impact debris is unavailable. Signal Run remains fully playable.',
        );
      },
      onError: (message) => {
        if (cancelled) return;
        readyRef.current = false;
        setReady(false);
        setAnnouncement(message || 'Signal Run could not open on this device.');
      },
    };

    void import('./ball-game-engine')
      .then(({ BallGameEngine: Engine }) => {
        if (cancelled) return;
        const engine = new Engine(host, options);
        localEngine = engine;
        engineRef.current = engine;
        engine.setMuted(mutedRef.current);
        engine.setComfortMode(comfortModeRef.current);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const detail = error instanceof Error ? error.message : '';
        readyRef.current = false;
        setReady(false);
        setAnnouncement(
          detail
            ? `Signal Run could not open: ${detail}`
            : 'Signal Run could not open on this device.',
        );
      });

    return () => {
      cancelled = true;
      clearCountdown();
      if (localEngine && engineRef.current === localEngine) {
        const current = localEngine.getSnapshot();
        if (current.score > 0) persistScore(current.score);
        localEngine.dispose();
        engineRef.current = null;
      }
      readyRef.current = false;
    };
  }, [changeMode, clearCountdown, persistScore]);

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const apply = (enabled: boolean) => {
      comfortModeRef.current = enabled;
      setComfortMode(enabled);
      engineRef.current?.setComfortMode(enabled);
    };
    const frame = window.requestAnimationFrame(() => apply(preference.matches));
    const handleChange = (event: MediaQueryListEvent) => apply(event.matches);
    preference.addEventListener('change', handleChange);
    return () => {
      window.cancelAnimationFrame(frame);
      preference.removeEventListener('change', handleChange);
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      const target = event.target;
      const interactive = target instanceof HTMLElement && Boolean(
        target.closest('button, a, input, select, textarea'),
      );
      const textEntry = target instanceof HTMLElement && Boolean(
        target.closest(
          'input, textarea, select, [contenteditable="true"], [contenteditable="plaintext-only"]',
        ),
      );
      const controlsEnabled =
        modeRef.current === 'countdown' ||
        modeRef.current === 'resuming' ||
        modeRef.current === 'running';

      if (MOVEMENT_KEYS.has(event.code)) {
        if (!controlsEnabled || textEntry) return;
        event.preventDefault();
        engineRef.current?.setKey(event.code, true);
        return;
      }

      if (event.repeat) return;
      if (
        (event.code === 'Enter' || event.code === 'Space') &&
        (
          modeRef.current === 'idle' ||
          modeRef.current === 'crashed' ||
          modeRef.current === 'extracted'
        ) &&
        !interactive
      ) {
        event.preventDefault();
        beginRun();
        return;
      }

      if (event.code === 'Escape' || event.code === 'KeyP') {
        if (interactive && event.code === 'Escape' && modeRef.current !== 'paused') return;
        event.preventDefault();
        if (modeRef.current === 'running') pauseRun();
        else if (modeRef.current === 'paused') resumeRun();
        else if (
          modeRef.current === 'countdown' ||
          modeRef.current === 'resuming'
        ) {
          interruptRun();
        }
      }
    };

    const handleKeyUp = (event: KeyboardEvent) => {
      if (MOVEMENT_KEYS.has(event.code)) engineRef.current?.setKey(event.code, false);
    };
    const pauseWhenHidden = () => {
      if (document.hidden) interruptRun();
    };

    window.addEventListener('keydown', handleKeyDown, { passive: false });
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', interruptRun);
    document.addEventListener('visibilitychange', pauseWhenHidden);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', interruptRun);
      document.removeEventListener('visibilitychange', pauseWhenHidden);
    };
  }, [beginRun, interruptRun, pauseRun, resumeRun]);

  useEffect(() => {
    const persistActiveRun = () => {
      if (modeRef.current === 'idle') return;
      const current = engineRef.current?.getSnapshot();
      if (current && current.score > 0) persistScore(current.score);
    };
    window.addEventListener('pagehide', persistActiveRun);
    return () => window.removeEventListener('pagehide', persistActiveRun);
  }, [persistScore]);

  useEffect(() => {
    const synchronizeBest = (event: StorageEvent) => {
      if (event.key !== SIGNAL_RUN_BALL_BEST_KEY) return;
      const synchronized = Math.max(
        bestScoreRef.current,
        readBestScore(availableStorage(), SIGNAL_RUN_BALL_BEST_KEY),
      );
      bestScoreRef.current = synchronized;
      setBestScore(synchronized);
    };
    window.addEventListener('storage', synchronizeBest);
    return () => window.removeEventListener('storage', synchronizeBest);
  }, []);

  const toggleMuted = () => {
    const next = !mutedRef.current;
    mutedRef.current = next;
    setMuted(next);
    engineRef.current?.setMuted(next);
    if (!next) ensureAudio();
    setAnnouncement(`Sound ${next ? 'off' : 'on'}.`);
  };

  const toggleComfort = () => {
    const next = !comfortModeRef.current;
    comfortModeRef.current = next;
    setComfortMode(next);
    engineRef.current?.setComfortMode(next);
    setAnnouncement(`Steady camera ${next ? 'on' : 'off'}.`);
  };

  const toggleAssist = () => {
    const next = !assistModeRef.current;
    assistModeRef.current = next;
    setAssistMode(next);
    if (modeRef.current === 'paused') {
      setAnnouncement(
        `Assist mode ${next ? 'on' : 'off'}. The change applies when you restart.`,
      );
      return;
    }
    setAnnouncement(
      next
        ? 'Assist mode on. Openings will be wider.'
        : 'Assist mode off. Standard openings restored.',
    );
  };

  return (
    <BallInterface
      snapshot={snapshot}
      mode={mode}
      ready={ready}
      bestScore={bestScore}
      isNewBest={runWasNewBest}
      countdown={countdown}
      announcement={announcement}
      muted={muted}
      comfortMode={comfortMode}
      assistMode={assistMode}
      primedDirection={primedInput.direction}
      onPlay={beginRun}
      onPause={pauseRun}
      onResume={resumeRun}
      onRestart={beginRun}
      onExit={exitGame}
      onToggleMuted={toggleMuted}
      onToggleComfort={toggleComfort}
      onToggleAssist={toggleAssist}
    >
      <div ref={canvasHostRef} className={styles.canvasHost} />
    </BallInterface>
  );
}
