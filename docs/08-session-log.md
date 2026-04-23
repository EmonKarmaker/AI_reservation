# Session Log — Phase 0 Complete, Phase 1 Starting

## What this document is
This is the **handoff state** of the AI Reservation SaaS project. When a new Claude chat session starts, read this first (after reading `CLAUDE.md` and the other 8 docs in `docs/`). It captures what's done, what decisions were made that override earlier docs, and what's next.

---

## Project state as of handoff

**Phase 0 — COMPLETE.** Both git commits locked in.

Commit history:
- `546250c` — feat(phase-0): project setup complete (backend skeleton, migration, docs)
- `d529605` — feat(phase-0): frontend scaffold (Next.js 16, shadcn/ui)

---

## What works right now

### Backend (`backend/`)
- Python 3.11.9 in `.venv`
- FastAPI 0.136.0 + async SQLAlchemy 2.0.49 + asyncpg 0.31.0 + Pydantic 2.13.3
- `app/main.py` with `/health` endpoint returning `{"status":"ok"}`
- `app/config.py` using `pydantic-settings`, loads from `.env`
- CORS wired to `FRONTEND_ORIGIN`
- Swagger UI at `/docs` in dev mode
- `pyproject.toml` with all deps, ruff + mypy + pytest configured
- Alembic initialized in `backend/alembic/` with `env.py` configured to read from settings
- One migration applied: `8c5d604ee81d_extensions_and_enums` — creates pgcrypto, citext, pgvector extensions + 11 Postgres enums per `docs/01-schema.md`

### Database (Supabase free tier)
- Project: `tmndmosvvymncvvndyuy` (region: ap-southeast-1 / Singapore)
- Extensions live: `pgcrypto 1.3`, `citext 1.6`, `vector 0.8.0`
- Enums live (11 total): booking_status, business_status, conversation_channel, conversation_status, day_of_week, embedding_source_type, escalation_priority, escalation_status, message_role, payment_status, user_role
- No tables yet — those come in Phase 1

### Frontend (`frontend/`)
- Next.js 16.2.4 (NOT 14 — scaffold gave us latest) + Turbopack + TypeScript strict + Tailwind v4 + App Router + `src/` dir + `@/*` alias
- shadcn/ui initialized with `base-nova` preset, CSS variables on
- Components installed: button, card, dialog, input, label, select, sonner, table
- Libraries installed: `react-hook-form`, `@hookform/resolvers`, `zod`
- `.env.local` and `.env.example` present, properly gitignored
- `AGENTS.md` + `CLAUDE.md` in frontend/ — Next.js 16 scaffold warnings about v16 breaking changes, kept intentionally

### Docs
- 8 planning docs in `docs/` (00–07)
- `CLAUDE.md` at project root with full project briefing
- This file (`docs/08-session-log.md`) tracking session state

---

## Decisions made that override the planning docs

1. **Next.js 16, not 14.** The scaffold installed latest. Tailwind v4 (not v3). `docs/00-overview.md` says "Next.js 14" — treat as "Next.js 14+" / "Next.js current stable."

2. **Tailwind v4 config is CSS-first.** No `tailwind.config.ts` file anymore — config lives in `src/app/globals.css` via `@theme` directive. shadcn already handled this.

3. **Supabase connection URL pattern (CRITICAL, keep this).**
   - `DATABASE_URL` (async, for FastAPI runtime) → **Transaction pooler** at port 6543, driver `postgresql+asyncpg://`
   - `DATABASE_URL_SYNC` (sync, for Alembic) → **Session pooler** at port 5432, driver `postgresql+psycopg2://`
   - Both go through `aws-0-ap-southeast-1.pooler.supabase.com` (the pooler host)
   - Username format: `postgres.PROJECT_REF` (with the dot-ref suffix) — required by pooler
   - Do NOT use "Direct connection" (`db.xxx.supabase.co:5432`) — it's IPv6-only on free tier, fails DNS resolution from Bangladesh (and many ISPs). This cost us ~1h of debugging.

