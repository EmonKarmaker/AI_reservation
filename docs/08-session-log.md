# Session Log — Phase 1 Data Layer Complete (1.1–1.4); Phase 1.5 Next

## What this document is
This is the **handoff state** of the AI Reservation SaaS project. When a new Claude chat session starts, read this first (after reading `CLAUDE.md` at the project root and the other 8 docs in `docs/`). It captures what's done, what decisions were made that override earlier docs, and what's next.

---

## Project state as of handoff

**Phase 0 — COMPLETE.**
**Phase 1.1 through 1.4 — COMPLETE.** Database now has all 17 tables live.
**Phase 1.5 — NEXT** (security utilities: `app/core/security.py`, `app/core/encryption.py`).

Commit history:

Phase 0:
- `546250c` — feat(phase-0): project setup complete (backend skeleton, migration, docs)
- `d529605` — feat(phase-0): frontend scaffold (Next.js 16, shadcn/ui)

Phase 1:
- `5aa6859` — feat(phase-1.1): SQLAlchemy Base, mixins, and Postgres enum classes
- `662cae5` — feat(phase-1.2): platform-level models (User, PlatformSetting, AuditLog)
- `b90f76b` — feat(phase-1.3a): business tenant foundation models (Business, BusinessSetting, OperatingHours, ScheduleException)
- `0990d52` — feat(phase-1.3b): booking core models (Service, Customer, Booking, Payment)
- `64727b5` — feat(phase-1.3c): AI + infra models (Conversation, Message, Escalation, Faq, Embedding, WebhookEvent); all 17 tables defined
- `688892f` — feat(phase-1.3d): wire SQLAlchemy relationships across all models
- `b7fa17e` — feat(phase-1.4a): wire Base.metadata into Alembic with pgvector render + enum skip hooks
- `3de3f91` — feat(phase-1.4bc): generate and patch migration for all 17 tables (resolve bookings<->conversations FK cycle, fix audit_logs DESC index)
- `3e16890` — fix(phase-1.4c): use postgresql.ENUM with create_type=False so migration applies cleanly
- `7c80a3e` — feat(phase-1.4d): apply migration; add verify_tables.py helper script

---

## What works right now

### Backend (`backend/`)
- Python 3.11.9 in `.venv`
- FastAPI 0.136.0 + async SQLAlchemy 2.0.49 + asyncpg 0.31.0 + Pydantic 2.13.3 + pgvector 0.4.2 (Python lib)
- `app/main.py` with `/health` endpoint returning `{"status":"ok"}`
- `app/config.py` using `pydantic-settings`, loads from `.env`
- CORS wired to `FRONTEND_ORIGIN`
- Swagger UI at `/docs` in dev mode
- `pyproject.toml` with all deps including `pgvector>=0.3.0`; ruff + mypy + pytest configured
- Alembic initialized in `backend/alembic/` with `env.py` configured to:
  - read sync URL from settings
  - expose `Base.metadata` for autogenerate
  - filter pre-existing enum types via `include_object`
  - render `pgvector.sqlalchemy.Vector` columns via `render_item`

### Models (`backend/app/models/`)
- 18 Python files: `base.py`, `enums.py`, `__init__.py`, plus 17 model files (one per table)
- All 17 models register on `Base.metadata`
- All SQLAlchemy relationships wired via `back_populates` on both sides
- `configure_mappers()` runs cleanly with no errors
- `pg_enum()` helper in `base.py` binds Python enums to existing Postgres enum types with `create_type=False` and `values_callable=lambda cls: [m.value for m in cls]`
- Three Postgres reserved-name columns (`metadata` on `audit_logs`, `messages`, `embeddings`) use Python attribute name `extra_data` via `mapped_column("metadata", ...)` positional first arg

### Database (Supabase free tier)
- Project: `tmndmosvvymncvvndyuy` (region: ap-southeast-1 / Singapore)
- Extensions live: `pgcrypto 1.3`, `citext 1.6`, `vector 0.8.0`
- Enums live (11 total): booking_status, business_status, conversation_channel, conversation_status, day_of_week, embedding_source_type, escalation_priority, escalation_status, message_role, payment_status, user_role
- **Tables live (17):** audit_logs, bookings, business_settings, businesses, conversations, customers, embeddings, escalations, faqs, messages, operating_hours, payments, platform_settings, schedule_exceptions, services, users, webhook_events
- Plus `alembic_version` table (Alembic-managed)
- Alembic at revision `858813776375` (head)
- HNSW cosine-similarity index on `embeddings.embedding`
- Deferred FK `fk_bookings_conversation_id` installed after both tables exist (resolves circular dependency)

### Verify helper (`backend/scripts/verify_tables.py`)
- Lists every table in the `public` schema. Run from `backend/`:
  `.venv\Scripts\python scripts\verify_tables.py`
- Should print 18 tables (17 + `alembic_version`)

