import {
  BALL_INITIAL_SPEED,
  BALL_MAX_SPEED,
  type BallPace,
} from './ball-simulation';
import type { LoomArc, LoomStitchEvent } from './loom-simulation';

type LegacySignalPhraseResult = 'clean' | 'broken';

type AudioWindow = Window &
  typeof globalThis & {
    webkitAudioContext?: typeof AudioContext;
  };

/**
 * A tiny procedural score for Signal Run. Audio is synthesized after a user
 * gesture, so the game ships without borrowed samples or autoplay surprises.
 */
export class SignalRunAudio {
  private context: AudioContext | null = null;
  private master: GainNode | null = null;
  private droneGain: GainNode | null = null;
  private windGain: GainNode | null = null;
  private droneFilter: BiquadFilterNode | null = null;
  private windFilter: BiquadFilterNode | null = null;
  private drone: OscillatorNode | null = null;
  private wind: AudioBufferSourceNode | null = null;
  private muted = false;

  async unlock(): Promise<boolean> {
    if (typeof window === "undefined") return false;

    if (!this.context) {
      const AudioContextConstructor =
        window.AudioContext ?? (window as AudioWindow).webkitAudioContext;
      if (!AudioContextConstructor) return false;

      const context = new AudioContextConstructor();
      const master = context.createGain();
      master.gain.value = this.muted ? 0 : 0.16;
      master.connect(context.destination);

      const compressor = context.createDynamicsCompressor();
      compressor.threshold.value = -24;
      compressor.knee.value = 18;
      compressor.ratio.value = 5;
      compressor.attack.value = 0.01;
      compressor.release.value = 0.22;
      compressor.connect(master);

      const droneFilter = context.createBiquadFilter();
      droneFilter.type = "lowpass";
      droneFilter.frequency.value = 170;
      droneFilter.Q.value = 1.4;
      droneFilter.connect(compressor);

      const droneGain = context.createGain();
      droneGain.gain.value = 0.065;
      droneGain.connect(droneFilter);

      const drone = context.createOscillator();
      drone.type = "sawtooth";
      drone.frequency.value = 44;
      drone.detune.value = -7;
      drone.connect(droneGain);
      drone.start();

      const windFilter = context.createBiquadFilter();
      windFilter.type = "bandpass";
      windFilter.frequency.value = 420;
      windFilter.Q.value = 0.7;
      windFilter.connect(compressor);

      const windGain = context.createGain();
      windGain.gain.value = 0.025;
      windGain.connect(windFilter);

      const buffer = context.createBuffer(1, context.sampleRate * 2, context.sampleRate);
      const samples = buffer.getChannelData(0);
      for (let index = 0; index < samples.length; index += 1) {
        samples[index] = Math.random() * 2 - 1;
      }
      const wind = context.createBufferSource();
      wind.buffer = buffer;
      wind.loop = true;
      wind.connect(windGain);
      wind.start();

      this.context = context;
      this.master = master;
      this.droneGain = droneGain;
      this.windGain = windGain;
      this.droneFilter = droneFilter;
      this.windFilter = windFilter;
      this.drone = drone;
      this.wind = wind;
    }

    if (this.context.state === "suspended") {
      await this.context.resume();
    }
    return true;
  }

  setMuted(muted: boolean) {
    this.muted = muted;
    if (!this.context || !this.master) return;
    this.master.gain.setTargetAtTime(muted ? 0 : 0.16, this.context.currentTime, 0.035);
  }

  setRunning(running: boolean) {
    if (!this.context || !this.droneGain || !this.windGain) return;
    const now = this.context.currentTime;
    this.droneGain.gain.setTargetAtTime(running ? 0.065 : 0.018, now, 0.12);
    this.windGain.gain.setTargetAtTime(running ? 0.025 : 0.004, now, 0.12);
  }

  setSpeed(speed: number) {
    if (!this.context || !this.drone || !this.windGain) return;
    const normalized = Math.min(
      Math.max(
        (speed - BALL_INITIAL_SPEED) / (BALL_MAX_SPEED - BALL_INITIAL_SPEED),
        0,
      ),
      1,
    );
    const now = this.context.currentTime;
    this.drone.frequency.setTargetAtTime(44 + normalized * 18, now, 0.08);
    this.windGain.gain.setTargetAtTime(0.025 + normalized * 0.045, now, 0.08);
  }

  /**
   * Shapes the continuous score around Signal Loom's physical state. Reeling
   * damps the wind, while an extended high-tension thread opens the filter and
   * lifts the carrier pitch. This keeps the sound informative without adding a
   * licensed music loop or masking anchor cues.
   */
  setLoomState(
    speed: number,
    tension: number,
    reeling: boolean,
    resonanceActive: boolean,
  ) {
    if (
      !this.context ||
      !this.drone ||
      !this.droneGain ||
      !this.windGain ||
      !this.droneFilter ||
      !this.windFilter
    ) return;
    const normalizedSpeed = Math.min(Math.max((speed - 8.5) / (22 - 8.5), 0), 1);
    const normalizedTension = Math.min(Math.max(tension, 0), 1);
    const now = this.context.currentTime;
    const resonanceLift = resonanceActive ? 9 : 0;

    this.drone.frequency.setTargetAtTime(
      40 + normalizedSpeed * 24 + normalizedTension * 11 + resonanceLift,
      now,
      0.075,
    );
    this.droneFilter.frequency.setTargetAtTime(
      150 + normalizedSpeed * 190 + normalizedTension * 310,
      now,
      0.09,
    );
    this.windFilter.frequency.setTargetAtTime(
      360 + normalizedSpeed * 760 + normalizedTension * 280,
      now,
      0.09,
    );
    this.droneGain.gain.setTargetAtTime(
      0.052 + normalizedTension * 0.026 + (resonanceActive ? 0.018 : 0),
      now,
      0.08,
    );
    this.windGain.gain.setTargetAtTime(
      (0.018 + normalizedSpeed * 0.048) * (reeling ? 0.58 : 1),
      now,
      0.08,
    );
  }

