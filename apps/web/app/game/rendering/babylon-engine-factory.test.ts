import { describe, expect, it, vi } from 'vitest';
import {
  createBabylonEngine,
  type BabylonEngineFactoryDependencies,
  type DisposableBabylonEngine,
  type InitializableBabylonEngine,
} from './babylon-engine-factory';

class FakeWebGPU implements InitializableBabylonEngine {
  disposed = 0;

  constructor(private readonly initializationError?: Error) {}

  async initAsync() {
    if (this.initializationError) throw this.initializationError;
  }

  dispose() {
    this.disposed += 1;
  }
}

class FakeWebGL implements DisposableBabylonEngine {
  disposed = 0;

  dispose() {
    this.disposed += 1;
  }
}

function dependencies(
  webGPU: FakeWebGPU,
  webGL: FakeWebGL,
  supported: () => Promise<boolean> = async () => true,
) {
  const createWebGPU = vi.fn(
    (...args: Parameters<
      BabylonEngineFactoryDependencies<FakeWebGPU, FakeWebGL>['createWebGPU']
    >) => {
      void args;
      return webGPU;
    },
  );
  const createWebGL = vi.fn(
    (...args: Parameters<
      BabylonEngineFactoryDependencies<FakeWebGPU, FakeWebGL>['createWebGL']
    >) => {
      void args;
      return webGL;
    },
  );
  const result: BabylonEngineFactoryDependencies<FakeWebGPU, FakeWebGL> = {
    isWebGPUSupported: supported,
    createWebGPU,
    createWebGL,
  };
  return { result, createWebGPU, createWebGL };
}

describe('Babylon browser engine selection', () => {
  it('initializes and truthfully reports WebGPU when it succeeds', async () => {
    const webGPU = new FakeWebGPU();
    const webGL = new FakeWebGL();
    const factory = dependencies(webGPU, webGL);
    const init = vi.spyOn(webGPU, 'initAsync');

    const selection = await createBabylonEngine(
      document.createElement('canvas'),
      {},
      factory.result,
    );

    expect(selection).toEqual({ engine: webGPU, backend: 'webgpu' });
    expect(init).toHaveBeenCalledOnce();
    expect(factory.createWebGL).not.toHaveBeenCalled();
    expect(webGPU.disposed).toBe(0);
  });

  it('uses WebGL directly when WebGPU is unsupported', async () => {
    const webGPU = new FakeWebGPU();
    const webGL = new FakeWebGL();
    const factory = dependencies(webGPU, webGL, async () => false);

    const selection = await createBabylonEngine(
      document.createElement('canvas'),
      {},
      factory.result,
    );

    expect(selection).toEqual({ engine: webGL, backend: 'webgl' });
    expect(factory.createWebGPU).not.toHaveBeenCalled();
    expect(factory.createWebGL).toHaveBeenCalledOnce();
  });

  it('disposes a failed WebGPU candidate before falling back to WebGL', async () => {
    const webGPU = new FakeWebGPU(new Error('adapter lost'));
    const webGL = new FakeWebGL();
    const factory = dependencies(webGPU, webGL);

    const selection = await createBabylonEngine(
      document.createElement('canvas'),
      {},
      factory.result,
    );

    expect(selection).toEqual({ engine: webGL, backend: 'webgl' });
    expect(webGPU.disposed).toBe(1);
    expect(factory.createWebGL).toHaveBeenCalledOnce();
  });

  it('falls back when capability probing rejects and never fabricates a null backend', async () => {
    const webGPU = new FakeWebGPU();
    const webGL = new FakeWebGL();
    const factory = dependencies(webGPU, webGL, async () => {
      throw new Error('probe failed');
    });

    const selection = await createBabylonEngine(
      document.createElement('canvas'),
      {},
      factory.result,
    );

    expect(selection.backend).toBe('webgl');
    expect(selection.engine).toBe(webGL);
    expect(factory.createWebGPU).not.toHaveBeenCalled();
  });

  it('forwards CSP-safe local options with adaptive device scaling disabled', async () => {
    const webGPU = new FakeWebGPU();
    const webGL = new FakeWebGL();
    const factory = dependencies(webGPU, webGL, async () => false);
    const canvas = document.createElement('canvas');

    await createBabylonEngine(
      canvas,
      {
        antialias: true,
        powerPreference: 'low-power',
        stencil: true,
      },
      factory.result,
    );

    expect(factory.createWebGL).toHaveBeenCalledWith(
      canvas,
      true,
      expect.objectContaining({
        adaptToDeviceRatio: false,
        audioEngine: false,
        loseContextOnDispose: true,
        powerPreference: 'low-power',
        preserveDrawingBuffer: false,
        stencil: true,
      }),
      false,
    );
    const engineOptions = factory.createWebGL.mock.calls[0][2];
    expect(Object.keys(engineOptions)).not.toContain('scriptUrl');
    expect(Object.keys(engineOptions)).not.toContain('wasmPath');
  });

  it('propagates WebGL creation failure instead of returning a non-rendering engine', async () => {
    const webGPU = new FakeWebGPU();
    const factory: BabylonEngineFactoryDependencies<FakeWebGPU, FakeWebGL> = {
      isWebGPUSupported: async () => false,
      createWebGPU: () => webGPU,
      createWebGL: () => {
        throw new Error('WebGL unavailable');
      },
    };

    await expect(
      createBabylonEngine(document.createElement('canvas'), {}, factory),
    ).rejects.toThrow('WebGL unavailable');
  });
});
