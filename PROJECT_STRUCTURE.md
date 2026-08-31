# APERTURE Project - Complete Analysis

## Project Overview
**Aperture** (branded as "Apex Cinema") is a comprehensive anime streaming platform built with modern full-stack technologies.

---

## Technology Stack

### Backend (Python/FastAPI)
- **Framework**: FastAPI 0.141.1
- **Database**: PostgreSQL (SQLAlchemy ORM with Alembic migrations)
- **Cache**: Redis
- **Storage**: AWS S3 (MinIO compatible)
- **Authentication**: OAuth2, JWT, Argon2 password hashing
- **Monitoring**: Sentry SDK for error tracking
- **Server**: Uvicorn

### Frontend (TypeScript/Next.js)
- **Framework**: Next.js 16.3.1
- **React**: 19.2.8
- **Language**: TypeScript 5.9.3
- **Testing**: Vitest, React Testing Library
- **Video**: HLS.js for video playback

---

## Backend Architecture (93 Python Files)

### Core Components

#### Database Models (`models.py`)
- **User**: User account with email/password authentication
- **OAuthIdentity**: OAuth provider integration
- **Profile**: User profiles with watchlists
- **MaturityLevel**: Content rating (kids, teen, adult)
- **SystemRecord**: System-level configuration storage

#### Services Layer (15 services)
1. **auth.py** - Authentication & authorization
2. **account_schemas.py** - Account management schemas
3. **analytics_service.py** - User analytics & tracking
4. **ask_movie_service.py** - Movie AI recommendation service
5. **catalog_service.py** - Media catalog management
6. **cinephile_service.py** - User preferences & taste
7. **curation_service.py** - Content curation system
8. **homepage_service.py** - Homepage generation
9. **knowledge_service.py** - Content knowledge base
10. **moment_service.py** - Scene/moment analysis
11. **passport_service.py** - User authentication/authorization
12. **prescription_service.py** - Personalized recommendations
13. **recommendation_service.py** - ML-based recommendations
14. **relationship_graph_service.py** - User/content relationships
15. **spoiler_service.py** - Spoiler detection & management

#### Routes (API Endpoints)
**Customer Routes:**
- `customer_auth.py` - Login, signup, password reset
- `customer_catalog.py` - Browse media catalog
- `account.py` - User account management
- `profiles.py` - User profile management
- `passport.py` - User authentication endpoints
- `playback.py` - Video streaming & playback
- `analytics.py` - Analytics collection
- `recommendations.py` - Recommendation API
- `scene_intelligence.py` - Scene analysis
- `cinephile.py` - User preferences
- `clubs.py` - User clubs/communities
- `community.py` - Community features
- `curation.py` - Content curation
- `homepage.py` - Homepage data
- `billing_webhooks.py` - Stripe webhook handling
- `oauth.py` - OAuth provider integration
- `operations.py` - System health & operations

**Admin Routes:**
- `admin_auth.py` - Admin authentication
- `admin_catalog.py` - Catalog management
- `admin_analytics.py` - Analytics dashboard
- `admin_community.py` - Community moderation
- `admin_curation.py` - Content curation management
- `admin_homepage.py` - Homepage management
- `admin_playback.py` - Playback management
- `admin_processing.py` - Media processing queue
- `admin_scenes.py` - Scene management
- `admin_support.py` - Support tickets
- `admin_uploads.py` - Media uploads

#### Infrastructure
- **config.py** - Settings & environment configuration
- **db.py** - Database connection & session management
- **observability.py** - Logging, metrics, request tracking
- **object_storage.py** - S3/MinIO integration
- **rate_limit.py** - API rate limiting
- **feature_flags.py** - Feature toggle system
- **mfa.py** - Multi-factor authentication
- **billing.py** - Stripe integration
- **captcha.py** - CAPTCHA validation
- **email_delivery.py** - Email service
- **geo.py** - Geolocation services
- **malware_scanner.py** - Content scanning
- **media_worker.py** - Background job processing
- **processing_queue.py** - Job queue management
- **remembered_accounts.py** - Account persistence

---

## Frontend Architecture (155 TypeScript/React Files)

### Key Features
- **Responsive UI** - Mobile-first design
- **Next.js Features** - SSR, ISR, API routes
- **Video Streaming** - HLS.js integration
- **Internationalization** - i18n support
- **Authentication** - JWT-based with cookie storage
- **Dynamic Content** - API-driven content rendering

