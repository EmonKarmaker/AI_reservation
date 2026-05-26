# Session Log — Phase 1 Complete; Phase 2 Next

## What this document is
This is the **handoff state** of the AI Reservation SaaS project. New Claude chats should read this after `CLAUDE.md` and the other 8 docs in `docs/`. It captures what's done, what decisions override the planning docs, and what's next.

---

## Project state as of handoff

**Phase 0 — COMPLETE.**
**Phase 1 (all sub-phases 1.1–1.8c) — COMPLETE.** Auth works end-to-end with cookies, 4 integration tests pass.
**Phase 2 — NEXT** (business admin dashboard shell + core CRUD).

### Commit history

Phase 0:
- `546250c` — feat(phase-0): project setup complete (backend skeleton, migration, docs)
- `d529605` — feat(phase-0): frontend scaffold (Next.js 16, shadcn/ui)

Phase 1.1–1.4 (data layer):
- `5aa6859` — feat(phase-1.1): SQLAlchemy Base, mixins, Postgres enum classes
- `662cae5` — feat(phase-1.2): platform-level models (User, PlatformSetting, AuditLog)
- `b90f76b` — feat(phase-1.3a): business tenant foundation models
- `0990d52` — feat(phase-1.3b): booking core models
- `64727b5` — feat(phase-1.3c): AI + infra models; all 17 tables defined
- `688892f` — feat(phase-1.3d): wire SQLAlchemy relationships
- `b7fa17e` — feat(phase-1.4a): wire Base.metadata into Alembic
- `3de3f91` — feat(phase-1.4bc): generate and patch migration
- `3e16890` — fix(phase-1.4c): use postgresql.ENUM with create_type=False
- `7c80a3e` — feat(phase-1.4d): apply migration; add verify_tables.py
- `57561e4` — docs: update session log (Phase 1.4 complete)

Phase 1.5–1.6 (security + DB session):
- `a4d492c` — feat(phase-1.5): security utils (JWT + bcrypt) and Fernet encryption
- `5633b78` — feat(phase-1.6): async DB session factory and FastAPI permission dependencies

Phase 1.7 (auth endpoints):
- `017c4ab` — feat(phase-1.7a): auth schemas (Pydantic) and service layer
- `0578c43` — feat(phase-1.7b): auth router with 5 endpoints mounted at /api/v1/auth

Phase 1.8 (bootstrap + seed + tests):
- `5a678b9` — feat(phase-1.8a): super admin bootstrap script
- (1.8b commit) — feat(phase-1.8b): seed 3 demo businesses with services, hours, and FAQs
- (1.8c commit) — feat(phase-1.8c): pytest setup and 4 integration tests for auth

---

## What works right now

### Backend (`backend/`)
- Python 3.11.9 in `.venv`
- FastAPI + async SQLAlchemy 2 + asyncpg + Pydantic v2 + pgvector
- `/health` endpoint live
- Pydantic Settings reads `.env` (must run from `backend/`)
- Alembic at revision `858813776375` (head)
- 17 tables live in Supabase + alembic_version tracking
- 11 Postgres enums, pgvector + HNSW index, pgcrypto + citext extensions

### Models (`backend/app/models/`)
- 17 models with full relationships
- `pg_enum()` helper binds Python enums to existing Postgres enum types
- Reserved-name columns (`metadata` on 3 tables) use `mapped_column("metadata", ...)` with Python attr name `extra_data`

### Auth (`backend/app/`)
- **Security** (`app/core/security.py`) — JWT encode/decode, bcrypt direct (NOT passlib), TokenData Pydantic model
- **Encryption** (`app/core/encryption.py`) — Fernet wrapper with module-level `platform_encryption` singleton
- **Database** (`app/core/database.py`) — async engine configured for Supabase pooler, `get_db()` dependency
- **Permissions** (`app/core/permissions.py`) — `get_current_user`, `require_super_admin`, `require_business_admin`, `get_business_id_filter`
- **Schemas** (`app/schemas/auth.py`) — RegisterRequest, LoginRequest, UserOut, etc. with EmailStr validation
- **Service** (`app/services/auth_service.py`) — HTTP-agnostic logic + 4 custom exceptions
- **Router** (`app/routers/auth.py`) — 5 endpoints mounted at `/api/v1/auth`:
  - `POST /register` — public, creates business + admin
  - `POST /login` — public, sets cookies
  - `POST /logout` — clears cookies (204)
  - `POST /refresh` — uses refresh cookie, re-issues access cookie
  - `GET /me` — JWT required, returns current user
