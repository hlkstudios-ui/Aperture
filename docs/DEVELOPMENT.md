# Development

## Toolchain

- Node.js: 24 or newer; `.nvmrc` selects the active Node 24 LTS line.
- Python: 3.12.
- PostgreSQL: 17.
- Redis: 8.
- MinIO: local S3-compatible development storage.

## Intended Local Endpoints

- Customer UI: <http://localhost:3000>
- Admin Studio: <http://localhost:3000/studio>
- API: <http://localhost:8001>
- API documentation: <http://localhost:8001/docs>
- MinIO console: <http://localhost:9101>

## Installation

From the repository root:

```sh
PATH=/opt/homebrew/bin:$PATH npm install
python3 -m venv .venv
.venv/bin/pip install -e 'apps/api[dev]'
# Only when the ignored root .env does not exist:
deploy/staging/generate-env.sh
```

Local development and isolated staging currently share this one root `.env`. The generator
copies `.env.example`, creates fresh local secrets, and refuses to overwrite existing values.

Local stateful dependencies on this workstation were installed with:

```sh
brew install postgresql@17 redis minio
```

## Verified Commands

Frontend:

```sh
PATH=/opt/homebrew/bin:$PATH npm run dev:web
PATH=/opt/homebrew/bin:$PATH npm run typecheck:web
PATH=/opt/homebrew/bin:$PATH npm run lint:web
PATH=/opt/homebrew/bin:$PATH npm run test:web
E2E_ENV_FILE=/absolute/path/to/aperture.e2e.env PATH=/opt/homebrew/bin:$PATH npm run test:e2e
PATH=/opt/homebrew/bin:$PATH npm run build:web
```

The Playwright configuration covers Chromium at common mobile, tablet, laptop, and 1920×1080 profiles plus desktop Firefox and WebKit/Safari-compatible engines. It fails on unexpected browser console/page errors or failed requests and stores screenshots/traces under `test-results/playwright`.

Browser tests require the disposable-resource contract in
[E2E_TESTING.md](E2E_TESTING.md); they never reuse the shared development stack.

Production-like isolated staging and recovery:

```sh
# Run generate-env.sh first only when the root .env is missing.
deploy/staging/verify.sh
deploy/staging/backup.sh /absolute/restricted/backup-directory
deploy/staging/restore-test.sh
```

Inside the API release image, production operators can run the secret-safe read-only preflight after injecting owner-approved production configuration:

```sh
python scripts/production_preflight.py --configuration-only
alembic upgrade head
python scripts/production_preflight.py
```

The full operator contract and required evidence are in `deploy/production/README.md` and `docs/PRODUCTION_HANDOFF.md`. These commands deliberately fail against development/staging settings and do not provision production infrastructure.

Once the first production baseline is accepted, the push-to-live developer and operator flow is
documented in [`CONTINUOUS_DEPLOYMENT.md`](CONTINUOUS_DEPLOYMENT.md).

`verify.sh` intentionally runs the full staging acceptance on Chromium desktop/mobile. Representative cross-browser and responsive checks use the configured projects, while generated-player acceptance can be targeted with:

```sh
npx playwright test tests/e2e/foundation.spec.ts tests/e2e/accessibility-i18n.spec.ts
npx playwright test tests/e2e/player-resume.spec.ts --project=desktop-firefox --project=desktop-webkit
```

API, migrations, and tests:

```sh
cd apps/api
../../.venv/bin/alembic upgrade head
../../.venv/bin/alembic current
../../.venv/bin/alembic check
../../.venv/bin/ruff check .
../../.venv/bin/pytest
../../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Seed the minimal original development catalog idempotently:

```sh
cd apps/api
../../.venv/bin/python scripts/seed_catalog.py
```

The seed command refuses staging/production environments and does not represent production catalog completion.

Provision or rotate the single local administrator interactively (never put its password in source control or a migration):

```sh
cd apps/api
../../.venv/bin/python scripts/provision_admin.py --email your-admin@example.com
```

The native Redis service configuration on this machine references absent optional modules. For this development run, Redis is started explicitly with the packaged server and a minimal local-only configuration:

```sh
/opt/homebrew/opt/redis/bin/redis-server --bind 127.0.0.1 --port 6380 --save '' --appendonly no
```

MinIO can be started from the repository root with the credentials in the single root `.env`:

```sh
docker compose --env-file .env -f docker-compose.dev.yml up -d minio
```

## Media Policy

Development media must be user-owned, public-domain, licensed, or explicitly authorized. Commercial copyrighted movies must not be committed to the repository.