### Main Application Routes
- `/` - Homepage
- `/auth/*` - Authentication flows
- `/profile/*` - User profiles
- `/watch/*` - Video player
- `/discover/*` - Content discovery
- `/community/*` - Community features
- `/admin/*` - Admin dashboard

---

## Key Features Implemented

### For Users
✅ Email/Password Authentication
✅ OAuth Integration (Google, GitHub, etc.)
✅ Multi-Factor Authentication (MFA)
✅ User Profiles with Watchlists
✅ Personalized Recommendations
✅ Video Playback (HLS streaming)
✅ Scene/Moment Analysis
✅ Community & Clubs
✅ Content Curation
✅ Analytics Tracking

### For Admins
✅ Catalog Management (TMDB integration)
✅ Media Processing Pipeline
✅ Analytics Dashboard
✅ Content Moderation
✅ Feature Flag Management
✅ Support Ticket System
✅ Upload Management
✅ Playback Configuration

### Feature Flags (Configurable)
- Scene Lens (Scene analysis)
- Ask Movie (AI recommendations)
- Community Features
- Watch Parties
- Experimental Recommendations

---

## Environment Configuration

### Key Environment Variables
```
APP_ENV=development
WEB_ORIGIN=http://localhost:3000
API_ORIGIN=http://localhost:8001
NEXT_PUBLIC_OBJECT_STORAGE_ORIGIN=http://localhost:9100
APERTURE_POSTGRES_PORT=5433
APERTURE_REDIS_PORT=6380
APERTURE_MINIO_PORT=9100
APERTURE_MINIO_CONSOLE_PORT=9101

# Database
POSTGRES_DB=anime_streaming_dev
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password

# Redis
REDIS_URL=redis://localhost:6380/0

# S3/MinIO
S3_ENDPOINT=http://localhost:9100
S3_PUBLIC_ENDPOINT=http://localhost:9100
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin

# Stripe
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# TMDB (The Movie Database)
TMDB_API_KEY=...
TMDB_LANGUAGE=en-CA
TMDB_REGION=CA
```

---

## Database Schema Overview

### Core Tables
- `users` - User accounts
- `profiles` - User profiles
- `oauth_identities` - OAuth provider links
- `device_sessions` - Active sessions
- `system_records` - System configuration

### Content Tables
- `media` - Movies/Shows
- `episodes` - Episode details
- `scenes` - Scene/moment details
- `genres` - Content genres
- `tags` - Content tags

### User Interaction Tables
- `watchlist_entries` - User watchlists
- `playback_state` - Watch progress
- `ratings` - User ratings
- `reviews` - User reviews
- `recommendations` - ML recommendations

### Community Tables
- `clubs` - User clubs
- `club_members` - Club membership
- `moments` - Shared moments
- `discussions` - Community discussions

---

## API Architecture

### Request Flow
1. **Client** → Next.js Frontend
2. **Frontend** → FastAPI Backend (`/api/*`)
3. **Backend** → Database/Cache/External APIs
4. **Response** → JSON

### Security
- CORS enabled for trusted origins
- CSRF protection
- Security headers (CSP, X-Frame-Options, etc.)
- Rate limiting per endpoint
- Request ID tracking
- JWT authentication
- OAuth2 support

### Observability
- Request logging with structured data
- Prometheus metrics
- Error tracking with Sentry
- Request ID propagation
- Performance metrics

---

## Project Statistics

| Metric | Count |
|--------|-------|
| Python Files | 93 |
| TypeScript/React Files | 155 |
| Database Models | 20+ |
| API Routes | 30+ |
| Services | 15 |
| Feature Flags | 5+ |
| Supported Auth Methods | 3+ |

---

## Running the Project

### Prerequisites
- Python 3.12+
- Node.js 24+
- PostgreSQL 12+
- Redis
- Docker (recommended for services)

### Startup Sequence
1. **Backend**:
   ```bash
   cd apps/api
   pip install -r requirements.lock
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
   ```

2. **Frontend**:
   ```bash
   cd apps/web
   npm install
   npm run dev
   ```

3. **Access**:
   - Frontend: http://localhost:3000
   - Backend Docs: http://localhost:8001/docs
   - Backend API: http://localhost:8001

---

## Development Features

### Testing
- Playwright E2E tests
- Vitest for React components
- Pytest for Python backend

### Code Quality
- ESLint for TypeScript
- Ruff for Python
- Type checking (TypeScript, Pydantic)
- Pre-commit hooks available

### Deployment
- Docker containers for both services
- Alembic for database migrations
- Hostinger deployment configuration
