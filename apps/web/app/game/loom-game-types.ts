import type {
  LoomArc,
  LoomEncounterKind,
  LoomExtractionResult,
  LoomIrisOutcome,
  LoomIrisStage,
  LoomPhase,
  LoomStitchEvent,
} from './loom-simulation';

export type LoomRunMode =
  | 'idle'
  | 'countdown'
  | 'resuming'
  | 'running'
  | 'paused'
  | 'finished';

export interface LoomActiveEncounter {
  kind: LoomEncounterKind;
  beat: number;
  route: 'safe' | 'expressive';
  phase: LoomPhase;
  secondsToContact: number;
}

export interface LoomGameSnapshot {
  score: number;
  exactScore: number;
  distance: number;
  elapsed: number;
  contractRemaining: number;
  contractProgress: number;
  speed: number;
  phase: LoomPhase;
  arc: LoomArc;
  activeEncounter: LoomActiveEncounter | null;
  needle: { x: number; y: number };
  echo: { x: number; y: number };
  threadLength: number;
  threadTension: number;
  peakThreadTension: number;
  reeling: boolean;
  stitches: number;
  safeStitches: number;
  expressiveStitches: number;
  missedAnchors: number;
  nearMisses: number;
  threadBreaks: number;
  stitchChain: number;
  bestStitchChain: number;
  resonanceCharge: number;
  resonanceReady: boolean;
  resonanceRemaining: number;
  resonanceCooldownRemaining: number;
  resonanceActivations: number;
  authoredChunksSeen: number;
  iris: {
    active: boolean;
    cycle: number;
    stage: LoomIrisStage;
    z: number;
    gapCenter: { x: number; y: number };
    gapRadius: number;
    secondsToContact: number | null;
    intensity: number;
    resolved: boolean;
    outcome: LoomIrisOutcome;
    chargeAwarded: boolean;
  };
  extraction: LoomExtractionResult | null;
}

export interface LoomPrimedInputFeedback {
  direction: string | null;
  phase: LoomPhase | null;
  reel: boolean;
  resonance: boolean;
}

export interface LoomGameEngineOptions {
  onReady(): void;
  onSnapshot(snapshot: LoomGameSnapshot): void;
  onThreadBreak(snapshot: LoomGameSnapshot): void;
  onAnchorMiss(snapshot: LoomGameSnapshot, opening: boolean): void;
  onIrisClear(snapshot: LoomGameSnapshot): void;
  onIrisHit(snapshot: LoomGameSnapshot): void;
  onPhase(phase: LoomPhase): void;
  onArc(arc: LoomArc): void;
  onStitch(event: LoomStitchEvent): void;
  onResonance(): void;
  onExtract(snapshot: LoomGameSnapshot): void;
  onPrimedInput(feedback: LoomPrimedInputFeedback): void;
  onPhysicsFallback?(): void;
  onError?(message: string): void;
}