  phase(phase: "ember" | "cobalt") {
    this.tone(phase === "ember" ? 240 : 360, 0.12, 0.08, "triangle", 1.45);
  }

  gate() {
    this.tone(520, 0.08, 0.045, "sine", 1.35);
  }

  sector(sector: BallPace) {
    this.tone(250 + sector * 72, 0.32, 0.07, 'triangle', 1.72);
  }

  phrase(result: LegacySignalPhraseResult, cleanStreak: number) {
    if (result === 'broken') {
      this.tone(170, 0.18, 0.05, 'triangle', 0.72);
      return;
    }
    const streakLift = Math.min(Math.max(cleanStreak - 1, 0), 4) * 28;
    this.tone(470 + streakLift, 0.16, 0.055, 'sine', 1.32);
  }

  resonance() {
    // A compact, original signal chord marks the reward window without
    // borrowing a melody or masking gameplay cues.
    this.tone(330, 0.48, 0.055, 'triangle', 1.5);
    this.tone(495, 0.56, 0.045, 'sine', 1.34);
    this.tone(660, 0.64, 0.035, 'sine', 1.18);
  }

  loomArc(arc: LoomArc) {
    const base = 174 + arc * 42;
    this.tone(base, 0.28, 0.05, 'triangle', 1.5);
    this.tone(base * 1.5, 0.36, 0.032, 'sine', 1.25);
  }

  stitch(event: Readonly<LoomStitchEvent>) {
    const chainLift = Math.min(event.chain, 8) * 16;
    const expressiveLift = event.expressive ? 95 : 0;
    const nearMissLift = event.nearMiss ? 42 : 0;
    this.tone(
      420 + chainLift + expressiveLift + nearMissLift,
      event.expressive ? 0.19 : 0.13,
      event.expressive ? 0.064 : 0.048,
      event.nearMiss ? 'triangle' : 'sine',
      event.resonanceActive ? 1.62 : 1.34,
    );
  }

  resonanceReady() {
    this.tone(294, 0.24, 0.042, 'sine', 1.5);
    this.tone(441, 0.3, 0.03, 'triangle', 1.25);
  }

  threadBreak() {
    this.damage();
    this.tone(138, 0.24, 0.045, 'sawtooth', 0.55);
  }

  anchorMiss(opening = false) {
    this.tone(opening ? 205 : 188, 0.13, 0.026, 'triangle', 0.72);
    this.tone(opening ? 154 : 142, 0.2, 0.018, 'sine', 0.68);
  }

  irisClear() {
    this.tone(392, 0.32, 0.052, 'triangle', 1.5);
    this.tone(588, 0.46, 0.042, 'sine', 1.32);
    this.tone(784, 0.58, 0.028, 'sine', 1.18);
  }

  irisHit() {
    this.tone(126, 0.31, 0.042, 'sawtooth', 0.58);
    this.tone(92, 0.42, 0.028, 'triangle', 0.52);
  }

  extraction() {
    this.tone(220, 0.72, 0.055, 'triangle', 2);
    this.tone(330, 0.86, 0.046, 'sine', 1.5);
    this.tone(495, 1.05, 0.035, 'sine', 1.25);
  }

  damage() {
    if (!this.context || !this.master || this.muted) return;
    const context = this.context;
    const now = context.currentTime;
    const buffer = context.createBuffer(1, Math.floor(context.sampleRate * 0.18), context.sampleRate);
    const samples = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) {
      const falloff = 1 - index / samples.length;
      samples[index] = (Math.random() * 2 - 1) * falloff;
    }
    const source = context.createBufferSource();
    source.buffer = buffer;
    const filter = context.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 260;
    const gain = context.createGain();
    gain.gain.setValueAtTime(0.18, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
    source.connect(filter);
    filter.connect(gain);
    gain.connect(this.master);
    source.start(now);
    source.stop(now + 0.2);
  }

  crash() {
    this.tone(92, 0.7, 0.13, "sawtooth", 0.35);
  }

  private tone(
    frequency: number,
    duration: number,
    volume: number,
    type: OscillatorType,
    endRatio: number,
  ) {
    if (!this.context || !this.master || this.muted) return;
    const context = this.context;
    const now = context.currentTime;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, now);
    oscillator.frequency.exponentialRampToValueAtTime(
      Math.max(frequency * endRatio, 20),
      now + duration,
    );
    gain.gain.setValueAtTime(0.001, now);
    gain.gain.exponentialRampToValueAtTime(volume, now + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.001, now + duration);
    oscillator.connect(gain);
    gain.connect(this.master);
    oscillator.start(now);
    oscillator.stop(now + duration + 0.02);
  }

  dispose() {
    try {
      this.drone?.stop();
      this.wind?.stop();
    } catch {
      // Nodes may already be stopped when React performs a strict-mode cleanup.
    }
    void this.context?.close();
    this.context = null;
    this.master = null;
    this.droneGain = null;
    this.windGain = null;
    this.droneFilter = null;
    this.windFilter = null;
    this.drone = null;
    this.wind = null;
  }
}
