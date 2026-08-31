import type { AbstractEngine } from '@babylonjs/core/Engines/abstractEngine.js';
import { Engine } from '@babylonjs/core/Engines/engine.js';
import type { EngineOptions } from '@babylonjs/core/Engines/thinEngine.js';
import {
  WebGPUEngine,
  type WebGPUEngineOptions,
} from '@babylonjs/core/Engines/webgpuEngine.js';

export type BabylonRenderBackend = 'webgpu' | 'webgl';

export interface DisposableBabylonEngine {
  dispose(): void;
}

export interface InitializableBabylonEngine extends DisposableBabylonEngine {
  initAsync(): Promise<void>;
}

export type BabylonEngineSelection<
  TWebGPU extends InitializableBabylonEngine,
  TWebGL extends DisposableBabylonEngine,
> =
  | { engine: TWebGPU; backend: 'webgpu' }
  | { engine: TWebGL; backend: 'webgl' };

export interface BabylonEngineFactoryDependencies<
  TWebGPU extends InitializableBabylonEngine,
  TWebGL extends DisposableBabylonEngine,
> {
  isWebGPUSupported(): Promise<boolean>;
  createWebGPU(
    canvas: HTMLCanvasElement,
    options: WebGPUEngineOptions,
  ): TWebGPU;
  createWebGL(
    canvas: HTMLCanvasElement,
    antialias: boolean,
    options: EngineOptions,
    adaptToDeviceRatio: boolean,
  ): TWebGL;
}

export interface BabylonEngineFactoryOptions {
  /** Canvas MSAA is disabled by default; post-process AA is cheaper to tier. */
  antialias?: boolean;
  powerPreference?: 'low-power' | 'high-performance';
  stencil?: boolean;
}

const DEFAULT_DEPENDENCIES: BabylonEngineFactoryDependencies<
  WebGPUEngine,
  Engine
> = {
  isWebGPUSupported: () => WebGPUEngine.IsSupportedAsync,
  createWebGPU: (canvas, options) => new WebGPUEngine(canvas, options),
  createWebGL: (canvas, antialias, options, adaptToDeviceRatio) =>
    new Engine(canvas, antialias, options, adaptToDeviceRatio),
};

function disposeFailedCandidate(candidate: DisposableBabylonEngine | null) {
  if (!candidate) return;
  try {
    candidate.dispose();
  } catch {
    // A partially initialized GPU device may also reject disposal. WebGL must
    // still get a chance to start instead of leaving the route unplayable.
  }
}

/**
 * Creates a browser rendering engine with an explicit WebGPU -> WebGL path.
 *
 * This intentionally does not use EngineFactory: its final NullEngine fallback
 * can report success without producing pixels. It also accepts no remote
 * script/decoder URLs, keeping engine startup compatible with the site's CSP.
 */
export async function createBabylonEngine<
  TWebGPU extends InitializableBabylonEngine = WebGPUEngine,
  TWebGL extends DisposableBabylonEngine = Engine,
>(
  canvas: HTMLCanvasElement,
  options: BabylonEngineFactoryOptions = {},
  dependencies?: BabylonEngineFactoryDependencies<TWebGPU, TWebGL>,
): Promise<BabylonEngineSelection<TWebGPU, TWebGL>> {
  const resolvedDependencies = (
    dependencies ?? DEFAULT_DEPENDENCIES
  ) as BabylonEngineFactoryDependencies<TWebGPU, TWebGL>;
  const antialias = options.antialias ?? false;
  const powerPreference = options.powerPreference ?? 'high-performance';
  const stencil = options.stencil ?? false;

  const webGPUOptions: WebGPUEngineOptions = {
    adaptToDeviceRatio: false,
    antialias,
    audioEngine: false,
    powerPreference,
    stencil,
  };
  const webGLOptions: EngineOptions = {
    adaptToDeviceRatio: false,
    antialias,
    audioEngine: false,
    failIfMajorPerformanceCaveat: false,
    loseContextOnDispose: true,
    powerPreference,
    premultipliedAlpha: false,
    preserveDrawingBuffer: false,
    stencil,
  };

  let webGPUSupported = false;
  try {
    webGPUSupported = await resolvedDependencies.isWebGPUSupported();
  } catch {
    // Capability probing itself can reject on an unhealthy adapter. Treat that
    // as unavailable and continue with the universally supported browser path.
  }

  if (webGPUSupported) {
    let candidate: TWebGPU | null = null;
    try {
      candidate = resolvedDependencies.createWebGPU(canvas, webGPUOptions);
      await candidate.initAsync();
      return { engine: candidate, backend: 'webgpu' };
    } catch {
      disposeFailedCandidate(candidate);
    }
  }

  const engine = resolvedDependencies.createWebGL(
    canvas,
    antialias,
    webGLOptions,
    false,
  );
  return { engine, backend: 'webgl' };
}

export type BrowserBabylonEngineSelection = BabylonEngineSelection<
  WebGPUEngine,
  Engine
> & { engine: AbstractEngine };
