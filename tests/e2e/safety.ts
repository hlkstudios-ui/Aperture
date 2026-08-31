import { createHash } from 'node:crypto';

const RUN_ID_PATTERN = /^[a-z0-9][a-z0-9-]{6,38}[a-z0-9]$/;
const OWNER_TOKEN_PATTERN = /^[a-f0-9]{64}$/;

type E2EEnvironment = Readonly<Record<string, string | undefined>>;

export type SafeE2EConfiguration = {
  apiOrigin: string;
  baseURL: string;
  databaseName: string;
  ownerToken: string;
  ownerTokenHash: string;
  redisDatabase: number;
  runId: string;
  s3Bucket: string;
};

export type ApiRuntimeIdentity = {
  environment: 'test';
  run_id: string;
  database_name: string;
  s3_bucket: string;
  redis_database: number;
  redis_owner_token_sha256: string;
  api_origin: string;
};

export type WebRuntimeIdentity = {
  environment: 'test';
  run_id: string;
  web_origin: string;
  gateway_target_origin: string;
  upstream: ApiRuntimeIdentity;
};

function required(environment: E2EEnvironment, name: string): string {
  const value = environment[name]?.trim();
  if (!value) {
    throw new Error(
      `${name} is required. Browser tests only run against an explicitly configured isolated test stack.`,
    );
  }
  return value;
}

function parseOrigin(environment: E2EEnvironment, name: string): URL {
  const value = required(environment, name);
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} must be an absolute http(s) URL.`);
  }
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error(`${name} must be an absolute http(s) URL without credentials.`);
  }
  if (parsed.pathname !== '/' || parsed.search || parsed.hash) {
    throw new Error(`${name} must be an origin without a path, query, or fragment.`);
  }
  return parsed;
}

function isLoopback(hostname: string): boolean {
  const normalized = hostname
    .toLowerCase()
    .replace(/\.$/, '')
    .replace(/^\[/, '')
    .replace(/\]$/, '');
  return (
    normalized === 'localhost' ||
    normalized === '::1' ||
    /^127(?:\.\d{1,3}){3}$/.test(normalized)
  );
}

function rejectDevelopmentPort(url: URL, name: string, ports: ReadonlySet<string>): void {
  if (ports.has(url.port)) {
    throw new Error(
      `${name} points at Aperture's shared development port ${url.port}; use a dedicated E2E port.`,
    );
  }
}

