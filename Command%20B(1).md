# COMMAND B — CODEX EXECUTION, DEVELOPMENT, TESTING, AND DELIVERY PROTOCOL

## 0. Mission

Execute **Command A** faithfully and incrementally.

Command A defines **what the product must become**.

Command B defines **how Codex must build it without damaging the project**.

This project must be developed as a real integrated application, not as isolated demos.

The frontend, backend, database, media processing, Admin Studio, customer experience, and intelligence features must evolve together.

---

# 1. First Rule: Audit Before Editing

Before creating or changing architecture:

1. inspect the repository root;
2. inspect source directories;
3. inspect configuration files;
4. inspect package/dependency files;
5. inspect Docker/dev-container files;
6. inspect environment examples;
7. inspect database schema/migrations;
8. inspect tests;
9. inspect CI configuration;
10. inspect existing documentation;
11. inspect unfinished branches/modules/TODO markers where visible in the working tree;
12. determine what is already functional;
13. determine what is broken;
14. determine what is missing.

If necessary, read every relevant source file.

Do not assume the repository is greenfield.

Do not overwrite established architecture merely because another stack is preferred.

---

# 2. Create a Project State Ledger

Create/update:

`docs/BUILD_STATUS.md`

It must contain:

- current phase,
- current stage,
- completed capabilities,
- partially completed capabilities,
- known defects,
- blocked items,
- database migration status,
- test status,
- live-server status,
- frontend URL,
- admin URL,
- backend URL,
- currently running services,
- next exact implementation step,
- production-readiness gaps.

Also maintain:

`docs/CHANGELOG.md`

Every meaningful implementation batch must update these files.

---

# 3. Mandatory Live-Development Environment

The website must be viewable while it is being developed.

## 3.1 Establish This Early

After repository audit, get the application running as soon as possible.

Target development endpoints unless repository conventions already define alternatives:

```text
Customer UI: http://localhost:3000
Admin Studio: http://localhost:3000/studio
API: http://localhost:8000
API Docs: http://localhost:8000/docs
```

## 3.2 Hot Reload

Enable:
- frontend hot module reload,
- backend auto reload,
- CSS/component live refresh,
- safe worker restart strategy where possible.

## 3.3 Keep the Development Stack Alive

Once working, do not repeatedly tear down the whole stack for ordinary code edits.

Only restart the required component when:
- dependency changes require it,
- database migrations require it,
- infrastructure changes require it,
- the process becomes unhealthy.

## 3.4 Live Verification Is Mandatory

After every UI implementation batch:

1. ensure services are running;
2. load the actual page;
3. interact with the feature;
4. check browser console;
5. inspect failed requests;
6. verify mobile/desktop at relevant milestones;
7. run targeted end-to-end test;
8. record success/failure in `BUILD_STATUS.md`.

A UI component is not finished just because TypeScript compiles.

---

# 4. Preferred Local Development Topology

If the existing repository does not already provide equivalent infrastructure, use a development topology similar to:

```text
Frontend
  └─ Next.js/React dev server :3000

Backend
  └─ FastAPI/Uvicorn reload :8000

PostgreSQL
  └─ Docker

Redis
  └─ Docker

S3-compatible storage
  └─ MinIO or equivalent local object storage

Media Worker
  └─ Python worker + FFmpeg

Optional AI/Index Worker
  └─ Python worker

Optional Reverse Proxy
  └─ only when useful
```

Use Docker Compose for stateful local dependencies when appropriate.

Do not containerize everything merely for aesthetics if it materially harms hot reload or developer productivity.

---

# 5. Greenfield Stack Preference

Only if the repository is effectively greenfield or the existing architecture clearly cannot support Command A:

## Frontend
- TypeScript
- React
- current stable Next.js or equivalent
- accessible component primitives
- strongly typed API client

## Backend
- Python
- current stable FastAPI or equivalent
- Pydantic/typed schemas
- SQLAlchemy or equivalent mature ORM
- Alembic or equivalent migrations

## Database
- PostgreSQL

