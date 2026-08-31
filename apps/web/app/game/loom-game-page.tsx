'use client';

import { useRouter } from 'next/navigation';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import {
  SignalLoomGameEngine,
  snapshotOfLoom,
  type LoomGameSnapshot,
  type LoomPrimedInputFeedback,
  type LoomRunMode,
} from './loom-game-engine';
import { createLoomSimulation, type LoomStitchEvent } from './loom-simulation';
import LoomInterface, {
  type LoomEventNotice,
  type LoomTouchDirection,
} from './loom-interface';
import {
  SIGNAL_LOOM_BEST_KEY,
  commitBestScore,
  readBestScore,
} from './best-score';

const INITIAL_SNAPSHOT = snapshotOfLoom(createLoomSimulation('signal-loom-intro'));
const EMPTY_PRIMED_INPUT: LoomPrimedInputFeedback = {
  direction: null,
  phase: null,
  reel: false,
  resonance: false,
};
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
const REEL_KEYS = new Set(['ShiftLeft', 'ShiftRight']);

function pulseHaptic(pattern: number | number[]) {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    // Vibration is optional and commonly disabled on desktop browsers.
  }
}

function availableStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function stitchAnnouncement(event: Readonly<LoomStitchEvent>) {
  const route = event.expressive ? 'Expressive stitch' : 'Clean stitch';
  const nearMiss = event.nearMiss ? ' Near pass.' : '';
  return `${route}. ${Math.floor(event.scoreAwarded).toLocaleString('en-CA')} points. Chain ${event.chain}.${nearMiss}`;
}

