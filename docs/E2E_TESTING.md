# Isolated browser testing

Browser acceptance tests are intentionally fail-closed. They no longer start or reuse the
shared `localhost:3000` development UI, and their database helpers refuse `development` even
when a fixture happens to use an `e2e-` prefix.

## Required isolated stack

Start a separate API and web process with a disposable PostgreSQL database, an isolated Redis
logical database, an isolated S3 bucket, and non-development ports. Use one lowercase run ID to
name both mutable resources:

- PostgreSQL database: `aperture_e2e_<run_id_with_underscores>`
- S3 bucket: `aperture-e2e-<run-id>`
- Redis logical database: 14 (reserved for E2E; pytest independently owns 15)
- Web port: anything except 3000
- API port: anything except 8000 or 8001

PostgreSQL, Redis, and S3 endpoints must be loopback-only. Apply migrations to the disposable
database and create the disposable bucket before starting the stack. Both processes must receive
the same test environment, including
`STUDIO_DEV_AUTO_LOGIN=false`.

The npm wrapper is the lifecycle owner for Redis DB14. Immediately before Playwright starts it
generates a one-run secret and atomically claims an empty DB14. It refuses both a different
owner (including another concurrent E2E run) and any non-empty database without a valid owner
record. On exit, it atomically verifies the same secret before flushing and releasing DB14.
Neither the wrapper nor the tests will guess that ownerless keys are disposable.

Before launching a browser, Playwright performs a two-hop runtime identity handshake:

1. The test-only API endpoint reports the database returned by PostgreSQL, the configured S3
   bucket, Redis database, run ID, and API origin actually bound by that API process.
2. A same-origin web endpoint calls its configured API and reports the server-only
   `API_ORIGIN` used as the gateway target.

Every value must match the environment file exactly. Both endpoints require the run-specific
header and the wrapper's Redis-owner secret, disable caching, and are unavailable outside
`APP_ENV=test`. Stateful Python fixture helpers independently verify that same live owner before
they can mutate the database.

The committed [environment template](../tests/e2e/e2e.env.example) documents every safety
variable without containing usable credentials. Keep the populated copy outside source control.

## Run Playwright

Pass the populated environment file to the cross-platform Node wrapper:

```sh
E2E_ENV_FILE=/absolute/path/to/aperture.e2e.env npm run test:e2e
```

PowerShell uses the same wrapper:

```powershell
$env:E2E_ENV_FILE = "C:\secure\aperture.e2e.env"
npm run test:e2e
```

Playwright arguments are forwarded normally:

```sh
npm run test:e2e -- tests/e2e/foundation.spec.ts --project=desktop-chromium
```

`E2E_BROWSER_EXECUTABLE` remains available to specs that select an installed browser binary.
Calling `npx playwright test` directly is deliberately refused because it cannot acquire the
Redis owner lifecycle. Always use `npm run test:e2e`.

## Recover a dead local owner

If the wrapper was forcibly killed, DB14 remains fenced rather than being wiped speculatively.
First confirm that no browser-test wrapper is still running. Then opt into a single reclaim:

```sh
E2E_RECLAIM_DEAD_OWNER=1 E2E_ENV_FILE=/absolute/path/to/aperture.e2e.env npm run test:e2e
```

```powershell
$env:E2E_RECLAIM_DEAD_OWNER = "1"
$env:E2E_ENV_FILE = "C:\secure\aperture.e2e.env"
npm run test:e2e
Remove-Item Env:E2E_RECLAIM_DEAD_OWNER
```

Reclaim succeeds only when the owner record names this host and its recorded PID is proven dead;
an active PID or a record from another host is refused. An ownerless DB14 containing unknown keys
is never auto-reclaimed: inspect that Redis instance manually and resolve its provenance before
clearing it outside the E2E tooling.
