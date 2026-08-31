import {
  BALL_INITIAL_SPEED,
  BALL_MAX_SPEED,
  type BallPace,
} from './ball-simulation';

type AudioWindow = Window &
  typeof globalThis & {
    webkitAudioContext?: typeof AudioContext;
  };

/** Procedural, sample-free audio scoped to the production ball runner. */
export class BallSignalRunAudio {
  private context: AudioContext | null = null;
  private master: GainNode | null = null;
  private droneGain: GainNode | null = null;
  private windGain: GainNode | null = null;
  private drone: OscillatorNode | null = null;
  private wind: AudioBufferSourceNode | null = null;
  private muted = false;

  async unlock(): Promise<boolean> {
    if (typeof window === 'undefined') return false;
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
      droneFilter.type = 'lowpass';
      droneFilter.frequency.value = 170;
      droneFilter.Q.value = 1.4;
      droneFilter.connect(compressor);

      const droneGain = context.createGain();
      droneGain.gain.value = 0.065;
      droneGain.connect(droneFilter);

      const drone = context.createOscillator();
      drone.type = 'sawtooth';
      drone.frequency.value = 44;
      drone.detune.value = -7;
      drone.connect(droneGain);
      drone.start();

      const windFilter = context.createBiquadFilter();
      windFilter.type = 'bandpass';
      windFilter.frequency.value = 420;
      windFilter.Q.value = 0.7;
      windFilter.connect(compressor);

      const windGain = context.createGain();
      windGain.gain.value = 0.025;
      windGain.connect(windFilter);

      const buffer = context.createBuffer(
        1,
        context.sampleRate * 2,
        context.sampleRate,
      );
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
      this.drone = drone;
      this.wind = wind;
    }

    if (this.context.state === 'suspended') await this.context.resume();
    return true;
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    if (!this.context || !this.master) return;
    this.master.gain.setTargetAtTime(
      muted ? 0 : 0.16,
      this.context.currentTime,
      0.035,
    );
  }

  setRunning(running: boolean): void {
    if (!this.context || !this.droneGain || !this.windGain) return;
    const now = this.context.currentTime;
    this.droneGain.gain.setTargetAtTime(running ? 0.065 : 0.018, now, 0.12);
    this.windGain.gain.setTargetAtTime(running ? 0.025 : 0.004, now, 0.12);
  }

  setSpeed(speed: number): void {
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

  gate(): void {
    this.tone(520, 0.08, 0.045, 'sine', 1.35);
  }

  sector(sector: BallPace): void {
    this.tone(250 + sector * 72, 0.32, 0.07, 'triangle', 1.72);
  }

  overdrive(): void {
    this.tone(330, 0.48, 0.055, 'triangle', 1.5);
    this.tone(495, 0.56, 0.045, 'sine', 1.34);
    this.tone(660, 0.64, 0.035, 'sine', 1.18);
  }

  damage(): void {
    if (!this.context || !this.master || this.muted) return;
    const context = this.context;
    const now = context.currentTime;
    const buffer = context.createBuffer(
      1,
      Math.floor(context.sampleRate * 0.18),
      context.sampleRate,
    );
    const samples = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) {
      const falloff = 1 - index / samples.length;
      samples[index] = (Math.random() * 2 - 1) * falloff;
    }
    const source = context.createBufferSource();
    source.buffer = buffer;
    const filter = context.createBiquadFilter();
    filter.type = 'lowpass';
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

  crash(): void {
    this.tone(92, 0.7, 0.13, 'sawtooth', 0.35);
  }

  extraction(): void {
    this.tone(220, 0.72, 0.055, 'triangle', 2);
    this.tone(330, 0.86, 0.046, 'sine', 1.5);
    this.tone(495, 1.05, 0.035, 'sine', 1.25);
  }

  private tone(
    frequency: number,
    duration: number,
    volume: number,
    type: OscillatorType,
    endRatio: number,
  ): void {
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

  dispose(): void {
    try {
      this.drone?.stop();
      this.wind?.stop();
    } catch {
      // Nodes may already be stopped during React strict-mode cleanup.
    }
    void this.context?.close();
    this.context = null;
    this.master = null;
    this.droneGain = null;
    this.windGain = null;
    this.drone = null;
    this.wind = null;
  }
}