4. **shadcn `form` component.** No standalone registry entry in current shadcn version. We have `react-hook-form` + `zod` installed. Create `form.tsx` wrapper manually in Phase 2 when first form is built.

5. **shadcn `toast` is deprecated** → using `sonner` instead. Same purpose, better API.

6. **Python 3.11, not 3.12.** Docs originally said 3.12+. User prefers 3.11 for stability. `pyproject.toml` now says `requires-python = ">=3.11"`.

---

## Gotchas discovered (avoid re-hitting)

1. **pyproject.toml hatchling config** — must include `[tool.hatch.build.targets.wheel] packages = ["app"]` or editable install fails with "unable to determine which files to ship".

2. **`.env` parsing** — user pasted `KEY=KEY=value` once (duplicate prefix). If config values look weird, check for this.

3. **Secret exposure** — user has pasted DB passwords in chat twice via Claude Code output. Strict rule in place: **never print, log, or echo env var values**. Use masked prints only (show scheme + host + port + `***` for password). Remind user to rotate any credential that appears in chat or logs.

4. **Supabase IPv6 issue** — see decision #3. If any connection error says "could not translate host name" on a `db.xxx.supabase.co` host → switch to pooler.

5. **Line ending warnings** (`LF will be replaced by CRLF`) — harmless on Windows, ignore.

---

## Workflow established (keep this going)

- **🤖 Claude Code** → ONLY file creation and code editing. No shell commands.
- **👤 User runs in terminal** → ALL shell commands (git, pip, alembic, uvicorn, pnpm, etc.) by copy-paste from my messages.
- **👤 User handles** → third-party dashboards (Supabase, etc.), pasting secrets into `.env`, final review decisions.
- **One step at a time.** User prefers small steps with clear copy-paste commands, not long combined instructions.
- **Short plain-English explanation at the top of every doc** — user asked for this on Document 2 onwards. Keep the pattern.

---

## What's next — Phase 1

Phase 1 per `docs/05-build-phases.md` = data layer + auth. Break it into 8 sub-phases so we commit after each:

- **Phase 1.1** — Base classes, mixins, enums in Python (`app/models/base.py`, `app/models/enums.py`)
- **Phase 1.2** — Platform-level models (users, platform_settings, audit_logs)
- **Phase 1.3** — Business-level models (businesses, business_settings, operating_hours, schedule_exceptions, services, customers, bookings, payments, conversations, messages, escalations, faqs, embeddings, webhook_events) — 14 tables
- **Phase 1.4** — Wire `Base.metadata` into Alembic `env.py`, generate + review autogenerated migration, apply it
- **Phase 1.5** — Security utilities (`app/core/security.py`: JWT encode/decode, bcrypt password hash, `get_current_user` dependency; `app/core/encryption.py`: Fernet wrapper)
- **Phase 1.6** — Permission dependencies (`app/core/permissions.py`: `require_super_admin`, `require_business_admin`)
- **Phase 1.7** — Auth endpoints per `docs/03-api.md` section 1: `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/refresh`. httpOnly cookies.
- **Phase 1.8** — `scripts/create_super_admin.py` bootstrap + `scripts/seed_demo_data.py` (3 demo businesses: Dental, HVAC, Law; 5 services each; 7 days of hours; 10 FAQs each) + 4 integration tests (register, login, 401 on protected route without auth, 403 on wrong role)

Phase 1 done-when conditions:
- All 17 tables exist in Supabase
- `POST /auth/login` with seeded business admin returns JWT cookie
- `GET /auth/me` with that cookie returns user + role
- Calling a business admin route as non-admin returns 403
- 4 integration tests green

---

## Resume instructions for next Claude chat

1. Read `CLAUDE.md` at project root
2. Read all 9 files in `docs/` (especially this one — it's the freshest state)
3. Confirm understanding by summarizing:
   - Current state (Phase 0 done, Phase 1 next)
   - The Supabase URL pattern (pooler, not direct)
   - The workflow rules (Claude Code for files only, user runs commands)
   - The 8 sub-phases of Phase 1
4. Ask user to say "start Phase 1.1" when ready
5. Begin with Phase 1.1 — small commit-sized chunks, one at a time
