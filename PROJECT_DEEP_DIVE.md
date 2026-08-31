# APERTURE - Project Deep Dive Summary

## Project Overview

**APERTURE** (Apex Cinema) is a sophisticated **anime streaming platform** built with modern full-stack technologies. It's a production-ready application with enterprise-level features including authentication, content management, recommendations, community features, and video streaming.

---

## Technology Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    APERTURE PLATFORM                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Frontend (Next.js 16 + React 19)                           │
│  ├─ TypeScript (155 files)                                  │
│  ├─ React Components                                        │
│  ├─ HLS Video Player (hls.js)                              │
│  └─ Responsive UI                                           │
│                                                               │
│  Backend (Python FastAPI)                                   │
│  ├─ 93 Python files                                         │
│  ├─ SQLAlchemy ORM                                          │
│  ├─ 30+ API Routes                                          │
│  ├─ 15 Business Services                                    │
│  └─ Feature Flags System                                    │
│                                                               │
│  Infrastructure                                             │
│  ├─ PostgreSQL (Primary Database)                           │
│  ├─ Redis (Caching & Sessions)                              │
│  ├─ MinIO/S3 (Object Storage)                               │
│  ├─ Mailpit (Email Testing)                                 │
│  └─ Stripe (Billing)                                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    Client Browser                         │
│                   (http://localhost:3000)                 │
└──────────────────┬───────────────────────────────────────┘
                   │ (Fetch/REST)
                   ▼
┌──────────────────────────────────────────────────────────┐
│              Next.js Frontend (React 19)                  │
│  ├─ SSR / ISR                                             │
│  ├─ API Routes (Proxy)                                    │
│  └─ Component Tree                                        │
└──────────────────┬───────────────────────────────────────┘
                   │ (JSON/HTTP)
                   ▼
┌──────────────────────────────────────────────────────────┐
│          FastAPI Backend (Python 3.12)                    │
│  ├─ Routing Layer                                         │
│  ├─ Authentication (JWT + OAuth2)                         │
│  └─ Business Logic Services                               │
└─┬───────────────────┬──────────────────────────┬──────────┘
  │                   │                          │
  ▼                   ▼                          ▼
┌────────────────┐ ┌─────────────┐ ┌──────────────────────┐
│  PostgreSQL    │ │   Redis     │ │   MinIO / S3         │
│  (Data)        │ │   (Cache)   │ │   (Media Storage)    │
└────────────────┘ └─────────────┘ └──────────────────────┘
```

---

## Core Components & Files

### 🔐 Authentication System

**Files**: `auth.py`, `passport_service.py`, `mfa.py`

**Features**:
- Email/password registration & login
- JWT token-based sessions
- OAuth2 integration (Google, GitHub, etc.)
- Multi-Factor Authentication (MFA)
- Session management

**Models**:
```
User
├─ id (UUID)
├─ email
├─ password_hash (Argon2)
├─ is_active
├─ created_at / updated_at
├─ profiles (1:N)
├─ sessions (1:N)
└─ oauth_identities (1:N)

Profile
├─ id (UUID)
├─ user_id (FK)
├─ name
├─ avatar_key
└─ preferences

OAuthIdentity
├─ id (UUID)
├─ user_id (FK)
├─ provider (Google, GitHub, etc.)
├─ subject
├─ email_at_link
└─ last_login_at
```

---

### 📺 Content Management System

**Files**: `catalog_service.py`, `catalog_schemas.py`, `models.py`

**Features**:
- Media catalog (Movies/Shows/Anime)
- TMDB integration for data import
- Genre & tag classification
- Content metadata
- Episode management
- Subtitle support

**Models**:
```
Media
├─ id (UUID)
├─ title
├─ description
├─ poster_key (S3)
├─ backdrop_key (S3)
├─ release_date
├─ maturity_level (kids, teen, adult)
├─ genres (N:N)
├─ tags (N:N)
└─ episodes (1:N)

Episode
├─ id (UUID)
├─ media_id (FK)
├─ episode_number
├─ title
├─ description
├─ duration
├─ video_key (S3)
└─ subtitles (1:N)

Scene
├─ id (UUID)
├─ episode_id (FK)
├─ start_time
├─ end_time
├─ description
└─ metadata (JSON)
```

---

### 🎬 Video Playback & Streaming

**Files**: `playback.py`, `playback_schemas.py`

**Features**:
- HLS (HTTP Live Streaming) support
- Adaptive bitrate streaming
- Subtitle delivery
- Playback state tracking
- Resume-from-position
- Multi-device sync

**Endpoints**:
```
GET    /playback/media/{id}        # Get playback info
POST   /playback/{id}/start        # Start session
PATCH  /playback/{id}/resume       # Update progress
GET    /playback/{id}/manifest     # HLS manifest
```

---

### 🤖 Recommendation Engine

**Files**: `recommendation_service.py`, `taste_service.py`, `prescription_service.py`

**Features**:
- ML-based recommendations
- User taste profiling
- Personalized "For You" feed
- Content similarity matching
- Watch history analysis
- Collaborative filtering

**Models**:
```
Recommendation
├─ id (UUID)
├─ user_id (FK)
├─ media_id (FK)
├─ score (0.0-1.0)
├─ reason (algorithm used)
└─ created_at

Rating
├─ id (UUID)
├─ user_id (FK)
├─ media_id (FK)
├─ score (1-10)
└─ created_at

WatchlistEntry
├─ id (UUID)
├─ user_id (FK)
├─ media_id (FK)
├─ status (watching, completed, dropped)
└─ added_at
```

---

### 👥 Community & Social Features

**Files**: `clubs.py`, `community.py`, `curation.py`

**Features**:
- User clubs/groups
- Community discussions
- Shared moments (scenes)
- Content curation
- User following
- Community moderation

**Models**:
```
Club
├─ id (UUID)
├─ name
├─ description
├─ creator_id (FK)
└─ members (N:N)

Community
├─ id (UUID)
├─ name
├─ description
└─ members (N:N)

Discussion
├─ id (UUID)
├─ club_id (FK)
├─ author_id (FK)
├─ title
├─ content
└─ replies (1:N)

Moment
├─ id (UUID)
├─ scene_id (FK)
├─ creator_id (FK)
├─ title
├─ description
└─ shares (1:N)
```

---

### 📊 Analytics & Observability

**Files**: `analytics_service.py`, `observability.py`, `analytics.py`

**Features**:
- User event tracking
- Playback analytics
- Content popularity metrics
- User engagement metrics
- Error tracking (Sentry)
- Request logging with structured data
- Prometheus metrics

**Tracked Events**:
```
- user.registered
- user.logged_in
- media.viewed
- playback.started
- playback.paused
- playback.completed
- content.rated
- discussion.posted
- error events
```

---

### ⚙️ Admin Dashboard

**Routes**: `admin_*.py` (11 files)

**Capabilities**:
- Catalog management (add/edit/delete media)
- Content curation
- User analytics dashboard
- Processing job monitoring
- Media transcoding queue
- Support ticket system
- Feature flag toggling
- Upload management

**Admin Routes**:
```
/admin/catalog        # Media management
/admin/analytics      # Analytics dashboard
/admin/community      # Community moderation
/admin/curation       # Content curation
/admin/processing     # Job processing
/admin/scenes         # Scene management
/admin/uploads        # Media uploads
/admin/support        # Support tickets
/admin/playback       # Playback config
/admin/homepage       # Homepage management
/admin/auth           # User management
```

---

## Request Flow Example: User Watching a Video

```
1. User logs in
   └─ POST /auth/login
      └─ credentials → FastAPI → verify password → generate JWT → return token

2. Frontend stores JWT in cookie
   └─ All subsequent requests include JWT

3. User browses catalog
   └─ GET /catalog/media?genre=anime
      └─ FastAPI → filter media → return list

4. User clicks video
   └─ GET /catalog/media/{id}
      └─ FastAPI → fetch details → return full metadata

5. Video player initiates playback
   └─ GET /playback/media/{id}
      └─ FastAPI → check permissions → generate HLS URL → return

6. Frontend loads HLS manifest
   └─ GET /content/{media_id}/manifest.m3u8
      └─ Generate adaptive bitrate playlist

7. Browser streams video chunks
   └─ GET /content/{media_id}/segment-{number}.ts
      └─ Stream encrypted segments from S3

8. User pauses at 00:15:30
   └─ PATCH /playback/{id}/resume {position: 915}
      └─ FastAPI → save to database → update watch state

9. Analytics event recorded
   └─ Event → Redis queue → Analytics service → processed → stored

10. Recommendation engine updates
    └─ User profile updated → recalculate recommendations → updated feed
```

---

## Database Schema Overview

### Core Tables (20+)

**Users & Auth**
- `users` - User accounts
- `profiles` - User profiles
- `oauth_identities` - OAuth links
- `device_sessions` - Active sessions

**Content**
- `media` - Movies/Shows/Anime
- `episodes` - Episode details
- `scenes` - Scenes/moments
- `genres` - Content genres
- `tags` - Content tags
- `subtitles` - Subtitle files
- `recommendations` - ML recommendations

**Playback**
- `playback_state` - Watch progress
- `playback_sessions` - Session tracking

**User Interaction**
- `ratings` - User ratings
- `reviews` - User reviews
- `watchlist_entries` - Watchlist
- `moments` - Shared scenes

**Community**
- `clubs` - User clubs
- `club_members` - Membership
- `discussions` - Discussions
- `community_members` - Community membership

**Admin**
- `processing_jobs` - Media processing
- `support_tickets` - Support tickets
- `feature_flags` - Feature toggles
- `admin_logs` - Audit logs

---

## Feature Flags (Configurable at Runtime)

```python
# Environment variables control features
FEATURE_SCENE_LENS_ENABLED=true           # Scene analysis AI
FEATURE_ASK_MOVIE_ENABLED=true            # Movie recommendation AI
FEATURE_COMMUNITY_ENABLED=true            # Community/clubs
FEATURE_WATCH_PARTIES_ENABLED=true        # Watch parties
FEATURE_EXPERIMENTAL_RECOMMENDATIONS=true # ML recommendations
```

---

## Security Features

### Authentication
- ✅ Password hashing (Argon2)
- ✅ JWT tokens with expiration
- ✅ OAuth2 integration
- ✅ Multi-Factor Authentication
- ✅ Session management

### API Security
- ✅ CORS protection
- ✅ CSRF tokens
- ✅ Rate limiting
- ✅ Request ID tracking
- ✅ Security headers (CSP, X-Frame-Options, etc.)

### Data Security
- ✅ SQL injection prevention (SQLAlchemy ORM)
- ✅ XSS prevention (React/NextJS)
- ✅ Secure password storage
- ✅ HTTPS in production (Caddy/nginx)

### Infrastructure
- ✅ Malware scanning
- ✅ Geolocation verification
- ✅ Error tracking (Sentry)
- ✅ Audit logging

---

## Deployment Architecture

```
┌─────────────────────────────────────┐
│         Production Environment       │
├─────────────────────────────────────┤
│                                     │
│  Caddy (Reverse Proxy)              │
│  ├─ HTTPS termination               │
│  ├─ Load balancing                  │
│  └─ Virtual host routing            │
│         │                           │
│  ┌──────┴──────┬──────────┬─────┐  │
│  │             │          │     │  │
│  ▼             ▼          ▼     ▼  │
│ Web API  Media Worker Scene Worker │
│  (N)       (N)            (N)      │
│         │                           │
│  ┌──────┴──────┬──────────┬─────┐  │
│  │             │          │     │  │
│  ▼             ▼          ▼     ▼  │
│ PostgreSQL   Redis    MinIO  Mailpit│
│  (HA)        (HA)     (HA)         │
│                                     │
│  Monitoring: Prometheus + Grafana   │
│  Logging: Sentry + ELK              │
│                                     │
└─────────────────────────────────────┘
```

---

## Key Statistics

| Metric | Count |
|--------|-------|
| **Python Files** | 93 |
| **TypeScript/React Files** | 155 |
| **Database Models** | 20+ |
| **API Routes** | 30+ |
| **Services** | 15 |
| **Feature Flags** | 5+ |
| **Authentication Methods** | 3+ |
| **Admin Routes** | 11+ |
| **Lines of Code (Backend)** | ~15,000 |
| **Lines of Code (Frontend)** | ~20,000 |

---

## Getting Started

### Prerequisites
- ✅ Python 3.12.10 (installed)
- ✅ Node.js 24.15.0 (installed)
- ✅ PostgreSQL (recommended)
- ✅ Redis (recommended)
- Docker (optional, for services)

### Quick Setup

```bash
# 1. Install dependencies (already done!)
# Backend: Python packages installed in apps/api/venv/
# Frontend: npm packages installed in apps/web/node_modules/

# 2. Start backend services
docker-compose -f docker-compose.dev.yml up -d

# 3. Start API server from the repository root
scripts/run-api-dev.sh

# 4. Start frontend from the repository root (new terminal)
scripts/run-web-dev.sh

# 5. Access application
# Frontend: http://localhost:3000
# API Docs: http://localhost:8001/docs
```

---

## Important Files & Their Roles

### Backend Entry Points
- **`apps/api/app/main.py`** - FastAPI application setup
- **`apps/api/app/config.py`** - Configuration management
- **`apps/api/app/db.py`** - Database connection
- **`apps/api/app/models.py`** - SQLAlchemy models

### Frontend Entry Points
- **`apps/web/app/layout.tsx`** - Root layout
- **`apps/web/app/page.tsx`** - Homepage
- **`apps/web/app/api/`** - API proxy routes

### Configuration
- **`.env`** - Unified local environment configuration
- **`pyproject.toml`** - Python project config
- **`apps/web/package.json`** - Node dependencies

### Documentation (Auto-generated)
- **`PROJECT_STRUCTURE.md`** - Detailed structure
- **`SETUP_GUIDE.md`** - Complete setup guide
- **`API Docs`** - Swagger UI at `/docs`

---

## Next Steps

1. **Review Project Structure**
   - Read `PROJECT_STRUCTURE.md`
   - Read `SETUP_GUIDE.md`

2. **Set Up Local Environment**
   - Start Docker services: `docker-compose -f docker-compose.dev.yml up -d`
   - Or configure PostgreSQL, Redis manually

3. **Run the Application**
   - Backend: `scripts/run-api-dev.sh`
   - Frontend: `scripts/run-web-dev.sh`

4. **Explore Features**
   - http://localhost:3000 - Frontend
   - http://localhost:8001/docs - API Documentation

5. **Make Changes**
   - Backend auto-reloads on Python file changes
   - Frontend auto-reloads on file changes

---

## Summary

**Aperture** is a production-ready anime streaming platform with:

✅ **Complete authentication system** (email, OAuth, MFA)
✅ **Video streaming** with HLS support
✅ **Recommendation engine** with ML
✅ **Community features** (clubs, discussions)
✅ **Admin dashboard** for content management
✅ **Analytics & observability** (Sentry, Prometheus)
✅ **Mobile-responsive** frontend
✅ **Enterprise-grade** architecture
✅ **Fully typed** (TypeScript + Pydantic)
✅ **Well-organized** codebase (93 Python + 155 TS files)

All dependencies installed and ready to run! 🚀