- httpOnly cookies, samesite=lax, secure flag only in prod/staging

### Scripts (`backend/scripts/`)
- `verify_tables.py` — list all tables (smoke test after migrations)
- `verify_db_session.py` — async session roundtrip (smoke test)
- `verify_demo_data.py` — row counts by entity
- `create_super_admin.py` — bootstrap super admin (env or interactive). Idempotent: detects existing.
- `seed_demo_data.py` — creates 3 demo businesses (Dhaka Dental, Quick HVAC, Rahman Law) with full setup. Idempotent.

### Tests (`backend/tests/`)
- `conftest.py` — fresh `AsyncEngine` per test (avoids closed-loop bugs), `unique_slug`/`unique_email` helpers
- `test_auth.py` — 4 integration tests, all green:
  1. register happy path → 201
  2. login happy path → 200 + cookies set
  3. /auth/me without auth → 401
  4. `require_super_admin` invoked on business_admin → 403

### Database state in Supabase
- 1 super admin (you)
- 4 businesses: `test-dental` (from manual Swagger testing) + `dhaka-dental` + `quick-hvac` + `rahman-law`
- 4 business admins (one for test-dental, one per demo business)
- 15 services, 21 operating hours rows, 30 FAQs

### Frontend (`frontend/`)
- Next.js 16 + Tailwind v4 + shadcn/ui scaffold ready
- No pages built yet (Phase 2 starts here)

---

## Decisions made that override the planning docs

1. **Next.js 16, not 14.** Latest at scaffold time. Tailwind v4 (CSS-first config in `globals.css`).

