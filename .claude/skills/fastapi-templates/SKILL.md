---
name: fastapi-templates
description: Use only when adding a genuinely new Signal Sports backend component with no existing equivalent (a new router module, service or repository for a new capability) or when Guy explicitly asks for FastAPI scaffolding. Maps patterns onto the existing backend layout (routes_*.py, services, repositories, orm_models, sync SQLAlchemy + SQLite, cookie sessions). NOT for editing existing routes, and never a reason to restructure the backend or add layers or dependencies.
---

# FastAPI Project Templates

## Signal Sports adaptation (read first; overrides the upstream text below where they differ)

Local adaptation of wshobson/agents `fastapi-templates` (MIT); provenance in [UPSTREAM.md](UPSTREAM.md).

**Activation is narrow.** Use this skill only for (a) a genuinely new backend component with no
existing equivalent, or (b) Guy explicitly asking for scaffolding. Editing or extending existing
routes, services or repositories follows the surrounding code and the area skills, not this
template.

**The existing backend is the template.** Map any pattern below onto what already exists; never
restructure:

| Upstream template | This repo |
|---|---|
| `api/v1/endpoints/*.py`, `router.py` | `app/api/routes_<area>.py`, registered in `app/main.py`; no `/v1` layer |
| async SQLAlchemy + asyncpg/PostgreSQL | **sync** SQLAlchemy 2.x + SQLite (`app/db/database.py`); the `get_session` dependency |
| `models/` + `schemas/` | ORM rows in `app/db/orm_models.py`; Pydantic models in `app/models/` |
| generic `BaseRepository` CRUD | small purpose-specific functions in `app/repositories/*_repository.py` |
| JWT / OAuth2 password flow / pwdlib | cookie sessions + argon2 (`app/services/auth_service.py`); `require_session` / `require_user` / `require_admin` (`app/core/security_deps.py`); the CSRF middleware |
| permissive CORS middleware | the `CSRF_ALLOWED_ORIGINS` policy (`app/core/csrf.py`); don't widen it |
| `pydantic-settings` | `app/core/config.py` + env flags documented in `backend/.env.example` |

**Hard rules for anything new**
- No new dependencies (asyncpg, aiosqlite, PyJWT, pwdlib, pydantic-settings, pytest-asyncio, …)
  without a concrete need and Guy's agreement. `requirements.txt` and the hash-pinned
  `requirements.lock` change together, in their own reviewed step.
- No new abstraction layers (generic repositories, service base classes, DI containers) for one
  feature.
- Every new route gets an authorization classification — `tests/test_authz_inventory.py` fails
  otherwise, by design — and mutating routes go through CSRF.
- Destructive or dev routes stay behind the existing guards: `ALLOW_DEV_RESET`, corpus protection
  (`app/db/corpus_protection.py`), `DEPLOY_ENV` checks (`app/core/deploy_mode.py`).
- Tests use the existing `client` / `anonymous_client` fixtures (sync `TestClient`, temp SQLite) —
  not the async client shown below.
- A new security-relevant route also triggers `differential-review`.

---

*Upstream text follows (lightly edited; see UPSTREAM.md).*

Production-ready FastAPI project structures with async patterns, dependency injection, middleware, and best practices for building high-performance APIs.

## When to Use This Skill

- Starting new FastAPI projects from scratch
- Implementing async REST APIs with Python
- Building high-performance web services and microservices
- Creating async applications with PostgreSQL, MongoDB
- Setting up API projects with proper structure and testing

## Core Concepts

### 1. Project Structure

**Recommended Layout:**

```
app/
├── api/                    # API routes
│   ├── v1/
│   │   ├── endpoints/
│   │   │   ├── users.py
│   │   │   ├── auth.py
│   │   │   └── items.py
│   │   └── router.py
│   └── dependencies.py     # Shared dependencies
├── core/                   # Core configuration
│   ├── config.py
│   ├── security.py
│   └── database.py
├── models/                 # Database models
│   ├── user.py
│   └── item.py
├── schemas/                # Pydantic schemas
│   ├── user.py
│   └── item.py
├── services/               # Business logic
│   ├── user_service.py
│   └── auth_service.py
├── repositories/           # Data access
│   ├── user_repository.py
│   └── item_repository.py
└── main.py                 # Application entry
```

### 2. Dependency Injection

FastAPI's built-in DI system using `Depends`:

- Database session management
- Authentication/authorization
- Shared business logic
- Configuration injection

### 3. Async Patterns

Proper async/await usage:

- Async route handlers
- Async database operations
- Async background tasks
- Async middleware

### 4. Dependencies

The packages the examples import:

```text
# requirements.txt
fastapi
uvicorn[standard]
pydantic-settings
sqlalchemy[asyncio]>=2.0  # DeclarativeBase; [asyncio] installs greenlet for the async engine
asyncpg                   # PostgreSQL driver: postgresql+asyncpg://...
PyJWT
pwdlib[argon2]
python-multipart          # only for a login route that uses OAuth2PasswordRequestForm

# requirements-dev.txt
pytest
pytest-asyncio
httpx
aiosqlite                 # test database: sqlite+aiosqlite:///:memory:
```

## Detailed worked examples and patterns

Detailed sections (starting with `## Implementation Patterns`) live in `references/details.md`. Read that file when the navigation summary above is insufficient.

## Testing

```python
# tests/conftest.py
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db, Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Async fixtures need pytest_asyncio.fixture in pytest-asyncio's default strict mode
@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        yield session
    await engine.dispose()

@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # httpx 0.28 removed AsyncClient(app=...); use an ASGI transport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

# tests/test_users.py
import pytest

@pytest.mark.asyncio
async def test_create_user(client):
    response = await client.post(
        "/api/v1/users/",
        json={
            "email": "test@example.com",
            "password": "testpass123",
            "name": "Test User"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
```
