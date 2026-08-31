import type { AbstractEngine } from '@babylonjs/core/Engines/abstractEngine.js';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';

import {
  LOOM_IRIS_START_SECONDS,
  createLoomSimulation,
  loomIrisStateForElapsed,
} from '../loom-simulation';
import type { RapierDebrisPose } from '../physics/rapier-physics';
import {
  SIGNAL_LOOM_ANCHOR_VISUAL_CAPACITY,
  SIGNAL_LOOM_ASSETS,
  SIGNAL_LOOM_DEBRIS_VISUAL_CAPACITY,
  SignalLoomScene,
  sanitizeLoomVisualDelta,
  signalLoomAnchorVisibleAtZ,
  signalLoomArcVisualProfile,
  signalLoomCameraFovAxis,
  signalLoomIrisBladeCenterRadius,
  signalLoomIrisCueStrength,
  signalLoomIrisGapScale,
  signalLoomDebrisPoolSlot,
  signalLoomPhaseShape,
  signalLoomRailCountForQuality,
  signalLoomRendererIsSoftware,
  signalLoomRibCountForQuality,
  wrappedLoomTunnelZ,
  type SignalLoomEngineFactory,
} from './signal-loom-scene';

function sizedHost(width = 640, height = 360) {
  const host = document.createElement('div');
  Object.defineProperties(host, {
    clientWidth: { configurable: true, value: width },
    clientHeight: { configurable: true, value: height },
  });
  host.getBoundingClientRect = () => ({
    bottom: height,
    height,
    left: 0,
    right: width,
    top: 0,
    width,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  document.body.appendChild(host);
  return host;
}

function nullEngineFactory(
  onEngine?: (engine: NullEngine) => void,
): SignalLoomEngineFactory {
  return async () => {
    const engine = new NullEngine({
      deterministicLockstep: false,
      lockstepMaxSteps: 4,
      renderHeight: 360,
      renderWidth: 640,
      textureSize: 256,
    });
    onEngine?.(engine);
    return { engine, backend: 'webgl' };
  };
}

function debrisPose(id: number): RapierDebrisPose {
  return {
    id,
    position: { x: id, y: -id, z: -10 - id },
    rotation: { x: 0, y: 0, z: 0, w: 1 },
    sleeping: false,
  };
}

describe('Signal Loom presentation helpers', () => {
  it('uses route-local assets and non-color-only phase glyphs', () => {
    expect(Object.values(SIGNAL_LOOM_ASSETS)).toEqual([
      '/game/loom-panels-albedo.webp',
      '/game/loom-veins-mask.webp',
    ]);
    expect(signalLoomPhaseShape('ember')).toBe('diamond');
    expect(signalLoomPhaseShape('cobalt')).toBe('ring');
    expect(new Set([
      signalLoomPhaseShape('ember'),
      signalLoomPhaseShape('cobalt'),
    ]).size).toBe(2);
  });

  it('clamps visual hitch recovery and wraps tunnel motion deterministically', () => {
    expect(sanitizeLoomVisualDelta(-1)).toBe(0);
    expect(sanitizeLoomVisualDelta(Number.NaN)).toBe(0);
    expect(sanitizeLoomVisualDelta(0.2)).toBe(0.05);
    expect(wrappedLoomTunnelZ(-70, 12, 100)).toBeCloseTo(-58);
    expect(wrappedLoomTunnelZ(-70, 112, 100)).toBeCloseTo(-58);
  });

  it('maps stable physics ids into a bounded debris pool', () => {
    expect(signalLoomDebrisPoolSlot(0, 32)).toBe(0);
    expect(signalLoomDebrisPoolSlot(33, 32)).toBe(1);
    expect(signalLoomDebrisPoolSlot(-1, 32)).toBe(31);
    expect(signalLoomDebrisPoolSlot(1, 0)).toBe(-1);
  });

  it('gives every contract arc a distinct protected environment movement', () => {
    const profiles = [1, 2, 3, 4].map((arc) =>
      signalLoomArcVisualProfile(arc as 1 | 2 | 3 | 4),
    );

    expect(new Set(profiles.map(({ ribRotationRate }) => ribRotationRate)).size)
      .toBe(4);
    expect(profiles[0].irisVisible).toBe(false);
    expect(profiles[1].irisVisible).toBe(false);
    expect(profiles[2].irisVisible).toBe(true);
    expect(profiles[3].warmBlend).toBeGreaterThan(0);
    expect(profiles[3].fogDensity).toBeLessThan(profiles[2].fogDensity);
  });

  it('reduces structural rib submissions on the emergency tier', () => {
    expect(signalLoomRibCountForQuality('cinematic')).toBe(24);
    expect(signalLoomRibCountForQuality('balanced')).toBe(24);
    expect(signalLoomRibCountForQuality('performance')).toBe(6);
    expect(signalLoomRailCountForQuality('balanced')).toBe(24);
    expect(signalLoomRailCountForQuality('performance')).toBe(8);
  });

  it('recognizes software WebGL renderers without penalizing ordinary GPUs', () => {
    expect(signalLoomRendererIsSoftware('Google SwiftShader')).toBe(true);
    expect(signalLoomRendererIsSoftware('Mesa llvmpipe (LLVM 18.1)')).toBe(true);
    expect(signalLoomRendererIsSoftware('ANGLE (NVIDIA RTX 4060)')).toBe(false);
  });

  it('preserves horizontal flight-plane visibility on portrait canvases', () => {
    expect(signalLoomCameraFovAxis(320, 568)).toBe('horizontal');
    expect(signalLoomCameraFovAxis(412, 915)).toBe('horizontal');
    expect(signalLoomCameraFovAxis(568, 320)).toBe('vertical');
    expect(signalLoomCameraFovAxis(1280, 720)).toBe('vertical');
    expect(signalLoomCameraFovAxis(Number.NaN, Number.NaN)).toBe('vertical');
  });

  it('maps the authoritative Iris aperture to its visible core and blade ring', () => {
    expect(signalLoomIrisGapScale(2.9)).toBeCloseTo(1);
    expect(signalLoomIrisGapScale(3.35) * 2.9).toBeCloseTo(3.35);
    expect(signalLoomIrisBladeCenterRadius(3.35)).toBeCloseTo(4.97);
    expect(signalLoomIrisBladeCenterRadius(-2)).toBeCloseTo(1.62);
  });

  it('keeps an accurate future-aperture cue through telegraph and approach', () => {
    expect(signalLoomIrisCueStrength('dormant', -110, 1)).toBe(0);
    expect(signalLoomIrisCueStrength('telegraph', -110, 0.25)).toBeCloseTo(0.25);
    expect(signalLoomIrisCueStrength('approach', -29, 0.84)).toBeCloseTo(0.84);
    expect(signalLoomIrisCueStrength('close', -24, 1)).toBe(1);
    expect(signalLoomIrisCueStrength('close', -12, 1)).toBeCloseTo(0.5);
    expect(signalLoomIrisCueStrength('contact', 0, 1)).toBe(0);
    expect(signalLoomIrisCueStrength('recovery', 12, 0.5)).toBe(0);
  });

  it('culls only anchors too distant to be actionable at each quality tier', () => {
    expect(signalLoomAnchorVisibleAtZ(-94.9, 'performance')).toBe(true);
    expect(signalLoomAnchorVisibleAtZ(-95.1, 'performance')).toBe(false);
    expect(signalLoomAnchorVisibleAtZ(-179.9, 'balanced')).toBe(true);
    expect(signalLoomAnchorVisibleAtZ(-180.1, 'cinematic')).toBe(false);
    expect(signalLoomAnchorVisibleAtZ(18, 'performance')).toBe(true);
    expect(signalLoomAnchorVisibleAtZ(18.1, 'performance')).toBe(false);
    expect(signalLoomAnchorVisibleAtZ(Number.NaN, 'performance')).toBe(false);
  });
});

describe('SignalLoomScene lifecycle', () => {
  it('owns a diagnostics canvas and mirrors simulation/debris into fixed pools', async () => {
    const host = sizedHost();
    const disconnect = vi.fn();
    const observe = vi.fn();
    let engineResize: ReturnType<typeof vi.spyOn> | undefined;
    let engineSetSize: ReturnType<typeof vi.spyOn> | undefined;
    const scene = await SignalLoomScene.create(host, {
      engineFactory: nullEngineFactory((engine) => {
        engineResize = vi.spyOn(engine, 'resize');
        engineSetSize = vi.spyOn(engine, 'setSize');
      }),
      physicsBackend: 'rapier',
      resizeObserverFactory: () => ({ disconnect, observe }),
      touchFirst: true,
    });

    const canvas = scene.getCanvas();
    expect(host.contains(canvas)).toBe(true);
    expect(canvas.dataset).toMatchObject({
      activeDebris: '0',
      physicsBackend: 'rapier',
      qualityTier: 'balanced',
      renderBackend: 'webgl',
      fovAxis: 'vertical',
    });
    expect(Number(canvas.dataset.pixelRatio)).toBeGreaterThan(0);
    expect(engineResize).toHaveBeenCalled();
    expect(engineSetSize).toHaveBeenCalled();
    expect(engineSetSize).not.toHaveBeenCalledWith(640, 360, true);
    expect(observe).toHaveBeenCalledWith(host);
    expect(scene.getDiagnostics()).toMatchObject({
      activeDebris: 0,
      anchorCapacity: SIGNAL_LOOM_ANCHOR_VISUAL_CAPACITY,
      debrisCapacity: SIGNAL_LOOM_DEBRIS_VISUAL_CAPACITY,
      disposed: false,
      paused: false,
      physicsBackend: 'rapier',
      qualityTier: 'balanced',
      renderBackend: 'webgl',
    });

    const simulation = createLoomSimulation('scene-contract');
    scene.render(simulation, 1 / 60);
    expect(canvas.dataset.visualArc).toBe('1');
    expect(canvas.dataset.irisStage).toBe('dormant');
    expect(canvas.dataset.activeIrisBlades).toBe('0');
    expect(canvas.dataset.irisCueVisible).toBe('false');

    simulation.arc = 3;
    simulation.iris = loomIrisStateForElapsed(
      simulation.seed,
      LOOM_IRIS_START_SECONDS + 5,
    );
    scene.render(simulation, 1 / 60);
    expect(canvas.dataset).toMatchObject({
      activeIrisBlades: '12',
      irisCycle: '1',
      irisGapRadius: simulation.iris.gapRadius.toFixed(3),
      irisGapX: simulation.iris.gapCenter.x.toFixed(3),
      irisGapY: simulation.iris.gapCenter.y.toFixed(3),
      irisStage: 'approach',
      irisZ: simulation.iris.z.toFixed(3),
      irisCueVisible: 'true',
    });
    expect(Number(canvas.dataset.irisCueScreenX)).toBeGreaterThan(0);
    expect(Number(canvas.dataset.irisCueScreenY)).toBeGreaterThan(0);
    expect(Number(canvas.dataset.irisCueScreenRadius)).toBeGreaterThan(0);
    scene.syncDebris([debrisPose(0), debrisPose(1)]);
    expect(canvas.dataset.activeDebris).toBe('2');

    scene.syncDebris((visit) => {
      visit(debrisPose(4));
    });
    expect(scene.getDiagnostics().activeDebris).toBe(1);

    scene.pause();
    expect(scene.getDiagnostics().paused).toBe(true);
    scene.resume();
    expect(scene.getDiagnostics().paused).toBe(false);
    scene.setComfortMode(true);
    scene.impact(1.5);
    scene.stitch({ expressive: true, nearMiss: false, phase: 'ember' });
    scene.resonance(true);
    scene.resize();

    scene.dispose();
    scene.dispose();
    expect(scene.getDiagnostics().disposed).toBe(true);
    expect(host.contains(canvas)).toBe(false);
    expect(disconnect).toHaveBeenCalledTimes(1);
    host.remove();
  });

  it('disposes a late engine result when an effect aborts during creation', async () => {
    const host = sizedHost();
    const controller = new AbortController();
    const dispose = vi.fn();
    let resolveFactory: ((selection: {
      engine: AbstractEngine;
      backend: 'webgl';
    }) => void) | undefined;
    const engineFactory: SignalLoomEngineFactory = () => new Promise((resolve) => {
      resolveFactory = resolve;
    });

    const pending = SignalLoomScene.create(host, {
      engineFactory,
      signal: controller.signal,
      touchFirst: false,
    });
    controller.abort();
    resolveFactory?.({
      engine: { dispose } as unknown as AbstractEngine,
      backend: 'webgl',
    });

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(dispose).toHaveBeenCalledTimes(1);
    expect(host.querySelector('canvas')).toBeNull();
    host.remove();
  });
});