## Cache/Queue
- Redis

## Jobs
- reliable Python background worker
- retries
- dead-letter/failure state
- idempotency

## Media
- FFmpeg / ffprobe

## Object Storage
- S3-compatible storage

## Test
- pytest
- frontend unit/component tests
- Playwright for browser E2E

Do not lock to a dependency version without checking the repository and compatibility first.

---

# 6. Preserve Project Integrity

For every change:

- make the smallest coherent change set;
- preserve existing public interfaces unless migration is intentional;
- do not rename large areas without reason;
- do not perform broad formatting unrelated to the task;
- do not remove tests to make a build pass;
- do not weaken types;
- do not silence exceptions globally;
- do not replace working implementations with mocks;
- do not introduce duplicate services that solve the same problem.

When architecture must change, document:
- why,
- migration steps,
- compatibility impact,
- rollback path.

---

# 7. Work Phase by Phase

Execute phases in the order defined in Command A unless a dependency requires a small reordering.

Do not jump straight to advanced AI features before:
- catalog,
- player,
- progress,
- media pipeline,
- authentication,
- scene data model,
- and spoiler-boundary infrastructure exist.

---

# 8. Execution Loop for Every Stage

For every stage, use this exact control loop:

## Step A — Inspect
Identify existing code and dependencies related to the stage.

## Step B — Plan
Write a short implementation plan into the working notes/status file.

## Step C — Implement
Change the smallest necessary set of files.

## Step D — Migrate
Run/create required schema migrations.

## Step E — Test
Run:
- targeted unit tests,
- targeted integration tests,
- static/type checks,
- lint if configured.

## Step F — Run
Bring affected services up.

## Step G — Browser Verify
Verify the actual running application.

## Step H — Record
Update:
- `docs/BUILD_STATUS.md`
- `docs/CHANGELOG.md`

## Step I — Gate
Do not advance if the phase acceptance criteria fail.

---

# 9. Phase 0 — Repository Audit and Control Package

## Objective
Understand the codebase completely enough to modify it safely.

## Required Outputs
Create/update:

- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT.md`
- `docs/BUILD_STATUS.md`
- `docs/PRODUCT_DECISIONS.md`
- `docs/CHANGELOG.md`
- `.env.example`

## Audit Checklist
Document:
- frontend framework,
- backend framework,
- language versions,
- package managers,
- database,
- migrations,
- storage,
- auth,
- player,
- media tooling,
- jobs,
- tests,
- current routes,
- existing Admin Studio,
- existing UI design system,
- deployment files,
- known failures.

## Gate
Do not begin broad implementation until the repository architecture and current state are documented.

---

# 10. Phase 1 — Live Foundation

## Objective
Create a durable development environment and visible running shell.

## Requirements
- customer shell renders;
- `/studio` renders;
- API health endpoint works;
- DB connection works;
- Redis connection works if used;
- object storage connection works if used;
- migrations work;
- environment validation exists;
- frontend/backend hot reload works;
- logs are readable.

## Customer Shell
Must contain:
- global page structure,
- navigation placeholder wired to real routes,
- responsive layout,
- design-system foundation.

## Studio Shell
Must contain:
- secure route boundary stub or real auth if already available,
- sidebar/header structure,
- dashboard route.

## Gate
Open both:
- `/`
- `/studio`

Verify live.

Record the URLs in `BUILD_STATUS.md`.

---

# 11. Phase 2 — Authentication, Admin Provisioning, and Profiles

## Customer Auth
Implement according to project requirements:
- register if public signup is intended,
- login,
- logout,
- password reset,
- secure sessions.

## Single Administrator
Create secure provisioning mechanism.

There must be **no public admin signup**.

Admin access must be checked server-side.

Prepare MFA support; implement it before production.

## Profiles
Implement:
- profile create/edit/delete,
- avatar,
- maturity setting architecture,
- language,
- playback/subtitle preferences.

## Tests
- customer login,
- profile switching,
- unauthorized Studio blocked,
- admin login success,
- normal user cannot call admin APIs.

---

# 12. Phase 3 — Catalog Domain

Implement real persistent models for:

- Movie
- Series
- Season
- Episode
- Edition
- Person
- Character
- Credit
- Company
- Franchise
- Genre
- Theme
- Tag
- Language
- Country
- Artwork
- Trailer/Clip metadata

Create:
- migrations,
- indexes,
- constraints,
- API schemas,
- services,
- admin CRUD endpoints,
- customer read endpoints.

Seed only development/demo content necessary to test.

Do not confuse seed data with production completion.

---

# 13. Phase 4 — Customer Catalog UI

Build real pages using backend data.

## Home
- hero,
- rails,
- content cards,
- loading states,
- empty states,
- error states.

## Movie
- full metadata,
- credits,
- related titles,
- Play/Resume,
- My List.

## Series
- season selector,
- episode list,
- progress,
- Play/Resume.

## Search
Initial:
- title,
- people,
- genre,
- tags.

Later expand to full Command A search model.

## Gate
Playwright must load these pages against the running stack.

No critical console errors.

---

# 14. Phase 5 — Admin Studio CMS

Build Admin Studio as a genuine operational product.

## Navigation
- Dashboard
- Content
- Movies
- Series
- Uploads
- Processing
- Collections
- Homepage
- Journeys
- Users
- Subscriptions
- Analytics
- Storage
- Settings

Hide unfinished items or label them clearly.

Do not create dead navigation that looks functional.

## Content Library
Implement:
- search,
- filters,
- statuses,
- edit,
- preview,
- publish controls.

## Movie Editor
Implement metadata and artwork sections.

## Series Editor
Implement:
- season creation,
- episode creation,
- ordering,
- bulk flow architecture.

## Gate
Admin can create a draft title from the browser and see it appear in the database/catalog preview.

---

# 15. Phase 6 — Upload System

## Large-File Flow
Prefer direct-to-object-storage or resumable upload architecture.

Implement:
- upload initialization,
- progress,
- completion,
- checksum/integrity,
- failure,
- retry/cancel where feasible,
- file validation.

## Storage
Organize assets by stable IDs, not unsafe user filenames.

Persist:
- asset id,
- original filename,
- media type,
- size,
- checksum,
- storage key,
- state,
- timestamps.

## Gate
Upload a permitted development test video through the Studio and verify it reaches object storage.

---

# 16. Phase 7 — Media Processing

Implement background processing:

1. probe source;
2. validate codecs/container;
3. extract metadata;
4. create renditions;
5. package HLS;
6. process audio;
7. process subtitles;
8. generate thumbnails;
9. generate preview sprites;
10. create duration/chapter data;
11. validate outputs;
12. mark Ready or Failed.

## Processing UI
Show:
- queue state,
- percentage/progress when calculable,
- source metadata,
- rendition status,
- errors,
- retry.

## Safety
Never expose local filesystem paths or raw storage credentials to the client.

## Gate
A development media file must complete the pipeline and produce a playable adaptive manifest.

---

# 17. Phase 8 — Production-Grade Player

Integrate the adaptive stream.

Implement:
- play/pause,
- seek,
- volume,
- fullscreen,
- PiP where supported,
- playback speed,
- quality,
- Auto,
- subtitles,
- audio tracks,
- next episode,
- skip intro/recap/credits data model,
- error states.

Persist progress efficiently.

## Gate
Browser test:
1. start title,
2. watch/seek,
3. leave,
4. return,
5. resume.

Test at least two renditions in development if source permits.

---

# 18. Phase 9 — Homepage Manager and Scheduling

## Homepage Manager
Admin can:
- set hero,
- create rail,
- select/query content,
- pin content,
- reorder,
- enable/disable,
- preview.

## Scheduling
Implement:
- publish now,
- publish later,
- unpublish later,
- rights window,
- timezone-safe server behavior.

## Gate
Change homepage layout from Studio and verify the customer homepage changes without source-code edits.

---

# 19. Phase 10 — Account and Subscription Architecture

Build:
- account dashboard,
- subscription state,
- plans,
- entitlements,
- device/session list,
- session revocation,
- billing-provider abstraction.

If payment integration is not yet configured:
- implement clean provider interface,
- use explicit development stub only in dev,
- label it as non-production.

Do not fake completed payments.

---

# 20. Phase 11 — Analytics Foundation

Create event pipeline for:
- impression,
- detail-open,
- play-start,
- progress,
- pause,
- seek,
- completion,
- search,
- search click,
- My List,
- rating,
- SceneLens open,
- Ask This Movie usage.

Avoid noisy unbounded writes.

Build aggregates for Studio.

## Gate
Play a test title and verify resulting events appear in analytics.

---

# 21. Phase 12 — Recommendations

Start with explainable recommender.

Implement:
- editorial,
- content similarity,
- watched exclusion rules,
- profile preference signals,
- popularity,
- cold start.

Recommendation response should include reason codes when relevant.

Do not pretend a machine-learning model exists if rules are being used.

---

# 22. Phase 13 — Movie Prescription and Taste DNA

## Taste DNA
Create a derived profile representation based on real user behavior.

## Movie Prescription
Build UI and API for:
- time,
- mood,
- pacing,
- intensity,
- genre,
- unwanted characteristics,
- language,
- release era,
- watched/unwatched.

Return:
- one best-fit movie,
- reason,
- match dimensions.

## Gate
Use seeded viewing history and verify different profiles receive meaningfully different results.

---

# 23. Phase 14 — Cinema Passport

Implement:
- watch statistics,
- favorite genres,
- favorite creators,
- country/decade distribution,
- first-watch vs rewatch,
- yearly report infrastructure.

All stats must derive from actual persisted viewing activity.

---

# 24. Phase 15 — Scene Intelligence Data Foundation

Do not begin with a chatbot.

First build structured scene data.

Models/services:
- Scene
- Chapter
- SceneCharacter
- SceneEntity
- SceneRelationship
- MusicCue
- ProductionNote
- SceneSource/Provenance
- SpoilerBoundary
- SceneIntelligenceVersion

Create enrichment job framework.

Support manual edits from Admin Studio.

---

# 25. Phase 16 — Scene Segmentation and Metadata Enrichment

For development test titles:

- ingest subtitles/transcript if legally available;
- detect/import scene boundaries;
- align timestamps;
- identify known characters only where confidence is adequate;
- create scene summaries;
- attach provenance;
- compute embeddings only if required;
- build searchable scene index.

Never guess missing filmmaking metadata.

---

# 26. Phase 17 — Spoiler Safety Engine

This must be implemented and tested before Ask This Movie ships.

## Core Rule

Given:
- title/episode,
- profile,
- playback timestamp `T`,
- spoiler protection ON,

retrieval is allowed to use story facts only if their reveal timestamp is `<= T`.

## Tests Must Include
- fact before T is available;
- fact exactly at T policy handled deterministically;
- fact after T is blocked;
- relationship revealed later is blocked;
- ending fact is blocked;
- rewatch/full-spoiler mode behavior;
- malformed metadata fails safely.

Prefer omission over accidental spoiler disclosure.

---

# 27. Phase 18 — SceneLens

Build player-integrated SceneLens.

Initial modules:
- current scene,
- current characters,
- actor,
- prior appearances,
- spoiler-safe character summary,
- scene summary,
- bookmarks,
- notes.

Then add:
- relationship map,
- music,
- filmmaking,
- production notes,
- easter eggs.

UI must not obscure the movie unnecessarily.

Support:
- pause activation,
- explicit button,
- keyboard shortcut where sensible,
- mobile layout.

---

# 28. Phase 19 — Ask This Movie

Build retrieval-grounded Q&A.

## Required Pipeline
1. identify title/episode;
2. identify profile;
3. identify current timestamp;
4. identify spoiler setting;
5. generate allowed retrieval range;
6. retrieve structured/approved scene data;
7. answer only from supported data;
8. expose uncertainty when needed;
9. log source/provenance internally;
10. never invent a future plot fact.

## Failure Behavior
If reliable information is unavailable:
- say it is not available;
- do not fabricate.

---

# 29. Phase 20 — Who Was That and What Did I Miss

## Who Was That
Return:
- character,
- actor,
- prior appearances,
- known relationships,
- spoiler-safe summary.

## What Did I Miss
Return:
- recap of the requested watched interval,
- no future information.

Add tests for dense mystery/ensemble-style sample data.

---

# 30. Phase 21 — Dynamic Relationship Graph

Implement graph query constrained by spoiler timestamp.

UI:
- zoom/pan where needed,
- accessible alternate representation,
- relationship labels,
- current-character emphasis,
- timestamp-safe reveal.

---

# 31. Phase 22 — Cinephile Toolkit

Implement incrementally:

- scene bookmarks,
- private notes,
- frame/still gallery using permitted assets,
- music timeline,
- filmmaking explorer,
- credits explorer,
- edition vault,
- version comparison,
- original-presentation metadata,
- film knowledge graph,
- collections,
- film journeys,
- after-credits room,
- rewatch intelligence.

Each should use shared domain models rather than isolated one-off tables.

---

# 32. Phase 23 — No-Algorithm Mode

Add preference-controlled homepage modes.

Implement deterministic No-Algorithm view:
- new titles,
- A-Z,
- release year,
- director,
- country,
- genre,
- collection.

Verify switching modes changes content strategy immediately and persistently per profile.

---

# 33. Phase 24 — Reviews and Community

Only enable publicly when moderation is ready.

Implement:
- ratings,
- review,
- spoiler flag,
- list,
- follow/activity architecture,
- reports,
- moderation queue.

Do not ship public user-generated content without:
- abuse report path,
- block/mute architecture,
- moderation capability,
- rate limits.

---

# 34. Phase 25 — Movie Clubs / Watch Parties

These are later enhancements.

Movie Clubs:
- club,
- membership,
- scheduled title,
- poll,
- discussion.

Watch Parties:
- synchronized playback,
- drift correction,
- host controls,
- private access.

Do not allow synchronized viewing to bypass per-user content entitlement.

---

# 35. Phase 26 — Accessibility and Internationalization Pass

Audit:
- keyboard,
- screen readers,
- focus management,
- contrast,
- subtitles,
- caption settings,
- RTL readiness,
- locale formatting,
- date/timezones,
- language selectors.

Dual subtitles must not break normal subtitle accessibility.

---

# 36. Phase 27 — Security Hardening

Run:
- dependency audit,
- authz audit,
- admin route audit,
- upload validation audit,
- signed-media audit,
- session audit,
- CSRF/CORS audit,
- secrets scan,
- production-header audit.

Ensure:
- no public admin creation,
- no insecure test credentials in production,
- no development debugging endpoints exposed.

---

# 37. Phase 28 — Performance Hardening

Measure, do not guess.

Frontend:
- bundle,
- page loading,
- image loading,
- rail performance,
- hydration/client work.

Backend:
- slow queries,
- N+1 queries,
- indexes,
- cache behavior,
- queue throughput.

Streaming:
- time to first frame,
- buffering,
- rendition switching,
- player error rates.

---

# 38. Phase 29 — Production Observability

Implement:
- structured logging,
- error tracking,
- health/readiness,
- job queue metrics,
- storage metrics,
- transcode metrics,
- API metrics,
- playback QoE,
- alerts.

Create runbooks for:
- failed media processing,
- DB unavailable,
- storage unavailable,
- queue backlog,
- CDN/origin issue,
- admin lockout,
- bad deployment.

---

# 39. Phase 30 — Staging Deployment

Build a production-like staging environment.

Must use:
- staging DB,
- staging storage,
- staging secrets,
- staging domain if available,
- protected Studio,
- production-like media delivery.

Run:
- migrations,
- smoke tests,
- E2E,
- media processing,
- playback,
- SceneLens,
- subscription/entitlement tests.

Do not point staging to production data by default.

---

# 40. Phase 31 — Production Launch Gate

Before launch, produce:

`docs/LAUNCH_CHECKLIST.md`

It must include:

## Product
- core user journeys pass;
- empty/error states pass;
- no unfinished critical UI.

## Media
- upload → process → play proven;
- subtitles/audio proven;
- adaptive playback proven.

## Admin
- secure login;
- upload;
- edit;
- publish;
- schedule;
- homepage management;
- failure recovery.

## Security
- secrets;
- TLS;
- admin MFA;
- rate limits;
- access checks;
- signed media.

## Data
- migrations;
- backups;
- restore test;
- retention.

## Operations
- monitoring;
- alerts;
- rollback;
- incident runbook.

## Legal/Content
- only licensed/authorized content;
- rights windows configured;
- policy pages in place as applicable.

Launch only after unresolved critical blockers are zero.

---

# 41. Browser Test Matrix

At meaningful milestones test:

## Desktop
- Chromium
- Firefox
- WebKit/Safari-compatible Playwright engine

## Responsive
At least:
- common mobile width,
- tablet width,
- laptop width,
- large desktop width.

For player features, include real browser/manual verification where automated media restrictions complicate testing.

---

# 42. Required Test Commands

Codex must discover actual repository commands and record them in:

`docs/DEVELOPMENT.md`

Typical categories:
- frontend typecheck,
- frontend lint,
- frontend unit tests,
- backend tests,
- migrations,
- Playwright,
- worker tests,
- production build.

Do not invent commands in documentation that are not actually runnable.

---

# 43. Visual Quality Rule

Do not allow the product to become a collection of generic dashboard templates.

For each major customer page:
- inspect hierarchy,
- spacing,
- typography,
- artwork ratios,
- motion,
- skeleton/loading,
- hover/focus,
- empty/error,
- responsive.

For Studio:
- optimize information density,
- clear statuses,
- table usability,
- forms,
- validation,
- progress visibility,
- failure recovery.

---

# 44. Data Quality Rule

For every imported/generated metadata field classify:

- authoritative,
- administrator-entered,
- imported,
- AI-generated,
- derived.

Persist source/provenance where it matters.

AI-generated metadata must be editable and versionable.

---

# 45. Error Handling Rule

Every asynchronous operation needs:

- Pending
- Running
- Succeeded
- Failed
- Retryable vs terminal classification where useful
- human-readable error
- machine-readable error code
- retry mechanism where safe
- audit/log correlation id

Never trap failures only in server logs if the administrator needs to act on them.

---

# 46. Database Rule

For each new domain:

1. model relationships;
2. define constraints;
3. define indexes;
4. write migration;
5. write rollback/downgrade if migration system supports it;
6. test migration on clean DB;
7. test migration against current dev DB.

Do not modify production schema manually outside migrations.

---

# 47. API Contract Rule

Frontend must not scatter raw fetch logic everywhere.

Use:
- generated or typed client,
- shared response types,
- consistent error handling,
- auth/session behavior,
- request cancellation where relevant.

Admin and customer APIs should have clear authorization boundaries.

---

# 48. Security Rule for the Single Admin

The simplicity of one administrator must be used to increase security.

Implement:
- one provisioned identity,
- no open invitation system,
- no public role assignment,
- MFA,
- audit trail,
- secure password reset/recovery mechanism,
- optional IP/session alerts later,
- session revocation.

Never store the admin password in source control or seed it in a production migration.

---

# 49. Media Copyright / Rights Rule

Development must use:
- user-owned,
- public-domain,
- properly licensed,
- or explicitly authorized test media.

Do not package copyrighted commercial movies into the repository.

Do not implement download/extraction features designed to bypass content protection.

---

# 50. Do Not Fake Completion

Examples of incomplete states that must remain marked incomplete:

- button exists but API does nothing;
- chart renders random values;
- upload UI accepts file but no processing occurs;
- quality selector changes label but not stream;
- SceneLens answers from a generic chatbot with no timestamp guard;
- "4K" badge is hardcoded;
- subscription page exists but entitlements are ignored;
- publish toggle changes UI but not customer availability.

Mark such work clearly as:
- scaffold,
- mock,
- blocked,
- or partial.

---

# 51. Status Reporting Format

At the end of every major implementation batch, update `BUILD_STATUS.md` with:

```text
PHASE:
STAGE:
STATUS: PASS / PARTIAL / BLOCKED / FAIL