### Frontend (`frontend/`)
- Next.js 16.2.4 + Turbopack + TypeScript strict + Tailwind v4 + App Router + `src/` dir + `@/*` alias
- shadcn/ui initialized with `base-nova` preset, CSS variables on
- Components installed: button, card, dialog, input, label, select, sonner, table
- Libraries installed: `react-hook-form`, `@hookform/resolvers`, `zod`
- `.env.local` and `.env.example` present, properly gitignored
- `AGENTS.md` + `CLAUDE.md` in frontend/ — Next.js 16 scaffold warnings, kept intentionally

### Docs
- 9 planning docs in `docs/` (00–08)
- `CLAUDE.md` at project root with full project briefing including Phase 1 status
- This file (`docs/08-session-log.md`) tracking current session state

---

## Decisions made that override the planning docs

1. **Next.js 16, not 14.** The scaffold installed latest. Tailwind v4 (not v3). Treat `00-overview.md`'s "Next.js 14" as "Next.js 14+ / current stable."

2. **Tailwind v4 config is CSS-first.** No `tailwind.config.ts` file — config lives in `src/app/globals.css` via `@theme` directive.

3. **Supabase connection URL pattern (CRITICAL).**
   - `DATABASE_URL` (async, FastAPI runtime) → **Transaction pooler** at port 6543, driver `postgresql+asyncpg://`
   - `DATABASE_URL_SYNC` (sync, Alembic) → **Session pooler** at port 5432, driver `postgresql+psycopg2://`
   - Both go through `aws-0-ap-southeast-1.pooler.supabase.com`
   - Username format: `postgres.PROJECT_REF` (with the dot-ref suffix) — required by pooler
   - Do NOT use "Direct connection" (`db.xxx.supabase.co:5432`) — IPv6-only on free tier, fails DNS from Bangladesh.

4. **shadcn `form` component.** No standalone registry entry in current shadcn version. Have `react-hook-form` + `zod` installed. Create `form.tsx` wrapper manually in Phase 2 when first form is built.

5. **shadcn `toast` is deprecated** → using `sonner`.

6. **Python 3.11, not 3.12.** User prefers 3.11 for stability. `pyproject.toml` says `requires-python = ">=3.11"`.

7. **Numbered enum names use SCREAMING_SNAKE_CASE in Python**, lowercase string values to match Postgres labels exactly. Bound via the `pg_enum()` helper.

8. **Reserved column name `metadata`.** Schema doc names the column `metadata` on three tables (`audit_logs`, `messages`, `embeddings`). SQLAlchemy's `DeclarativeBase` reserves `metadata` as a class attribute, so the Python attribute is `extra_data` and the Postgres column name is forced via the positional first arg: `mapped_column("metadata", JSONB, ...)`.

9. **Models for `PlatformSetting`, `AuditLog`, `WebhookEvent` have NO `relationship(...)` calls.** They're either polymorphic (`AuditLog.entity_id`, `Embedding.source_id`) or singleton-ish (`PlatformSetting`, `WebhookEvent`) so traversal in Python isn't useful.

10. **No `lazy="selectin"` defaults on relationships.** Default loading strategy. Per-query `selectinload()` / `joinedload()` will be used when service-layer queries are written in later phases — gives per-query control and matches `docs/07-conventions.md`.

---

## Gotchas discovered (avoid re-hitting)

1. **pyproject.toml hatchling config** — must include `[tool.hatch.build.targets.wheel] packages = ["app"]` or editable install fails with "unable to determine which files to ship".

2. **`.env` parsing** — duplicate-prefix typos (`KEY=KEY=value`) silently mangle config. Sanity-check loaded settings if they look wrong.

3. **Secret exposure** — strict rule: **never print, log, or echo env var values**. Use masked prints only (scheme + host + port + `***`). Rotate any credential that has appeared in chat or logs.

4. **Supabase IPv6 issue** — see decision #3. If a connection error says "could not translate host name" on a `db.xxx.supabase.co` host → switch to pooler.

5. **Line ending warnings** (`LF will be replaced by CRLF`) — harmless on Windows, ignore.

6. **`sa.Enum` ignores `create_type=False` inside `op.create_table`.** When the bootstrap migration `8c5d604ee81d` created all 11 enum types, the Phase 1.4 migration's `op.create_table()` calls referenced them via `sa.Enum(name='...', create_type=False)`. SQLAlchemy ignored the flag and emitted `CREATE TYPE` via a `before_create` event hook → "type already exists" failure. **Fix:** use `postgresql.ENUM(...)` from the dialect-specific module instead — the PG dialect's ENUM honors `create_type=False` correctly. **Rule for all future migrations involving enums:** `from sqlalchemy.dialects import postgresql` and use `postgresql.ENUM(values, name='...', create_type=False)`. Document this in any new migration that touches enums.