export default function LoomGamePage() {
  const router = useRouter();
  const canvasHostRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<SignalLoomGameEngine | null>(null);
  const modeRef = useRef<LoomRunMode>('idle');
  const countdownTimersRef = useRef<number[]>([]);
  const noticeTimerRef = useRef<number | null>(null);
  const touchDirectionsRef = useRef(new Set<LoomTouchDirection>());
  const bestScoreRef = useRef(0);

  const [mode, setMode] = useState<LoomRunMode>('idle');
  const [snapshot, setSnapshot] = useState<LoomGameSnapshot>(INITIAL_SNAPSHOT);
  const [countdown, setCountdown] = useState(3);
  const [primedInput, setPrimedInput] = useState(EMPTY_PRIMED_INPUT);
  const [ready, setReady] = useState(false);
  const [muted, setMuted] = useState(false);
  const [comfortMode, setComfortMode] = useState(false);
  const [fullscreenAvailable, setFullscreenAvailable] = useState(false);
  const [fullscreenActive, setFullscreenActive] = useState(false);
  const [bestScore, setBestScore] = useState(0);
  const [isNewBest, setIsNewBest] = useState(false);
  const [announcement, setAnnouncement] = useState('Signal Loom preparing.');
  const [eventNotice, setEventNotice] = useState<LoomEventNotice | null>(null);
  const [error, setError] = useState<string | null>(null);

  const changeMode = useCallback((next: LoomRunMode) => {
    modeRef.current = next;
    setMode(next);
  }, []);

  const clearCountdown = useCallback(() => {
    countdownTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    countdownTimersRef.current = [];
  }, []);

  const clearInput = useCallback(() => {
    touchDirectionsRef.current.clear();
    engineRef.current?.releaseInput();
    setPrimedInput(EMPTY_PRIMED_INPUT);
  }, []);

  const showNotice = useCallback(
    (notice: Omit<LoomEventNotice, 'id'>, duration = 2_400) => {
      if (noticeTimerRef.current !== null) {
        window.clearTimeout(noticeTimerRef.current);
      }
      setEventNotice({ ...notice, id: Date.now() });
      noticeTimerRef.current = window.setTimeout(() => {
        noticeTimerRef.current = null;
        setEventNotice(null);
      }, duration);
    },
    [],
  );

  const persistScore = useCallback((candidate: number, celebrate = false) => {
    const normalizedCandidate = Math.max(
      0,
      Math.floor(Number.isFinite(candidate) ? candidate : 0),
    );
    const previousBest = Math.max(
      bestScoreRef.current,
      readBestScore(availableStorage(), SIGNAL_LOOM_BEST_KEY),
    );
    const nextBest = commitBestScore(
      availableStorage(),
      normalizedCandidate,
      bestScoreRef.current,
      SIGNAL_LOOM_BEST_KEY,
    );
    bestScoreRef.current = nextBest;
    setBestScore(nextBest);
    if (celebrate) setIsNewBest(normalizedCandidate > previousBest);
    return nextBest;
  }, []);

  const ensureAudio = useCallback((engine = engineRef.current) => {
    if (!engine) return;
    void engine.unlockAudio().then((available) => {
      if (available || engineRef.current !== engine) return;
      engine.setMuted(true);
      setMuted(true);
      setAnnouncement('Web Audio is unavailable. The contract remains fully playable.');
    });
  }, []);

  const beginContract = useCallback(() => {
    const engine = engineRef.current;
    if (!engine || !ready || modeRef.current === 'countdown') return;
    clearCountdown();
    clearInput();
    ensureAudio(engine);
    engine.prepareRun(
      (Date.now() ^ Math.floor(Math.random() * 0xffffffff)) >>> 0,
    );
    setIsNewBest(false);
    if (noticeTimerRef.current !== null) {
      window.clearTimeout(noticeTimerRef.current);
      noticeTimerRef.current = null;
    }
    setEventNotice(null);
    engine.primeInput();
    setCountdown(3);
    setAnnouncement('Needle synchronized. Contract begins in three.');
    changeMode('countdown');
    countdownTimersRef.current = [
      window.setTimeout(() => {
        setCountdown(2);
        setAnnouncement('Two. Choose a line.');
      }, 600),
      window.setTimeout(() => {
        setCountdown(1);
        setAnnouncement('One. Hold the Thread.');
      }, 1_200),
      window.setTimeout(() => {
        changeMode('running');
        engine.start();
        setAnnouncement('Contract live. Draw light through the anchors.');
      }, 1_800),
    ];
  }, [changeMode, clearCountdown, clearInput, ensureAudio, ready]);

  const pauseContract = useCallback(() => {
    if (modeRef.current !== 'running') return;
    clearInput();
    engineRef.current?.pause();
    changeMode('paused');
    setAnnouncement('Contract suspended. The Thread is held.');
  }, [changeMode, clearInput]);

  const interruptContract = useCallback(() => {
    const current = modeRef.current;
    clearInput();
    if (current === 'countdown') {
      clearCountdown();
      engineRef.current?.pause();
      setCountdown(3);
      changeMode('idle');
      setAnnouncement('Launch cancelled while the game was out of focus.');
      return;
    }
    if (current === 'resuming') {
      clearCountdown();
      engineRef.current?.pause();
      setCountdown(3);
      changeMode('paused');
      setAnnouncement('Re-entry cancelled. The Thread remains held.');
      return;
    }
    if (current === 'running') pauseContract();
  }, [changeMode, clearCountdown, clearInput, pauseContract]);

  const resumeContract = useCallback(() => {
    if (modeRef.current !== 'paused') return;
    const engine = engineRef.current;
    if (!engine) return;
    clearCountdown();
    clearInput();
    engine.primeInput();
    ensureAudio(engine);
    setCountdown(3);
    changeMode('resuming');
    setAnnouncement('Thread reacquiring in three.');
    countdownTimersRef.current = [
      window.setTimeout(() => {
        setCountdown(2);
        setAnnouncement('Two. Prime your route.');
      }, 350),
      window.setTimeout(() => {
        setCountdown(1);
        setAnnouncement('One. Hold your line.');
      }, 700),
      window.setTimeout(() => {
        changeMode('running');
        engine.start();
        setAnnouncement('Contract resumed.');
      }, 1_050),
    ];
  }, [changeMode, clearCountdown, clearInput, ensureAudio]);

  const endContract = useCallback(() => {
    clearCountdown();
    clearInput();
    const finalSnapshot = engineRef.current?.finishRun() ?? snapshot;
    setSnapshot(finalSnapshot);
    if (finalSnapshot.stitches > 0) {
      persistScore(finalSnapshot.score, true);
    } else {
      setIsNewBest(false);
    }
    changeMode('finished');
    setAnnouncement(`Archive banked with ${finalSnapshot.score.toLocaleString('en-CA')} points.`);
  }, [changeMode, clearCountdown, clearInput, persistScore, snapshot]);

  const exitGame = useCallback(() => {
    const current = modeRef.current;
    if (current === 'running' || current === 'resuming' || current === 'paused') {
      clearCountdown();
      clearInput();
      const finalSnapshot = engineRef.current?.finishRun();
      if (finalSnapshot?.stitches) persistScore(finalSnapshot.score);
    }
    router.push('/');
  }, [clearCountdown, clearInput, persistScore, router]);

  useEffect(() => {
    document.documentElement.classList.add('signal-loom-open');
    document.body.classList.add('signal-loom-open');
    const footer = document.querySelector<HTMLElement>('body > footer, body footer');
    const footerWasInert = footer?.hasAttribute('inert') ?? false;
    const previousFooterAriaHidden = footer?.getAttribute('aria-hidden');
    footer?.setAttribute('inert', '');
    footer?.setAttribute('aria-hidden', 'true');
    return () => {
      if (noticeTimerRef.current !== null) {
        window.clearTimeout(noticeTimerRef.current);
      }
      document.documentElement.classList.remove('signal-loom-open');
      document.body.classList.remove('signal-loom-open');
      if (!footerWasInert) footer?.removeAttribute('inert');
      if (previousFooterAriaHidden === null) footer?.removeAttribute('aria-hidden');
      else if (previousFooterAriaHidden !== undefined) {
        footer?.setAttribute('aria-hidden', previousFooterAriaHidden);
      }
    };
  }, []);

  useEffect(() => {
    const host = canvasHostRef.current;
    if (!host) return;
    const engine = new SignalLoomGameEngine(host, {
      onReady: () => {
        setReady(true);
        setAnnouncement('Signal Loom ready. Begin when you are ready.');
      },
      onSnapshot: setSnapshot,
      onThreadBreak: (current) => {
        pulseHaptic([35, 24, 48]);
        setAnnouncement(`Thread break. ${current.threadBreaks} total. Chain reset.`);
        showNotice({
          tone: 'break',
          eyebrow: 'Thread severed',
          title: 'Rebuild the line',
          detail: 'Chain reset. Ease the Echo back through the next anchor.',
        });
      },
      onAnchorMiss: (_current, opening) => {
        pulseHaptic(opening ? [10, 22, 10] : 10);
        const message = opening
          ? 'Opening splice missed. Hold Reel through contact.'
          : 'Signal anchor passed. Match its phase and cross the illuminated mark.';
        setAnnouncement(message);
        showNotice({
          tone: 'miss',
          eyebrow: opening ? 'Opening splice missed' : 'Signal passed',
          title: opening ? 'Hold Reel through contact' : 'Cross the next anchor',
          detail: opening
            ? 'The opening teaches a controlled stitch before wider exposure.'
            : 'Match the phase shape, then carry the Thread through the mark.',
        });
      },
      onIrisClear: (current) => {
        const chargeCopy = current.iris.chargeAwarded
          ? {
              announcement: 'Resonance charge gained.',
              title: '+1,200 · Resonance +1',
              detail: 'The full Thread cleared the opening and stored one charge.',
            }
          : {
              announcement: 'Resonance was already full.',
              title: '+1,200 · Charge full',
              detail: 'The full Thread cleared the opening. Release stored Resonance before the next Iris to make room.',
            };
        pulseHaptic([12, 18, 34, 18, 56]);
        setAnnouncement(`Iris aligned. Needle, Echo, and Thread clear. Twelve hundred points. ${chargeCopy.announcement}`);
        showNotice({
          tone: 'iris-clear',
          eyebrow: 'Iris aligned',
          title: chargeCopy.title,
          detail: chargeCopy.detail,
        }, 2_800);
      },
      onIrisHit: () => {
        pulseHaptic([48, 20, 72]);
        setAnnouncement('Iris blade contact. Put the Needle, Echo, and full Thread inside the illuminated aperture.');
        showNotice({
          tone: 'iris-hit',
          eyebrow: 'Iris blade contact',
          title: 'Bring both lights inside',
          detail: 'Needle, Echo, and the full Thread must clear the aperture.',
        }, 3_000);
      },
      onPhase: (phase) => {
        pulseHaptic(10);
        setAnnouncement(`${phase === 'ember' ? 'Ember diamond' : 'Cobalt ring'} phase engaged.`);
      },
      onArc: (arc) => {
        pulseHaptic([12, 20, 30]);
        const labels = ['Threading', 'Refraction', 'Iris', 'Extraction'];
        setAnnouncement(`Arc ${arc}: ${labels[arc - 1]}. The Loom has changed.`);
      },
      onStitch: (event) => {
        pulseHaptic(event.expressive ? [8, 18, 12] : 8);
        setAnnouncement(stitchAnnouncement(event));
      },
      onResonance: () => {
        pulseHaptic([18, 24, 18, 24, 54]);
        setAnnouncement('Stored Resonance released. Double exposure for six seconds.');
      },
      onExtract: (finalSnapshot) => {
        pulseHaptic([18, 26, 18, 26, 72]);
        setSnapshot(finalSnapshot);
        if (finalSnapshot.stitches > 0) {
          persistScore(finalSnapshot.score, true);
        } else {
          setIsNewBest(false);
        }
        changeMode('finished');
        setAnnouncement(`Archive extracted. Final score ${finalSnapshot.score.toLocaleString('en-CA')}.`);
      },
      onPrimedInput: setPrimedInput,
      onPhysicsFallback: () => {
        setAnnouncement(
          'Physical debris is unavailable on this device. The full deterministic contract remains playable.',
        );
      },
      onError: (message) => {
        setError(message);
        setAnnouncement('Signal Loom could not open.');
      },
    });
    engineRef.current = engine;
    engine.setMuted(muted);
    engine.setComfortMode(comfortMode);

    bestScoreRef.current = readBestScore(
      availableStorage(),
      SIGNAL_LOOM_BEST_KEY,
    );
    setBestScore(bestScoreRef.current);

    return () => {
      clearCountdown();
      if (
        modeRef.current === 'running' ||
        modeRef.current === 'resuming' ||
        modeRef.current === 'paused'
      ) {
        const current = engine.getSnapshot();
        if (current.stitches > 0) persistScore(current.score);
      }
      engine.dispose();
      engineRef.current = null;
    };
    // One engine owns the canvas for the route lifetime. State changes flow
    // through callbacks and must not recreate Babylon or Rapier.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const apply = (enabled: boolean) => {
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
    const update = () => {
      const root = rootRef.current;
      setFullscreenAvailable(Boolean(
        root &&
        typeof root.requestFullscreen === 'function' &&
        typeof document.exitFullscreen === 'function',
      ));
      setFullscreenActive(document.fullscreenElement === root);
    };
    update();
    document.addEventListener('fullscreenchange', update);
    return () => document.removeEventListener('fullscreenchange', update);
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
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
        modeRef.current === 'running' ||
        modeRef.current === 'resuming';

      if (MOVEMENT_KEYS.has(event.code)) {
        if (!controlsEnabled || textEntry) return;
        event.preventDefault();
        engineRef.current?.setKey(event.code, true);
        return;
      }
      if (REEL_KEYS.has(event.code)) {
        if (!controlsEnabled || textEntry) return;
        event.preventDefault();
        engineRef.current?.setReel(true);
        return;
      }
      if (event.repeat) return;
      if (event.code === 'Space') {
        if (interactive) return;
        event.preventDefault();
        if (controlsEnabled) engineRef.current?.togglePhase();
        else if (modeRef.current === 'idle' || modeRef.current === 'finished') {
          beginContract();
        }
        return;
      }
      if (event.code === 'KeyR' && controlsEnabled && !textEntry) {
        event.preventDefault();
        engineRef.current?.activateResonance();
        return;
      }
      if (
        event.code === 'Enter' &&
        (modeRef.current === 'idle' || modeRef.current === 'finished') &&
        !interactive
      ) {
        event.preventDefault();
        beginContract();
        return;
      }
      if (event.code === 'Escape' || event.code === 'KeyP') {
        if (interactive && event.code === 'Escape' && modeRef.current !== 'paused') return;
        event.preventDefault();
        if (modeRef.current === 'running') pauseContract();
        else if (modeRef.current === 'paused') resumeContract();
        else if (modeRef.current === 'resuming') interruptContract();
      }
    };

    const handleKeyUp = (event: KeyboardEvent) => {
      if (MOVEMENT_KEYS.has(event.code)) engineRef.current?.setKey(event.code, false);
      if (REEL_KEYS.has(event.code)) engineRef.current?.setReel(false);
    };
    const pauseWhenHidden = () => {
      if (document.hidden) interruptContract();
    };
    window.addEventListener('keydown', handleKeyDown, { passive: false });
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', interruptContract);
    document.addEventListener('visibilitychange', pauseWhenHidden);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', interruptContract);
      document.removeEventListener('visibilitychange', pauseWhenHidden);
    };
  }, [beginContract, interruptContract, pauseContract, resumeContract]);

  useEffect(() => {
    const persistActive = () => {
      if (
        modeRef.current !== 'running' &&
        modeRef.current !== 'resuming' &&
        modeRef.current !== 'paused'
      ) return;
      const current = engineRef.current?.getSnapshot();
      if (current?.stitches) persistScore(current.score);
    };
    window.addEventListener('pagehide', persistActive);
    return () => window.removeEventListener('pagehide', persistActive);
  }, [persistScore]);

  useEffect(() => {
    const synchronizeBest = (event: StorageEvent) => {
      if (event.key !== SIGNAL_LOOM_BEST_KEY) return;
      const synchronized = Math.max(
        bestScoreRef.current,
        readBestScore(availableStorage(), SIGNAL_LOOM_BEST_KEY),
      );
      if (synchronized > bestScoreRef.current) setIsNewBest(false);
      bestScoreRef.current = synchronized;
      setBestScore(synchronized);
    };
    window.addEventListener('storage', synchronizeBest);
    return () => window.removeEventListener('storage', synchronizeBest);
  }, []);

  const updateTouchDirection = useCallback((
    direction: LoomTouchDirection,
    pressed: boolean,
  ) => {
    if (pressed) touchDirectionsRef.current.add(direction);
    else touchDirectionsRef.current.delete(direction);
    const directions = touchDirectionsRef.current;
    engineRef.current?.setVirtualDirection(
      Number(directions.has('right')) - Number(directions.has('left')),
      Number(directions.has('up')) - Number(directions.has('down')),
    );
  }, []);

  const toggleSound = () => {
    const next = !muted;
    setMuted(next);
    engineRef.current?.setMuted(next);
    if (!next) ensureAudio();
  };

  const toggleComfort = () => {
    const next = !comfortMode;
    setComfortMode(next);
    engineRef.current?.setComfortMode(next);
  };

  const toggleFullscreen = async () => {
    try {
      if (!document.fullscreenElement) await rootRef.current?.requestFullscreen();
      else await document.exitFullscreen();
    } catch {
      setAnnouncement('The browser declined the fullscreen request.');
    }
  };

  return (
    <div ref={rootRef} className="signal-loom-page">
      <LoomInterface
        snapshot={snapshot}
        mode={mode}
        ready={ready}
        countdown={countdown}
        primedInput={primedInput}
        announcement={announcement}
        eventNotice={eventNotice}
        error={error}
        muted={muted}
        comfortMode={comfortMode}
        fullscreenAvailable={fullscreenAvailable}
        fullscreenActive={fullscreenActive}
        bestScore={bestScore}
        isNewBest={isNewBest}
        onBegin={beginContract}
        onPause={pauseContract}
        onResume={resumeContract}
        onEnd={endContract}
        onTogglePhase={() => engineRef.current?.togglePhase()}
        onSetReel={(active) => engineRef.current?.setReel(active)}
        onActivateResonance={() => engineRef.current?.activateResonance()}
        onTouchDirection={updateTouchDirection}
        onToggleSound={toggleSound}
        onToggleComfort={toggleComfort}
        onToggleFullscreen={() => void toggleFullscreen()}
        onExit={exitGame}
      >
        <div
          ref={canvasHostRef}
          className="signal-loom-canvas-host"
        />
      </LoomInterface>
    </div>
  );
}
