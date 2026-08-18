# Product Decisions

## PD-001 — Commands A and B Are Authoritative

Command A defines product scope and acceptance. Command B defines execution order and delivery discipline. A capability is not complete until its integrated behavior is tested and, when user-facing, verified in the running application.

## PD-002 — Greenfield Architecture

Because no pre-existing application architecture exists, use the preferred greenfield topology from Command B: Next.js/TypeScript, FastAPI/Python, PostgreSQL, Redis, S3-compatible storage, Python media workers, and FFmpeg. Exact versions must be compatibility-checked before locking them.

## PD-003 — One Private Administrator

The platform has exactly one provisioned administrator and no public admin registration. Customer accounts may contain multiple independent viewer profiles.

## PD-004 — Two Viewer Modes, One Catalog

Normal Mode provides a simple premium viewing experience. Cinephile Mode progressively exposes deeper discovery and scene intelligence over the same catalog and account.

## PD-005 — Truthful State

Mock, scaffolded, partial, blocked, or development-only behavior is labeled explicitly. Metrics, playback capability, billing, AI grounding, and completion status must never be fabricated.

## PD-006 — Rights-Safe Development

Only authorized development media and metadata may be used. No feature may facilitate content-protection bypass or unauthorized redistribution.