2. **Supabase URL pattern (CRITICAL).**
   - `DATABASE_URL` (async, FastAPI runtime) → **Transaction pooler**, port **6543**, `postgresql+asyncpg://`
   - `DATABASE_URL_SYNC` (sync, Alembic) → **Session pooler**, port **5432**, `postgresql+psycopg2://`
   - Pooler host: `aws-1-ap-southeast-2.pooler.supabase.com` (NOT `ap-southeast-1` — Supabase migrated the project's endpoint at some point; the actual working host is `ap-southeast-2`)
   - Username format: `postgres.PROJECT_REF` (with the dot-ref suffix)
   - Do NOT use "Direct connection" (`db.xxx.supabase.co:5432`) — IPv6-only on free tier
   - **Async pooler config required** (see gotcha #11 below): `statement_cache_size=0` + randomized `prepared_statement_name_func`

3. **bcrypt direct, not passlib.** passlib 1.7.4 is unmaintained and incompatible with bcrypt 5.x. `app/core/security.py` calls `bcrypt.gensalt(rounds=12)` / `bcrypt.checkpw` directly. pyproject.toml deps: `bcrypt>=4.0.0` (no passlib).

4. **`PLATFORM_ENCRYPTION_KEY` requires a real Fernet key**, not a placeholder. Generate via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

5. **`pydantic[email]>=2.7.0`** in deps (not bare `pydantic`). Pydantic's `EmailStr` requires the optional `email-validator` package.

6. **Numbered enum names use SCREAMING_SNAKE_CASE in Python**, lowercase string values to match Postgres labels exactly.

7. **Reserved column name `metadata`.** SQLAlchemy DeclarativeBase reserves `metadata`. On 3 tables (`audit_logs`, `messages`, `embeddings`), the Postgres column is forced via `mapped_column("metadata", JSONB, ...)` and the Python attribute is `extra_data`.

8. **No `lazy=` relationship defaults.** Per-query `selectinload()` / `joinedload()` will be used when service-layer queries need it.

9. **JWT subject is user UUID string** (immutable), not email. `role` and `business_id` travel as separate claims. Refresh tokens carry only `sub` — role/business_id are re-read from DB at refresh time.

10. **Cookie security flags depend on environment.** `secure=True` only when `ENVIRONMENT in {"prod", "staging"}`. Dev cookies must NOT be secure or browsers reject them over HTTP.

11. **Test DB strategy:** Phase 1.8c tests use a fresh `AsyncEngine` per test (not the module-level engine) to avoid pytest-asyncio's closed-loop bug. Tests commit data; collision avoided via unique slugs/emails. A dedicated test schema is deferred to Phase 4+.

---

## Gotchas discovered (avoid re-hitting these)

1. **pyproject.toml hatchling config** must include `[tool.hatch.build.targets.wheel] packages = ["app"]` or editable install fails.

2. **`.env` parsing** — duplicate-prefix typos (`KEY=KEY=value`) silently mangle config. Sanity-check loaded settings if values look wrong.

3. **Secret exposure** — never print env var values. Mask scheme + host + port + `***` for debugging. Rotate any credential that has appeared in chat or logs.

4. **Supabase IPv6 issue** — direct (non-pooler) hostnames fail DNS from Bangladesh. Use the pooler.

5. **`sa.Enum` ignores `create_type=False` inside `op.create_table`.** Use `postgresql.ENUM(...)` from the dialect-specific module instead. The PG dialect's ENUM honors the flag correctly. **Rule for all future migrations:** `from sqlalchemy.dialects import postgresql` and `postgresql.ENUM(values, name='...', create_type=False)`.

6. **Circular FK cycles need deferred constraint creation.** `bookings.conversation_id` ↔ `conversations.booking_id`. **Pattern in migration:** create one table without the offending FK, create the second, then `op.create_foreign_key(...)` after both exist. Mirror in `downgrade()`.

7. **Chat-to-terminal autolink corruption.** Filenames ending `.py` get auto-linkified by the chat UI. Copy-pasting can produce `verify_[tables.py](http://tables.py)` where `verify_tables.py` was meant. Disk and git history are USUALLY fine. Trust `git log --name-only` and import-test results, not shell display.

8. **`alembic check` exits non-zero when schema is out of sync.** Intentional. "FAILED" just means autogenerate sees pending changes.

9. **Alembic autogenerate drops DESC ordering on indexes.** Always grep generated migrations for `_desc` and verify they use `sa.literal_column('created_at DESC')`.

10. **passlib 1.7.4 is incompatible with bcrypt 5.x.** passlib reads `bcrypt.__about__.__version__` which the newer bcrypt removed; then falls back to a self-test that hits a 72-byte limit. **Fix:** drop passlib, use bcrypt directly. Schema unchanged (bcrypt hashes are bcrypt hashes).

11. **asyncpg + Supabase transaction pooler require `statement_cache_size=0` + randomized `prepared_statement_name_func`.** Otherwise prepared-statement names like `__asyncpg_stmt_1__` collide across pooled connections (DuplicatePreparedStatementError). Both flags are set in `app/core/database.py` `create_async_engine` connect_args.

12. **Supabase free tier projects pause after inactivity.** Symptom: `asyncpg.exceptions.InternalServerError: tenant/user postgres.<ref> not found`. Fix: open the Supabase dashboard and click "Restore project". Takes ~1 minute to wake.

13. **`PLATFORM_ENCRYPTION_KEY` must be a real Fernet key.** If `.env` has the placeholder, `app/core/encryption.py` will raise `EncryptionError` at module import. Generate via `Fernet.generate_key().decode()`.

14. **All `python -c` checks must run from `backend/`.** Pydantic Settings discovers `.env` relative to cwd. Running from repo root makes Python see no env vars and crash with "Field required" for every config field.

15. **pytest-asyncio + module-level async engine = "Event loop is closed".** Each test gets a fresh event loop, but the engine's pool keeps connections bound to previous (now-closed) loops. **Fix:** create a fresh `AsyncEngine` per test in `conftest.py`, dispose at teardown. Do NOT use the module-level `engine` from `app.core.database` directly in tests.

16. **Pydantic `EmailStr` requires email-validator.** Without it, schema modules fail at import with `ImportError: email-validator is not installed`. Declare `pydantic[email]` in pyproject.toml deps.

17. **Never paste real credentials into chat.** Even local-dev creds. Conversation logs, screenshots, and training pipelines may retain them. Treat the chat like a public forum.

---

## Workflow established (keep this going)

- **🤖 Claude Code** → ONLY file creation and code editing. No shell commands.
- **👤 User runs in terminal** → ALL shell commands (git, pip, alembic, uvicorn, pnpm, pytest, etc.) by copy-paste from web-chat Claude's messages.
- **👤 User handles** → third-party dashboards (Supabase, Stripe, Vapi), pasting secrets into `.env`, final review decisions, password rotation.
- **One step at a time.** Small steps with clear copy-paste commands.
- **Sub-phase sized commits.** Each Phase 1 sub-phase was its own commit. Easy to revert/review.
- **Verify before committing.** Quick Python or pytest check after each Claude Code edit confirms it works.

---

## What's next — Phase 2

Per `docs/05-build-phases.md` — 4–5 days.

**Goal:** Business admin logs in, sees a dashboard, can CRUD services and hours.

**Backend tasks:**
1. `routers/admin/business.py` — GET/PATCH business, PATCH settings, POST logo upload
2. `routers/admin/services.py` — full CRUD. Skip embedding sync (stub).
3. `routers/admin/hours.py` — GET/PUT operating hours, exceptions CRUD
4. `routers/admin/faqs.py` — CRUD. Skip embedding sync.
5. `integrations/supabase_storage.py` — image upload helper
6. Integration tests for services CRUD (create, list, update, delete, scope enforcement)

**Frontend tasks:**
1. `app/(public)/login/page.tsx` + Zustand auth store
2. `lib/api/client.ts` — fetch wrapper with cookies, error normalization
3. `components/layout/admin-sidebar.tsx` + admin auth guard layout
4. `app/admin/page.tsx` — dashboard shell with stat placeholders
5. `app/admin/services/page.tsx` + `[id]/page.tsx` — services CRUD UI
6. `app/admin/hours/page.tsx` — 7-day editor
7. `app/admin/faqs/page.tsx` — FAQ CRUD UI
8. `app/admin/settings/page.tsx` — business info, logo upload

**Done when:**
- Login as `owner@dhakadental.com` (password `demo1234`) → see sidebar → click Services → see 5 seeded services → edit one → see change persist
- Edit hours → see change in Supabase
- Upload logo → see it on dashboard

Phase 2 sub-phase plan (to be confirmed at start):
- **2.1** — backend admin/business + admin/services CRUD + tests
- **2.2** — backend admin/hours + admin/faqs CRUD + tests
- **2.3** — Supabase storage integration for logos
- **2.4** — frontend auth store + login page + protected layout
- **2.5** — frontend services + hours + faqs pages
- **2.6** — frontend settings + dashboard shell

---

## Resume instructions for next Claude chat

1. Read `CLAUDE.md` at project root
2. Read all 9 files in `docs/`, especially this one
3. Confirm understanding by summarizing:
   - Current state: Phase 1 complete; auth tested end-to-end; 1 super admin + 4 businesses + demo data in Supabase. Phase 2 next.
   - Supabase URL pattern: pooler at `aws-1-ap-southeast-2`, async port 6543, `statement_cache_size=0`.
   - The 17 gotchas — especially: `postgresql.ENUM` (not `sa.Enum`); bcrypt direct (not passlib); fresh engine per test; never paste creds.
4. Wait for the user to say "start Phase 2.1" before producing prompts.