7. **Circular FK cycles need deferred constraint creation.** `bookings.conversation_id` → `conversations.id` and `conversations.booking_id` → `bookings.id` form a cycle. Alembic autogenerate emits `SAWarning: Cannot correctly sort tables` and writes tables in alphabetical order, which fails because `bookings` references `conversations` before it exists. **Fix pattern in migration:** (a) create `bookings` without the `conversation_id` FK (column stays, FK constraint omitted from `ForeignKeyConstraint` list), (b) create `conversations` normally with its FK to `bookings.id` since `bookings` now exists, (c) at end of `upgrade()`, `op.create_foreign_key('fk_bookings_conversation_id', 'bookings', 'conversations', ['conversation_id'], ['id'], ondelete='SET NULL')`. In `downgrade()`, drop the deferred FK first via `op.drop_constraint('fk_bookings_conversation_id', 'bookings', type_='foreignkey')`, then drop tables in reverse dependency order.

8. **Chat-to-terminal autolink corruption.** Filenames ending in `.py` get auto-linkified by the chat UI's Markdown rendering. Copy-pasting a filename into PowerShell can result in `verify_[tables.py](http://tables.py)` arriving where `verify_tables.py` was meant. Symptoms: bracket-laden errors, `findstr: Cannot open` errors, weird `Cannot find drive` errors. **Disk and git history are usually fine** — the corruption is in transit, not on disk. **Workarounds:** type filenames manually, use PowerShell tab completion (`scripts\v` + Tab), check ground truth via `git log --name-only` (which doesn't autolink), or use VS Code's file explorer for renames.

9. **`alembic check` exits non-zero when schema is out of sync.** This is intentional and correct — the command exists to detect drift. "FAILED: New upgrade operations detected" simply means autogenerate sees changes that need a new migration. Not an error in the configuration sense.

10. **Alembic autogenerate drops DESC ordering on indexes.** When a model declares `Index('foo', text('created_at DESC'))`, autogenerate sometimes renders the index as `['created_at']` (no DESC) in the migration. Always grep generated migrations for index names ending in `_desc` and verify the migration uses `sa.literal_column('created_at DESC')`. We patched `ix_audit_logs_created_at_desc` manually in `3de3f91`.

---

## Workflow established (keep this going)

- **🤖 Claude Code** → ONLY file creation and code editing. No shell commands.
- **👤 User runs in terminal** → ALL shell commands (git, pip, alembic, uvicorn, pnpm, etc.) by copy-paste from web-chat Claude's messages.
- **👤 User handles** → third-party dashboards (Supabase, etc.), pasting secrets into `.env`, final review decisions.
- **One step at a time.** Small steps with clear copy-paste commands, not long combined instructions.
- **Sub-phase sized commits.** Each Phase 1 sub-phase (1.1, 1.2, 1.3a, 1.3b, 1.3c, 1.3d, 1.4a, 1.4b/c, 1.4d) is its own commit. Easy to revert, easy to review.
- **Verify before committing.** After every Claude Code edit, run a small Python check (`from app.models import Base; print(...)`) or an Alembic command to confirm the change actually works before staging.

---

## What's next — Phase 1.5

Per `docs/05-build-phases.md`:

- **Phase 1.5** — Security utilities
  - `app/core/security.py`: JWT encode/decode, bcrypt password hash + verify, `get_current_user` dependency
  - `app/core/encryption.py`: Fernet wrapper around `PLATFORM_ENCRYPTION_KEY` for `platform_settings.value_encrypted` and `business_settings.custom_api_key_encrypted`
- **Phase 1.6** — Permission dependencies
  - `app/core/permissions.py`: `require_super_admin`, `require_business_admin`, `require_business_admin_for_self_or_super_admin`
- **Phase 1.7** — Auth endpoints per `docs/03-api.md` section 1
  - `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/refresh`
  - httpOnly cookies, JWT in `access_token`, refresh in `refresh_token`
- **Phase 1.8** — Bootstrap + seed + tests
  - `scripts/create_super_admin.py` — interactive (or env-driven) super admin creation
  - `scripts/seed_demo_data.py` — 3 demo businesses (Dental, HVAC, Law), 5 services each, 7 days of hours, 10 FAQs each, 1 business admin per business
  - 4 integration tests: register, login, 401 on protected route without auth, 403 on wrong role

Phase 1 done-when conditions:
- All 17 tables exist in Supabase ✅ DONE
- `POST /auth/login` with seeded business admin returns JWT cookie
- `GET /auth/me` with that cookie returns user + role
- Calling a business admin route as non-admin returns 403
- 4 integration tests green

---

## Resume instructions for next Claude chat

1. Read `CLAUDE.md` at project root
2. Read all 9 files in `docs/` (especially this one — it's the freshest state)
3. Confirm understanding by summarizing:
   - Current state: Phase 1.1–1.4 done, all 17 tables live in Supabase, Alembic at `858813776375 (head)`. Phase 1.5 next.
   - The Supabase URL pattern (pooler, not direct).
   - The workflow rules (Claude Code for files only, user runs commands).
   - Three critical gotchas to keep in mind: `postgresql.ENUM` for migration enums (not `sa.Enum`); deferred FK pattern for bookings↔conversations cycle; chat autolink trap on `.py` filenames.
4. Ask user to say "start Phase 1.5" when ready
5. Begin with Phase 1.5 — small commit-sized chunks, one at a time
