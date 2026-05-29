# Session Log — Phases 0-3 Complete; Phase 4 In Progress (4.1-4.5, 4.7 done; 4.6 + 4.8 pending)

## What this document is
This is the **handoff state** of the AI Reservation SaaS project. New Claude chats should read this after `CLAUDE.md` and the other 8 docs in `docs/`. It captures what's done, what decisions override the planning docs, and what's next.

---

## Project state as of handoff

**Phase 0 — COMPLETE.**
**Phase 1 (all sub-phases) — COMPLETE.** Auth works end-to-end with cookies.
**Phase 2 (all sub-phases) — COMPLETE.** Full admin CRUD across services, hours, FAQs, business profile + settings; frontend pages live.
**Phase 3 (all sub-phases) — COMPLETE.** Local MiniLM embeddings (384-dim), sync on CRUD, backfill done. 51 embeddings in DB (20 service, 31 faq).
**Phase 4 — IN PROGRESS.**
- 4.1 Groq LLM integration — DONE
- 4.2 RAG retrieval helper (pgvector cosine) — DONE
- 4.3 Minimal 3-node graph (retrieve → answer) — DONE
- 4.4 Conversation persistence (4-node graph w/ history) — DONE
- 4.5 Intent classification + conditional branching (question / booking / escalate) — DONE
- 4.6 Booking flow (15+ nodes) — PENDING (the big one)
- 4.7 Public chat endpoint + Next.js widget at /chat/[slug] — DONE
- 4.8 Escalation email via Resend — PENDING

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

Phase 2 (admin CRUD backend + frontend, multiple commits across sub-phases 2.1-2.6).
Phase 2 outcome: business owner can log in and CRUD services, hours, FAQs, business profile, and settings end-to-end. 14 backend integration tests pass.

Phase 3 (embeddings):
- `0736dbd` — feat(phase-3.1): sentence-transformers MiniLM embeddings module (384-dim local, lazy-loaded)
- `fd93ac2` — feat(phase-3.2-3.4): embedding sync service and admin router wiring; embeddings now generated on service/FAQ create/update/delete
- `936b1d8` — feat(phase-3.5): backfill_embeddings script; Phase 3 complete (51 embeddings in DB)

Phase 4 (chatbot, in progress):
- `9599e6d` — feat(phase-4.1): Groq LLM integration with chat_completion wrapper and dual-tier model config (FAST = llama-3.1-8b-instant, SMART = llama-3.3-70b-versatile)
- (4.2 commit) — feat(phase-4.2): RAG retrieval helper with pgvector cosine search; verified against Dhaka Dental
- `848ec2b` — feat(phase-4.3): minimal LangGraph 3-node chat (retrieve+answer); verified end-to-end against Dhaka Dental
- `046e230` — feat(phase-4.4): conversation persistence with history; 4-node graph (load_history+retrieve+answer+save_turn); anonymous customer auto-provisioning with synthetic email
- (4.5 commit) — feat(phase-4.5): intent classification with few-shot prompt + conditional branching to booking/escalate stubs; routing verified on 4-turn dialogue
- `14b2d92` — feat(phase-4.7a): public POST /api/v1/chat/{slug} endpoint; anonymous, auto-mints customer_id, returns conversation_id + intent
- `d054360` — feat(phase-4.7b): /chat/[slug] page with ChatWidget client component; localStorage-persisted customer_id; optimistic UI

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

18. **NullPool for SQLAlchemy + Supabase pgbouncer transaction pooler.** Supersedes the `prepared_statement_name_func` lambda in gotcha #11 — that workaround DOES NOT WORK because asyncpg caches the generated name on the connection. Symptom: 500 errors with `asyncpg.exceptions.InvalidSQLStatementNameError: prepared statement "__asyncpg_..." does not exist` after the first ~2 requests succeed. Cause: SQLAlchemy QueuePool reuses asyncpg connections; pgbouncer routes queries to different backend connections that haven't seen the prepared-statement name. **Fix:** `poolclass=NullPool` in `create_async_engine`. Each request opens a fresh asyncpg connection; pgbouncer handles real pooling. Tests passed because pytest uses fresh engines per test (per gotcha #15). Keep `statement_cache_size=0` as belt-and-suspenders. Both flags are set in `app/core/database.py`.

19. **`from __future__ import annotations` + `TYPE_CHECKING` import + dataclass state schema = LangGraph runtime NameError.** LangGraph's `StateGraph(MyState)` constructor calls `get_type_hints(MyState, include_extras=True)` at compile time, forcing evaluation of every annotation. Imports under `if TYPE_CHECKING:` aren't there at runtime → `NameError: name 'AsyncSession' is not defined`. **Fix:** anything annotated on a LangGraph state schema field must be runtime-importable. Move `from sqlalchemy.ext.asyncio import AsyncSession` (and similar) out of `TYPE_CHECKING` for state schema files.

20. **`conversations.session_token` is NOT NULL with no DB default.** Plain `Conversation(business_id=..., customer_id=..., channel=..., status=...)` insert fails with `NotNullViolationError`. The frontend was originally expected to mint and pass the session_token; for server-side chat creation, mint one with `secrets.token_urlsafe(32)` in `get_or_create_conversation`. General lesson: audit NOT NULL columns without server_default before relying on naive ORM inserts. Schema-vs-model gaps surface as runtime IntegrityError.

21. **`customers.ck_customers_email_or_phone` requires email OR phone.** Anonymous chat customers have neither when first contacting the chatbot. **Fix:** synthesize an email `anon-{customer_id}@chat.local` when creating a Customer row from anonymous chat. The `chat.local` domain is non-routable and unambiguously not real; the booking flow can overwrite with the real email later. Also: customers.customer_id is a FK to customers.id, so `get_or_create_conversation` must `_ensure_customer_exists` (create a placeholder Customer row keyed by the customer_id) BEFORE inserting the conversation.

