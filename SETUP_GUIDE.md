# APERTURE - Complete Project Setup & Running Guide

## Project Summary

**Aperture** is a full-stack anime streaming platform with:
- **Backend**: Python FastAPI with PostgreSQL, Redis, S3 storage
- **Frontend**: Next.js 16 React application
- **Features**: Authentication, video streaming, recommendations, community features
- **93 Python files** + **155 TypeScript/React files**

---

## Prerequisites Installed ✅

- ✅ Python 3.12.10
- ✅ Node.js v24.15.0
- ✅ npm 11.12.1
- ✅ Backend dependencies installed in `apps/api/venv/`
- ✅ Frontend dependencies installed in `apps/web/node_modules/`

---

## Quick Start (For Development)

### Option 1: Using Docker (Recommended)
If Docker Desktop is running:

```bash
# Start all infrastructure services (PostgreSQL, Redis, MinIO, Mailpit)
docker-compose -f docker-compose.dev.yml up -d

# In terminal 1, from the repository root: Start Backend API
scripts/run-api-dev.sh

# In terminal 2, from the repository root: Start Frontend
scripts/run-web-dev.sh

# Access:
# - Frontend: http://localhost:3000
# - API Docs: http://localhost:8001/docs
```

### Option 2: Manual Setup (Without Docker)

You'll need to set up database manually or use the provided services.

#### Step 1: Start Backend Services (if running locally without Docker)

You need PostgreSQL, Redis, and MinIO running. For development, use:
- PostgreSQL: `postgresql://postgres:password@localhost:5433/anime_streaming_dev`
- Redis: `redis://localhost:6380/0`
- MinIO: S3-compatible at `http://localhost:9100` (console: `http://localhost:9101`)

#### Step 2: Start the API Backend

```bash
# Terminal 1 - Backend API
cd apps/api

# Activate virtual environment
source venv/Scripts/activate

# Run database migrations
alembic upgrade head

# Return to the repository root and start the server.
# The script reads API_PORT literally from .env and defaults to 8001.
cd ../..
scripts/run-api-dev.sh
```

✅ API will be available at: `http://localhost:8001`
📚 API Documentation: `http://localhost:8001/docs`
🔄 API Playground: `http://localhost:8001/redoc`

#### Step 3: Start the Web Frontend

```bash
# Terminal 2 - Frontend, from the repository root
scripts/run-web-dev.sh
```

✅ Frontend will be available at: `http://localhost:3000`

---

## Project Structure Overview

### Backend (`apps/api/`)
```
apps/api/
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── models.py               # Database models
│   ├── db.py                   # Database connection
│   ├── config.py               # Configuration
│   ├── routes/                 # API endpoints (30+ routes)
│   │   ├── customer_auth.py   # User authentication
│   │   ├── customer_catalog.py # Browse media
│   │   ├── playback.py        # Video streaming
│   │   ├── recommendations.py # ML recommendations
│   │   └── ...
│   ├── *_service.py            # Business logic (15 services)
│   │   ├── auth.py
│   │   ├── catalog_service.py
│   │   ├── recommendation_service.py
│   │   └── ...
│   ├── *_schemas.py            # Pydantic models (request/response)
│   └── ... infrastructure files
├── migrations/                  # Alembic database migrations
├── requirements.lock           # Python dependencies
├── pyproject.toml              # Project config
└── Dockerfile                  # Container image

Key Components:
- 20+ Database Models
- 15 Business Logic Services
- 30+ API Routes
- 5+ Feature Flags
- OAuth2 + JWT Authentication
- Redis Caching
- S3 Object Storage
```

### Frontend (`apps/web/`)
```
apps/web/
├── app/                        # Next.js App Router
│   ├── (auth)/                # Authentication pages
│   ├── (app)/                 # Main application pages
│   ├── admin/                 # Admin dashboard
│   └── api/                   # API routes (proxy)
├── components/                # React components
├── lib/                       # Utilities & helpers
├── styles/                    # CSS modules
├── public/                    # Static assets
├── package.json              # Dependencies
├── next.config.ts            # Next.js configuration
└── tsconfig.json             # TypeScript config

Key Features:
- Server-side rendering (SSR)
- API proxy for CORS handling
- HLS.js video player
- Responsive design
- TypeScript throughout
- Vitest for testing
```