function databaseName(databaseUrl: string): string {
  let parsed: URL;
  try {
    parsed = new URL(databaseUrl);
  } catch {
    throw new Error('DATABASE_URL must be an absolute PostgreSQL URL for the isolated E2E database.');
  }
  if (!['postgresql:', 'postgresql+psycopg:'].includes(parsed.protocol)) {
    throw new Error('DATABASE_URL must use PostgreSQL for browser tests.');
  }
  if (!isLoopback(parsed.hostname)) {
    throw new Error('DATABASE_URL must use a loopback PostgreSQL host.');
  }
  return decodeURIComponent(parsed.pathname.replace(/^\//, ''));
}

function redisDatabase(redisUrl: string): number {
  let parsed: URL;
  try {
    parsed = new URL(redisUrl);
  } catch {
    throw new Error('REDIS_URL must be an absolute Redis URL for the isolated E2E cache.');
  }
  if (!['redis:', 'rediss:'].includes(parsed.protocol)) {
    throw new Error('REDIS_URL must use the redis or rediss protocol.');
  }
  if (!isLoopback(parsed.hostname)) {
    throw new Error('REDIS_URL must use a loopback Redis host.');
  }
  if (parsed.search || parsed.hash) {
    throw new Error('REDIS_URL cannot contain a query or fragment that overrides database 14.');
  }
  const value = parsed.pathname.replace(/^\//, '');
  if (!/^\d+$/.test(value)) {
    throw new Error('REDIS_URL must select an explicit logical database from 1 through 15.');
  }
  return Number.parseInt(value, 10);
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function verifyApiRuntimeIdentity(
  value: unknown,
  configuration: SafeE2EConfiguration,
): ApiRuntimeIdentity {
  if (!record(value)) {
    throw new Error('API runtime identity is not a JSON object.');
  }

  const mismatches: string[] = [];
  if (value.environment !== 'test') mismatches.push('environment');
  if (value.run_id !== configuration.runId) mismatches.push('run id');
  if (value.database_name !== configuration.databaseName) mismatches.push('database');
  if (value.s3_bucket !== configuration.s3Bucket) mismatches.push('S3 bucket');
  if (value.redis_database !== configuration.redisDatabase) mismatches.push('Redis database');
  if (value.redis_owner_token_sha256 !== configuration.ownerTokenHash) {
    mismatches.push('Redis owner token');
  }
  if (value.api_origin !== configuration.apiOrigin) mismatches.push('API origin');
  if (mismatches.length > 0) {
    throw new Error(`API runtime identity mismatch: ${mismatches.join(', ')}.`);
  }

  return {
    environment: 'test',
    run_id: configuration.runId,
    database_name: configuration.databaseName,
    s3_bucket: configuration.s3Bucket,
    redis_database: configuration.redisDatabase,
    redis_owner_token_sha256: configuration.ownerTokenHash,
    api_origin: configuration.apiOrigin,
  };
}

export function verifyWebRuntimeIdentity(
  value: unknown,
  configuration: SafeE2EConfiguration,
  directApiIdentity: ApiRuntimeIdentity,
): WebRuntimeIdentity {
  if (!record(value)) {
    throw new Error('Web runtime identity is not a JSON object.');
  }

  const mismatches: string[] = [];
  if (value.environment !== 'test') mismatches.push('environment');
  if (value.run_id !== configuration.runId) mismatches.push('run id');
  if (value.web_origin !== configuration.baseURL) mismatches.push('web origin');
  if (value.gateway_target_origin !== configuration.apiOrigin) {
    mismatches.push('gateway target origin');
  }
  if (mismatches.length > 0) {
    throw new Error(`Web runtime identity mismatch: ${mismatches.join(', ')}.`);
  }

  const upstream = verifyApiRuntimeIdentity(value.upstream, configuration);
  if (
    upstream.run_id !== directApiIdentity.run_id ||
    upstream.database_name !== directApiIdentity.database_name ||
    upstream.s3_bucket !== directApiIdentity.s3_bucket ||
    upstream.redis_database !== directApiIdentity.redis_database ||
    upstream.redis_owner_token_sha256 !== directApiIdentity.redis_owner_token_sha256 ||
    upstream.api_origin !== directApiIdentity.api_origin
  ) {
    throw new Error('Web runtime identity mismatch: upstream API identity.');
  }

  return {
    environment: 'test',
    run_id: configuration.runId,
    web_origin: configuration.baseURL,
    gateway_target_origin: configuration.apiOrigin,
    upstream,
  };
}

export function validateE2EConfiguration(
  environment: E2EEnvironment = process.env,
): SafeE2EConfiguration {
  if (required(environment, 'APP_ENV') !== 'test') {
    throw new Error('Browser tests require APP_ENV=test; development and staging stacks are refused.');
  }
  if (required(environment, 'STUDIO_DEV_AUTO_LOGIN').toLowerCase() !== 'false') {
    throw new Error('Browser tests require STUDIO_DEV_AUTO_LOGIN=false.');
  }

  const runId = required(environment, 'E2E_RUN_ID');
  if (!RUN_ID_PATTERN.test(runId)) {
    throw new Error(
      'E2E_RUN_ID must contain 8-40 lowercase letters, digits, or hyphens and have alphanumeric ends.',
    );
  }

  const ownerToken = required(environment, 'E2E_OWNER_TOKEN');
  if (!OWNER_TOKEN_PATTERN.test(ownerToken)) {
    throw new Error('E2E_OWNER_TOKEN must be the 64-character secret generated by the E2E wrapper.');
  }

  const baseURL = parseOrigin(environment, 'E2E_BASE_URL');
  const apiOrigin = parseOrigin(environment, 'E2E_API_ORIGIN');
  rejectDevelopmentPort(baseURL, 'E2E_BASE_URL', new Set(['3000']));
  rejectDevelopmentPort(apiOrigin, 'E2E_API_ORIGIN', new Set(['8000', '8001']));

  const expectedDatabase = `aperture_e2e_${runId.replaceAll('-', '_')}`;
  if (databaseName(required(environment, 'DATABASE_URL')) !== expectedDatabase) {
    throw new Error(`DATABASE_URL must target the isolated ${expectedDatabase} database.`);
  }

  const expectedBucket = `aperture-e2e-${runId}`;
  if (required(environment, 'S3_BUCKET') !== expectedBucket) {
    throw new Error(`S3_BUCKET must be the isolated ${expectedBucket} bucket.`);
  }

  const redisDb = redisDatabase(required(environment, 'REDIS_URL'));
  if (redisDb !== 14) {
    throw new Error('REDIS_URL must select E2E-reserved logical database 14.');
  }

  const s3Endpoint = parseOrigin(environment, 'S3_ENDPOINT');
  if (!isLoopback(s3Endpoint.hostname)) {
    throw new Error('S3_ENDPOINT must use a loopback object-storage host.');
  }

  return {
    apiOrigin: apiOrigin.origin,
    baseURL: baseURL.origin,
    databaseName: expectedDatabase,
    ownerToken,
    ownerTokenHash: createHash('sha256').update(ownerToken).digest('hex'),
    redisDatabase: redisDb,
    runId,
    s3Bucket: expectedBucket,
  };
}
