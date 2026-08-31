import {
  validateE2EConfiguration,
  verifyApiRuntimeIdentity,
  verifyWebRuntimeIdentity,
} from './safety';

const IDENTITY_ATTEMPTS = 10;
const IDENTITY_RETRY_MS = 250;

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function fetchIdentity(
  url: URL,
  runId: string,
  ownerToken: string,
  label: string,
): Promise<unknown> {
  let lastFailure = 'no response';

  for (let attempt = 1; attempt <= IDENTITY_ATTEMPTS; attempt += 1) {
    try {
      const response = await fetch(url, {
        headers: {
          'X-Aperture-E2E-Owner': ownerToken,
          'X-Aperture-E2E-Run': runId,
        },
        signal: AbortSignal.timeout(1_000),
      });
      if (!response.ok) {
        lastFailure = `HTTP ${response.status}`;
      } else {
        return await response.json();
      }
    } catch (error) {
      lastFailure = error instanceof Error ? error.message : String(error);
    }
    if (attempt < IDENTITY_ATTEMPTS) await delay(IDENTITY_RETRY_MS);
  }

  throw new Error(`Refusing browser tests: ${label} ${url} was not verified (${lastFailure}).`);
}

export default async function globalSetup(): Promise<void> {
  const configuration = validateE2EConfiguration();
  const apiIdentityUrl = new URL('/__test__/runtime-identity', configuration.apiOrigin);
  const webIdentityUrl = new URL(
    '/api/__test__/runtime-identity',
    configuration.baseURL,
  );

  const apiIdentity = verifyApiRuntimeIdentity(
    await fetchIdentity(
      apiIdentityUrl,
      configuration.runId,
      configuration.ownerToken,
      'API identity',
    ),
    configuration,
  );
  verifyWebRuntimeIdentity(
    await fetchIdentity(
      webIdentityUrl,
      configuration.runId,
      configuration.ownerToken,
      'web identity',
    ),
    configuration,
    apiIdentity,
  );
}