---

## Key Classes & Objects

### Backend Models (SQLAlchemy ORM)

**User Management**
```python
User              # User account with email/password
Profile           # User profile with preferences
OAuthIdentity     # OAuth provider linking
DeviceSession     # Active sessions

Enums:
- MaturityLevel   # kids, teen, adult
- HomepageMode    # curated, no_algorithm
```

**Content**
```python
Media             # Movies/Shows
Episode           # Episode details
Scene             # Scene/moment details
Genre             # Content genre
Tag               # Content tags
Subtitle          # Subtitle files
```

**User Interaction**
```python
WatchlistEntry    # User's watchlist
PlaybackState     # Watch progress
Rating            # User ratings
Review            # User reviews
Recommendation    # ML recommendations
Moment            # Shared scene moments
```

**Community**
```python
Club              # User clubs/groups
ClubMember        # Club membership
Community         # Community group
Discussion        # Community discussions
```

### Backend Services

```python
AuthService             # Authentication & tokens
CatalogService         # Media catalog operations
RecommendationService  # ML-based recommendations
CinephileService       # User taste/preferences
HomepageService        # Homepage generation
CurationService        # Content curation
PlaybackService        # Video streaming
AnalyticsService       # Usage analytics
KnowledgeService       # Content knowledge base
PassportService        # User authentication/authorization
MomentService          # Scene analysis
```

### Frontend Components

```typescript
// Authentication
LoginForm           // Email/password login
OAuthFlow           // OAuth authentication
MFASetup            // Multi-factor auth

// Content Discovery
ContentGrid         // Media grid display
ContentCard         // Individual media card
SearchBar           // Search functionality
FilterBar           // Content filtering

// Player
VideoPlayer         // HLS video player
PlaybackControls    // Play, pause, seek controls
SubtitleSelector    # Subtitle selection
QualitySelector     # Video quality selection

// User Features
Watchlist           # User's watchlist
Profile             # User profile page
Recommendations     # Personalized recommendations
Community           # Community/clubs section
```

---

## Environment Variables

### Database
```
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5433/anime_streaming_dev
POSTGRES_DB=anime_streaming_dev
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
APERTURE_POSTGRES_PORT=5433
```

### Cache & Storage
```
REDIS_URL=redis://localhost:6380/0
APERTURE_REDIS_PORT=6380
S3_ENDPOINT=http://localhost:9100
S3_PUBLIC_ENDPOINT=http://localhost:9100
NEXT_PUBLIC_OBJECT_STORAGE_ORIGIN=http://localhost:9100
APERTURE_MINIO_PORT=9100
APERTURE_MINIO_CONSOLE_PORT=9101
S3_BUCKET=aperture-media
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
```

### API Configuration
```
APP_ENV=development
WEB_ORIGIN=http://localhost:3000
API_ORIGIN=http://localhost:8001
```

### Feature Flags
```
FEATURE_SCENE_LENS_ENABLED=true
FEATURE_ASK_MOVIE_ENABLED=true
FEATURE_COMMUNITY_ENABLED=true
FEATURE_WATCH_PARTIES_ENABLED=true
FEATURE_EXPERIMENTAL_RECOMMENDATIONS_ENABLED=true
```

---

## Running Different Components

### Run Backend Only
```bash
# From the repository root
scripts/run-api-dev.sh
```

### Run Frontend Only
```bash
# From the repository root
scripts/run-web-dev.sh
```

### Run Tests (Backend)
```bash
cd apps/api
source venv/Scripts/activate
pytest tests/
```

### Run Tests (Frontend)
```bash
cd apps/web
npm run test
```