22. **PowerShell expands `[name]` as a character-class wildcard.** `Get-Content src\app\chat\[slug]\page.tsx` silently matches nothing and returns empty (or errors with "Cannot find path"). Affects any Next.js dynamic-route directory. **Fix:** use `-LiteralPath`: `Get-Content -LiteralPath 'src\app\chat\[slug]\page.tsx'`. Or quote the bracketed segment: `'src\app\chat\`[slug`]\page.tsx'`. Or use VSCode/IDE file open. Claude Code's `view` tool handles this transparently.

23. **`str_replace` anchor mismatch fails silently.** If a multi-line `old_str` doesn't exactly match the file content (trailing whitespace, CRLF vs LF, slight indentation drift), Claude Code reports "edit applied" but the file is unchanged. **Mitigation:** verify after every significant edit with `findstr` or `Get-Content` for an unambiguous unique string from the new content. For multi-edit changes to one file, prefer deleting and recreating with `create_file` — single point of failure, easier to debug.

---

## Workflow established (keep this going)

- **🤖 Claude Code** → ONLY file creation and code editing. No shell commands.
- **👤 User runs in terminal** → ALL shell commands (git, pip, alembic, uvicorn, pnpm, pytest, etc.) by copy-paste from web-chat Claude's messages.
- **👤 User handles** → third-party dashboards (Supabase, Stripe, Vapi), pasting secrets into `.env`, final review decisions, password rotation.
- **One step at a time.** Small steps with clear copy-paste commands.
- **Sub-phase sized commits.** Each Phase 1 sub-phase was its own commit. Easy to revert/review.
- **Verify before committing.** Quick Python or pytest check after each Claude Code edit confirms it works.

---

## What's next — Phase 4.6 (the big one), then 4.8

### Phase 4.6 — Booking flow (multi-day)

**Goal:** Customer chats with the AI receptionist, picks a service, picks a date/time, provides contact info, and gets a confirmed booking row in the DB.

The booking node is replacing `booking_stub_node` in `app/services/chat_graph.py`. Per `docs/02-langgraph.md` the booking flow is ~15-18 nodes:

1. **service_selection** — extract service name from message or ask. Uses RAG with `source_types=[SERVICE]` filter; if multiple match, ask the customer to pick.
2. **date_extraction** — parse "Saturday", "tomorrow", "next week", explicit dates. Validate against business `booking_window_days`.
3. **time_slot_search** — query `operating_hours` + existing `bookings` for the date, return available slots respecting `service.duration_minutes` + `service.buffer_minutes`.
4. **time_selection** — ask customer to pick from slots (or propose nearest if they asked for a specific time).
5. **contact_collection** — ask for full_name, email, phone. Validate. Update the placeholder Customer row.
6. **payment_check** — if `business_settings.require_payment_at_booking`, route to Stripe payment intent creation; else skip.
7. **confirmation** — create Booking row (status=confirmed or pending_payment), update Conversation.booking_id, send confirmation message.
8. **escalation_fallback** — if any step fails (no slots, validation, payment fails), route to escalate_stub.

Watch for: re-routing on each turn (a customer might bail mid-booking with a question — the intent classifier already handles this).

**Sub-phase plan:**
- **4.6.1** — service_selection node (RAG-driven, with disambiguation)
- **4.6.2** — date + time slot logic (no LLM; deterministic date parsing + DB query)
- **4.6.3** — contact_collection node (updates placeholder Customer)
- **4.6.4** — Booking row creation + Conversation update; skip Stripe (deferred to Phase 5)
- **4.6.5** — End-to-end verification: chat → "I want to book a cleaning Saturday" → walks through full flow → booking row in DB

### Phase 4.8 — Escalation email via Resend

**Goal:** When `escalate_stub_node` fires, send an email to the business's `business_settings.escalation_email` so a human knows to follow up.

Small, contained: ~1-2 hours.

Files: `app/integrations/resend.py` (thin wrapper), update `escalate_stub_node` to call it best-effort.

Resend free tier: 3000 emails/month. Use `noreply@yourdomain` as From. Test mode initially.

### Tech debt to address before going to production
- 49 anonymous test businesses accumulated in Supabase from cumulative pytest runs. Tests should be torn down or use a dedicated schema. Phase 11 polish.
- Logo upload (Phase 2.3) was deferred. Needs Supabase Storage bucket + service-role key.
- Streaming chat responses (currently single fetch per turn). Polish for Phase 11.

---

## Resume instructions for next Claude chat

1. Read `CLAUDE.md` at project root
2. Read all 9 files in `docs/`, especially this one
3. Confirm understanding by summarizing:
   - Current state: Phases 0-3 complete; Phase 4 partially complete (4.1-4.5 + 4.7 done; 4.6 + 4.8 pending). Chatbot works end-to-end via `/chat/[slug]`; intent routing correct; conversation persistence working; booking is currently a stub.
   - Supabase URL pattern: pooler at `aws-1-ap-southeast-2`, async port 6543, **NullPool** (per gotcha #18).
   - The 23 gotchas — especially:
     - #18 (NullPool, supersedes #11's lambda)
     - #19 (LangGraph + TYPE_CHECKING incompatibility)
     - #20 + #21 (Customer + Conversation insert chain for anonymous chatbot customers)
     - #22 (PowerShell `[slug]` wildcard)
     - #23 (str_replace silent failure — always verify with findstr after edits)
   - Strict workflow: web-chat Claude writes file-edit prompts; user runs ALL shell commands; never ask Claude Code for shell commands or to print secrets.
4. Wait for the user to say what to start before producing prompts. Likely "start Phase 4.6.1" or "start Phase 4.8".
