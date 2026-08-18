# Development

## Toolchain

- Node.js: 20.19 or newer; `.nvmrc` selects Node 22. The installed Homebrew Node 23.9 runtime has been verified locally.
- Python: 3.12.
- PostgreSQL: 17.
- Redis: 8.
- MinIO: local S3-compatible development storage.

## Intended Local Endpoints

- Customer UI: <http://localhost:3000>
- Admin Studio: <http://localhost:3000/studio>
- API: <http://localhost:8000>
- API documentation: <http://localhost:8000/docs>
- MinIO console: <http://localhost:9001>

## Installation

From the repository root:

```sh
PATH=/opt/homebrew/bin:$PATH npm install
python3 -m venv .venv
.venv/bin/pip install -e 'apps/api[dev]'
```

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
PATH=/opt/homebrew/bin:$PATH npm run test:e2e
PATH=/opt/homebrew/bin:$PATH npm run build:web
```

The Playwright configuration covers Chromium at common mobile, tablet, laptop, and 1920×1080 profiles plus desktop Firefox and WebKit/Safari-compatible engines. It fails on unexpected browser console/page errors or failed requests and stores screenshots/traces under `test-results/playwright`.

Production-like isolated staging and recovery:

```sh
deploy/staging/generate-env.sh
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
../../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
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
/opt/homebrew/opt/redis/bin/redis-server --bind 127.0.0.1 --port 6379 --save '' --appendonly no
```

MinIO is started from the repository root with development-only credentials matching `.env.example`:

```sh
mkdir -p data/minio
MINIO_ROOT_USER=replace_for_local_development MINIO_ROOT_PASSWORD=replace_for_local_development minio server data/minio --address 127.0.0.1:9000 --console-address 127.0.0.1:9001
```

## Media Policy

Development media must be user-owned, public-domain, licensed, or explicitly authorized. Commercial copyrighted movies must not be committed to the repository.