### Database Migrations
```bash
cd apps/api
source venv/Scripts/activate

# View migration status
alembic current

# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## API Endpoints (Key Routes)

### Authentication
```
POST   /auth/register          # Register new user
POST   /auth/login             # Login with email/password
POST   /auth/logout            # Logout
POST   /auth/password-reset    # Reset password
POST   /oauth/authorize        # OAuth authentication
```

### User Management
```
GET    /account/profile        # Get user profile
PUT    /account/profile        # Update profile
POST   /account/mfa/setup      # Setup MFA
GET    /profiles               # Get user profiles
POST   /profiles               # Create profile
```

### Content
```
GET    /catalog/media          # List media
GET    /catalog/media/{id}     # Get media details
GET    /catalog/search         # Search content
GET    /catalog/genres         # Get genres
GET    /homepage               # Get homepage data
```

### Playback
```
GET    /playback/media/{id}    # Get playback info
POST   /playback/{id}/start    # Start playback session
PATCH  /playback/{id}/resume   # Update watch progress
```

### Recommendations
```
GET    /recommendations        # Get recommendations
GET    /recommendations/for-you  # Personalized recommendations
```

### Community
```
GET    /clubs                  # List clubs
POST   /clubs                  # Create club
GET    /community              # Community feeds
POST   /discussions            # Post discussion
```

---

## Admin Routes

### Content Management
```
PUT    /admin/catalog/{id}     # Update media
DELETE /admin/catalog/{id}     # Delete media
POST   /admin/curation/create  # Create curation
```

TMDB catalog population is a development/test-only CLI task, not an admin HTTP endpoint.
After adding `TMDB_API_READ_ACCESS_TOKEN` to the root `.env`, starting the dependencies,
and running migrations, import and publish the local catalog with:

```bash
cd apps/api
./venv/Scripts/python.exe scripts/import_tmdb_catalog.py --movies 16 --series 16 --scope mixed
```

### Analytics
```
GET    /admin/analytics/users  # User analytics
GET    /admin/analytics/content  # Content analytics
GET    /admin/analytics/playback # Playback stats
```

### Processing
```
GET    /admin/processing/jobs  # List processing jobs
POST   /admin/processing/jobs  # Queue new job
GET    /admin/processing/jobs/{id}  # Job status
```

---

## Common Issues & Solutions

### PostgreSQL Connection Error
**Issue**: `Error connecting to database`
**Solution**:
- Ensure PostgreSQL is running: `pg_isready`
- Check DATABASE_URL is correct
- Verify the required labels are present in the root `.env`

### Redis Connection Error
**Issue**: `Error connecting to Redis`
**Solution**:
- Ensure Redis is running: `redis-cli ping`
- Check that `REDIS_URL` is present in the root `.env`

### Frontend Can't Reach API
**Issue**: Gateway requests return an upstream error
**Solution**:
- Ensure API is running on the `API_PORT` configured in `.env` (default 8001)
- Check that the server-only `API_ORIGIN` in `.env` uses the same API port
- Verify `/api/gateway/*` reaches Next.js before any deployment-level `/api/*` catch-all

### uvloop Error on Windows
**Issue**: `uvloop does not support Windows`
**Solution**: ✅ Already handled! Using `requirements.windows.lock`

### Node/npm modules not found
**Issue**: `Module not found`
**Solution**:
```bash
cd apps/web
npm install
npm cache clean --force
```

---

## Useful Commands

### Backend
```bash
# Start API with debug logging
DEBUG=1 python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --log-level debug

# Run linter
ruff check .

# Format code
ruff format .

# Type checking
mypy app/
```

### Frontend
```bash
# Build for production
npm run build

# Type checking
npm run typecheck

# Linting
npm run lint

# Run E2E tests
npm run test:e2e
```

### Database
```bash
# Connect to PostgreSQL
psql -U postgres -d anime_streaming_dev -h localhost

# Reset database
alembic downgrade base
alembic upgrade head
```

---

## Next Steps

1. **Start Infrastructure** (Docker):
   ```bash
   docker-compose -f docker-compose.dev.yml up -d
   ```

2. **Start Backend**:
   ```bash
   scripts/run-api-dev.sh
   ```

3. **Start Frontend**:
   ```bash
   cd apps/web && npm run dev
   ```

4. **Access Application**:
   - Frontend: http://localhost:3000
   - API: http://localhost:8001
   - API Docs: http://localhost:8001/docs

5. **Explore**:
   - Create account
   - Browse media catalog
   - Test video playback
   - Try recommendations

---

## Documentation

- API Documentation: http://localhost:8001/docs (when running)
- OpenAPI Schema: http://localhost:8001/openapi.json
- Project Structure: `PROJECT_STRUCTURE.md`
- Environment Config: repository-root `.env`

Enjoy exploring Aperture! 🎬✨