IMPLEMENTED:
- ...

FILES CHANGED:
- ...

MIGRATIONS:
- ...

TESTS:
- command -> result

LIVE VERIFICATION:
- URL
- page/flow tested
- browser result
- console errors
- network errors

KNOWN ISSUES:
- ...

NEXT STEP:
- ...
```

---

# 52. Live-Server Failure Recovery

If the live development website stops working:

1. identify which process failed;
2. inspect logs;
3. fix the underlying cause;
4. restore the affected service;
5. reload the page;
6. rerun the last verification;
7. only then continue feature development.

Do not ignore a broken live environment for multiple phases.

---

# 53. Development Data

Provide a safe local seed dataset that is rich enough to exercise:
- movie page,
- series page,
- multi-season series,
- multiple credits,
- multiple genres,
- artwork,
- search,
- rails,
- recommendation,
- progress,
- SceneLens sample,
- relationship graph,
- multiple editions if needed.

Use placeholder/generated/public-domain assets where licensing requires it.

---

# 54. Feature Flags

Use feature flags for risky/incomplete advanced features such as:
- SceneLens,
- Ask This Movie,
- community,
- watch parties,
- experimental recommendations.

Feature flags must not become a permanent substitute for finishing work.

---

# 55. Production Configuration

Separate:
- development,
- test,
- staging,
- production.

Never reuse:
- database,
- object storage bucket,
- secrets,
- admin test account,
- analytics namespace

across environments unless intentionally configured and documented.

---

# 56. Backup and Restore

Before production:
- automated database backup,
- object-storage durability strategy,
- configuration backup,
- restore procedure,
- restore test.

Record actual restore steps.

---

# 57. Deployment Strategy

Prefer repeatable deployment:
- container/image or deterministic build,
- migration step,
- health check,
- rollout,
- smoke test,
- rollback.

Do not deploy by manually editing production files.

---

# 58. Final Acceptance Scenario

The platform is considered end-to-end functional only when this scenario works:

1. Administrator securely signs into `/studio`.
2. Administrator creates a movie.
3. Administrator adds metadata and artwork.
4. Administrator uploads a source video.
5. The system stores and validates it.
6. A background job processes the video.
7. HLS/adaptive renditions are created.
8. Thumbnails/subtitles/audio are associated.
9. Administrator previews the processed title.
10. Administrator publishes or schedules it.
11. The title appears in the intended customer rail.
12. Customer signs in and selects a profile.
13. Customer finds the title through home/search.
14. Customer opens details.
15. Customer plays adaptive video.
16. Customer leaves and later resumes.
17. Watch activity affects Continue Watching.
18. My List and rating work.
19. Recommendation/taste systems consume valid signals.
20. SceneLens recognizes the correct movie/time context.
21. Spoiler-safe Ask This Movie does not reveal future information.
22. Cinema Passport reflects completed activity.
23. Admin analytics reflect real generated events.
24. The entire flow can be repeated after a clean deployment.

Only then is the architecture proving the intended product loop.

---

# 59. Final Instruction to Codex

Build this project **brick by brick, phase by phase, while the website remains observable in its running state**.

Prefer correctness, integration, recoverability, and visible working behavior over quickly producing disconnected code.

Do not stop at "minimum viable."

Do not stop at "Netflix clone."

The target is a premium streaming platform whose defining advantage is that it treats a movie not merely as a video file, but as an interactive world that can be watched, understood, explored, remembered, and discovered.
