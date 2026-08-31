import type {
  BallGateEvent,
  BallImpactEvent,
  BallPace,
  BallStatus,
} from './ball-simulation';

export type BallRunMode =
  | 'idle'
  | 'countdown'
  | 'resuming'
  | 'running'
  | 'paused'
  | 'crashed'
  | 'extracted';

export interface BallGameSnapshot {
  status: BallStatus;
  score: number;
  exactScore: number;
  distance: number;
  elapsed: number;
  contractRemaining: number;
  speed: number;
  pace: BallPace;
  integrity: number;
  combo: number;
  ball: { x: number; y: number };
  gatesCleared: number;
  nearMisses: number;
  impacts: number;
  overdriveCharge: number;
  overdriveRemaining: number;
  overdriveActivations: number;
}

export interface BallPrimedInputFeedback {
  direction: string | null;
}

export interface BallGameDiagnostics {
  ready: boolean;
  running: boolean;
  physicsBackend: 'rapier' | 'none';
  renderBackend: 'webgpu' | 'webgl' | 'none';
  canvasCount: number;
}

export interface BallGameEngineOptions {
  onReady(): void;
  onSnapshot(snapshot: BallGameSnapshot): void;
  onImpact(event: BallImpactEvent, snapshot: BallGameSnapshot): void;
  onGate(event: BallGateEvent, snapshot: BallGameSnapshot): void;
  onPace(pace: BallPace): void;
  onOverdrive(snapshot: BallGameSnapshot): void;
  onCrash(snapshot: BallGameSnapshot): void;
  onExtract(snapshot: BallGameSnapshot): void;
  onPrimedInput(feedback: BallPrimedInputFeedback): void;
  onPhysicsFallback?(): void;
  onError?(message: string): void;
}
