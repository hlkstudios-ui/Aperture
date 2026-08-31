#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const environmentFile = process.env.E2E_ENV_FILE?.trim();

if (environmentFile) {
  const absoluteEnvironmentFile = resolve(repositoryRoot, environmentFile);
  if (!existsSync(absoluteEnvironmentFile)) {
    console.error(`E2E_ENV_FILE does not exist: ${absoluteEnvironmentFile}`);
    process.exit(2);
  }
  process.loadEnvFile(absoluteEnvironmentFile);
}

function pythonExecutable() {
  if (process.env.E2E_PYTHON_EXECUTABLE?.trim()) {
    return process.env.E2E_PYTHON_EXECUTABLE.trim();
  }
  const candidates = process.platform === 'win32'
    ? [
        resolve(repositoryRoot, '.venv', 'Scripts', 'python.exe'),
        resolve(repositoryRoot, 'apps', 'api', '.venv', 'Scripts', 'python.exe'),
        resolve(repositoryRoot, 'apps', 'api', 'venv', 'Scripts', 'python.exe'),
      ]
    : [
        resolve(repositoryRoot, '.venv', 'bin', 'python'),
        resolve(repositoryRoot, 'apps', 'api', '.venv', 'bin', 'python'),
        resolve(repositoryRoot, 'apps', 'api', 'venv', 'bin', 'python'),
      ];
  return candidates.find((candidate) => existsSync(candidate)) ??
    (process.platform === 'win32' ? 'python' : 'python3');
}

function waitFor(command, args, options) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, options);
    child.once('error', reject);
    child.once('exit', (code, signal) => resolvePromise({ code, signal }));
  });
}

const ownerToken = randomBytes(32).toString('hex');
const childEnvironment = {
  ...process.env,
  E2E_OWNER_PID: String(process.pid),
  E2E_OWNER_TOKEN: ownerToken,
  NODE_ENV: 'test',
};
const ownerScript = resolve(repositoryRoot, 'apps', 'api', 'scripts', 'e2e_redis_owner.py');
const python = pythonExecutable();
const acquireArguments = [ownerScript, 'acquire'];
if (process.env.E2E_RECLAIM_DEAD_OWNER === '1') {
  acquireArguments.push('--reclaim-dead-local');
}

let acquired = false;
let exitCode = 1;
try {
  const acquisition = await waitFor(python, acquireArguments, {
    cwd: resolve(repositoryRoot, 'apps', 'api'),
    env: childEnvironment,
    stdio: 'inherit',
    windowsHide: true,
  });
  if (acquisition.signal || acquisition.code !== 0) {
    process.exitCode = acquisition.code ?? 2;
  } else {
    acquired = true;
    const require = createRequire(import.meta.url);
    const playwrightCli = require.resolve('@playwright/test/cli');
    const playwright = spawn(
      process.execPath,
      [playwrightCli, 'test', ...process.argv.slice(2)],
      {
        cwd: repositoryRoot,
        env: childEnvironment,
        stdio: 'inherit',
        windowsHide: true,
      },
    );
    for (const signal of ['SIGINT', 'SIGTERM']) {
      process.on(signal, () => playwright.kill(signal));
    }
    const result = await new Promise((resolvePromise, reject) => {
      playwright.once('error', reject);
      playwright.once('exit', (code, signal) => resolvePromise({ code, signal }));
    });
    if (result.signal) {
      console.error(`Playwright stopped after ${result.signal}.`);
      exitCode = 1;
    } else {
      exitCode = result.code ?? 1;
    }
  }
} catch (error) {
  console.error(`Unable to run isolated browser tests: ${error.message}`);
  exitCode = 2;
  process.exitCode = 2;
} finally {
  if (acquired) {
    try {
      const release = await waitFor(python, [ownerScript, 'release'], {
        cwd: resolve(repositoryRoot, 'apps', 'api'),
        env: childEnvironment,
        stdio: 'inherit',
        windowsHide: true,
      });
      if (release.signal || release.code !== 0) {
        console.error('E2E Redis owner release failed; DB14 remains fenced.');
        exitCode = 2;
      }
    } catch (error) {
      console.error(`Unable to release the E2E Redis owner: ${error.message}`);
      exitCode = 2;
    }
  }
}

if (acquired) process.exitCode = exitCode;
