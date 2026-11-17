# AI Reservation SaaS — Daily Context

> **Save this as `CONTEXT.md` at the repo root** (`E:\GitHub\AI_reservation\CONTEXT.md`), next to `CLAUDE.md`.
> Built on 2026-10-22 from a read-only audit of the real repo; last updated **2026-11-18** after Phase 4.6.5 / 4.6.6d.
> Items marked **(verify)** could not be confirmed from files alone.

**How to use it.** Start of day: read §1–§3, then paste the *Daily kickoff* prompt into Claude Code. End of day: update §1, tick §4, add a §11 entry, commit. Keep this file under ~350 lines; move old detail into `docs/08-session-log.md`.

---

## 1. Right now (EDIT THIS EVERY DAY)

| Field | Value |
|---|---|
| Date | 2026-11-18 |
| Phase / task | Phase 4 done once the changes below are verified + committed. Next: **Phase 5** (Stripe + confirmation emails) |
| Last commit | `488c232` feat(phase-4.6.6b) — today's work is **uncommitted** on disk (see §11, 2026-11-18) |
| Git | Branch `main`, tracks `origin/main`. Recovery done 2026-10-23 (Supabase resumed, app + 14 tests ran) |
| Status | Groq model switch, 4.6.5 edge cases, 4.6.6d side questions, 122 new tests — all passing on a local test DB |
| Blockers | Needs your run: `pip install -e ".[dev]"`, `pytest`, a live chat test (Groq), then commit |
| Next action | Follow §11 "To finish" for 2026-11-18, then start Phase 5 |

---

## 2. What this project is

Multi-tenant AI receptionist SaaS. A business configures services, hours and FAQs. Customers chat with an agent that answers from the business's own data (RAG) and books appointments. Planned: Stripe payments, Vapi voice, escalation dashboard, super-admin panel.

- Repo: `github.com/EmonKarmaker/AI_reservation` · local: `E:\GitHub\AI_reservation`
- Demo business: **Dhaka Dental Clinic**, slug `dhaka-dental`, timezone `Asia/Dhaka`. Also seeded: `quick-hvac`, `rahman-law`
- Demo login: `owner@dhakadental.com` (password is in `backend/scripts/seed_demo_data.py`)
- Planning docs: `docs/00`–`08`. Key: `01-schema`, `03-api`, `05-build-phases`

---

## 3. Workflow rules (non-negotiable)

1. **Claude Code = file creation and code edits only. No shell commands.**
2. **I run every shell command** (git, pip, pnpm, alembic, uvicorn, pytest, python) by copy-paste.
3. **I handle** third-party dashboards, pasting secrets into `.env`, and final review decisions.
4. **Never print, log or echo env var values.** Masked debugging only (scheme + host + port + `***`). Never paste real credentials into chat. Rotate anything that has appeared in chat or logs (the Supabase DB password was exposed twice).
5. **One small step at a time.** Before coding, state: phase → task → files → wait for "go".
6. **One commit per sub-phase.** Verify (pytest or a quick script) before committing.
7. **Single-line commit messages** in PowerShell.
8. After every non-trivial edit, **verify the file actually changed** (gotcha 23).
9. Short plain-English summary at the top of every new doc.
10. **Don't paste text containing `>` into PowerShell** (gotcha 31).

---

## 4. Phase tracker

**Phase 0 — Setup:** ✅
**Phase 1 — Data layer + auth (1.1–1.8c):** ✅ 17 tables, JWT cookie auth, super-admin + seed scripts
**Phase 2 — Admin dashboard + CRUD:** ✅ 2.1 (`6bb3354`) · 2.2 (`3ae478a`) · 2.4 (`d6e4aad`) · 2.5 (`22de666`) · 2.6 (`fd289c4`)
- ⬜ **2.3 logo upload: not built.** No `supabase_storage.py`, no upload endpoint. `logo_url` is just a text column. `SUPABASE_*` settings are unused
**Phase 3 — Embeddings:** ✅ 3.1–3.5 (MiniLM 384-dim, sync on CRUD, backfill, 51 embeddings)
- ⬜ **Public landing page: not built.** `frontend/src/app/page.tsx` is still the default Next.js scaffold. No `/demo/[slug]` route (chat is at `/chat/[slug]`)
**Phase 4 — Chat receptionist:**
- ✅ 4.1 Groq · 4.2 RAG · 4.3 LangGraph · 4.4 persistence · 4.5 intents · 4.7a chat endpoint · 4.7b chat page + widget · 4.8 escalation email (Resend)
- ✅ Booking flow: 4.6.1 service (`7e36ba8`) · 4.6.2a/b dates+slots (`ef5f79d`, `1eb175b`) · 4.6.3 contact (`a8c71f6`) · 4.6.4 Booking row (`bfbfc8b`) · 4.6.6a demo data (`4a58eb4`) · 4.6.6c name validation (`a4d3ce3`) · 4.6.6b cancellation (`488c232`)
- ✅ **4.6.5 edge cases** (2026-11-18, uncommitted): holiday closures + special hours, daily booking cap, slot re-check before booking, second booking in the same chat
- ✅ **4.6.6d side questions mid-booking** (2026-11-18, uncommitted)
- ✅ Groq models moved to `openai/gpt-oss-20b` / `openai/gpt-oss-120b` (Llama shut down 2026-08-16)

**Phases 5–11 — all ⬜, no code yet** (no Stripe, Vapi or webhook files exist; the `webhook_events` and `payments` tables are defined but unused)
5 Stripe + confirmation emails · 6 Vapi voice · 7 Escalation dashboard · 8 RAG judge · 9 Cancel/reschedule existing bookings · 10 Analytics + super admin · 11 Polish + deploy

---

## 5. Day-0 recovery runbook (you run everything)

### A. Check the local repo (from `E:\GitHub\AI_reservation`)
```
git status
git fetch
git status -sb
git log --oneline -3
```
Expect: head `488c232`; only four untracked files (`bytes`, `modified`, `~27000`, `—`, all empty). Remove them:
```
git clean -n
```
If that lists **only** those four, run `git clean -f`. (It won't touch ignored files like `.env`.) If `git status` shows modified tracked files, stop and look at them before going on.

### B. Backend environment (from `backend\`)
```
python --version                 # needs 3.11.x
python -m venv .venv             # skip if .venv already exists
.venv\Scripts\Activate.ps1       # Mac/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pip install tzdata               # missing from pyproject.toml, see gotcha 30
```
Frontend (from `frontend\`): `pnpm install`

### C. Is the database alive? (from `backend\`)
```
python scripts/verify_tables.py
```
- **Prints 17 tables + `alembic_version`** → DB is fine, skip to E.
- **Error like `tenant/user ... not found`** → the free project is paused. In the Supabase dashboard:
  - **"Resume project" button** → click it, wait ~1 min, re-run the script.
  - **Only backup/download options** → paused over 90 days, can't be resumed in the dashboard. Go to D.
- **Any other error** → paste the error here (mask host/password).

### D. New Supabase project (only if C says so)
Everything is demo data and reproducible from migrations + scripts, so create a **new project** rather than restoring a backup.
1. In the new project open **Connect** and copy the **pooler** URLs. Don't assume the region (the old host was `aws-1-ap-southeast-2.pooler.supabase.com`).
   - `DATABASE_URL` → **Transaction pooler**, port **6543**, `postgresql+asyncpg://`
   - `DATABASE_URL_SYNC` → **Session pooler**, port **5432**, `postgresql+psycopg2://`
   - Username `postgres.<PROJECT_REF>`. **Never use the "Direct connection"** (IPv6-only on free tier; fails from Bangladesh)
2. Put them in `backend\.env` yourself. Other names are already there; see `backend/.env.example` (all 31 names).
3. Rebuild (from `backend\`):
```
alembic upgrade head                      # 8c5d604ee81d (extensions+enums) -> 858813776375 (17 tables)
python scripts/verify_tables.py           # expect 17 tables + alembic_version
python scripts/create_super_admin.py
python scripts/seed_demo_data.py          # safe to re-run
python scripts/fix_demo_data.py           # idempotent: sets dhaka-dental currency to BDT, soft-deletes a stale "test" service
python scripts/backfill_embeddings.py     # ~51 embeddings
python scripts/set_escalation_email.py dhaka-dental you@example.com
python scripts/verify_demo_data.py
```
Use an email you own. The default sender `onboarding@resend.dev` is Resend's test sender and normally only delivers to your own Resend account email **(verify)**.

### E. Keys to check
- `PLATFORM_ENCRYPTION_KEY` must be a real Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` (never paste the output into chat)
- `GROQ_API_KEY` valid. Defaults in `config.py`: smart `openai/gpt-oss-120b`, fast `openai/gpt-oss-20b`. (The old Llama defaults were shut down by Groq on 2026-08-16.) Don't set `GROQ_MODEL_*` in `.env` unless you mean to override
- `RESEND_API_KEY` valid (needed for escalation email)
- Frontend `.env.local` needs `NEXT_PUBLIC_API_URL` (file exists, unchecked)

### F. Smoke test
```
# terminal 1, backend\
uvicorn app.main:app --host localhost --port 8000 --reload
# terminal 2, frontend\
pnpm dev
# terminal 3, backend\
pytest
```
1. `http://localhost:8000/health` → `{"status":"ok"}`
2. `pytest` green (136 tests as of 2026-11-18)
3. Log in as `owner@dhakadental.com`; Services, Hours, FAQs, Settings load
4. `/chat/dhaka-dental`: *"I want to book a routine cleaning"* → date → slot → name → email → phone
5. In Supabase: a `bookings` row with `status = pending_payment` and `idempotency_key = chat:<conversation_id>:<draft_id>`

**Recovery is done when 1–5 pass.** Then set §1 to Phase 4.6.5.

---

## 6. Daily routine

**Start (5 min):** `git status` + `git log --oneline -3` → read §1–§3 → start backend + frontend (§5F; if a request 500s, make sure only **one** uvicorn is on port 8000) → paste the Daily kickoff prompt into Claude Code.

**End (5 min):** verify (pytest or script) → commit → update §1, §4, §11 → `git add CONTEXT.md` · `git commit -m "docs: update CONTEXT.md"` · `git push`.

**Supabase free tier pauses after ~7 days idle**, and can only be resumed within 90 days of the pause. If you'll be away for a week, run `python scripts/verify_tables.py` once, or upgrade to a paid plan.

---

## 7. Stack and locked decisions

**Installed backend:** FastAPI · async SQLAlchemy 2 · asyncpg · pgvector · LangGraph · Pydantic v2 · Groq · sentence-transformers (MiniLM) · Alembic · bcrypt · python-jose · Resend. Python **3.11**, always run from `backend\`.
**Installed frontend:** Next.js **16.2.4** · React 19 · Tailwind **v4** (CSS-first, no `tailwind.config.ts`) · shadcn/ui (`base-nova`) · Zustand · react-hook-form + zod · sonner. Package manager **pnpm**.
**Planned but NOT installed yet:** backend LangChain, APScheduler, Stripe, Vapi SDKs; frontend TanStack Query, Tremor, Recharts, assistant-ui, `@vapi-ai/web`, Framer Motion.

**Decisions that override the planning docs**
- bcrypt used directly, **not passlib**
- Postgres enums: `postgresql.ENUM(..., create_type=False)`, **not** `sa.Enum`
- Reserved column `metadata`: on `audit_logs`, `messages`, `embeddings` use `mapped_column("metadata", ...)` with Python attribute `extra_data`
- JWT `sub` = user UUID; httpOnly cookies; `secure` only in prod/staging
- DB engine: **`NullPool`** + `statement_cache_size=0` (Supabase transaction pooler)
- Session factory: `from app.core.database import async_session_factory`
- Booking idempotency key `chat:{conversation_id}:{draft_id}` (one per booking attempt, so one chat can make several bookings; old drafts without `draft_id` use `chat:{conversation_id}`); times stored UTC, converted from business timezone
- Booking draft lives in `conversations.langgraph_state` (JSONB). Stages: service → date → slot → contact → complete
- Day hours: a `schedule_exceptions` row for the date beats the weekly `operating_hours` row (`slot_finder.resolve_hours`); `business_settings.max_daily_bookings` is enforced
- A chosen slot is re-checked (`is_slot_still_available`) right before the Booking is written; if taken, fresh times are offered. Still not race-proof between two simultaneous transactions (needs an exclusion constraint)
- Groq: `openai/gpt-oss-20b` / `openai/gpt-oss-120b` are reasoning models; `chat_completion` sets `reasoning_effort="low"` and a ≥1024-token budget. Always call the LLM through it
- LangGraph lives in `app/services/` (not `app/ai/` as `docs/04` planned). **The tree in §8 is the truth.**

**Hard rules from `CLAUDE.md`:** every business-scoped query filters by `business_id` · no booking without idempotency key · webhooks verify signatures · Stripe/Vapi mocked in tests · no secrets in git.
**Known rule violations:** admin routers run `select()` directly instead of going through services; `ChatWidget.tsx` breaks the kebab-case file rule.

---

## 8. Actual file map (audit at `488c232` + 2026-11-18 additions)

```
AI_reservation/
├── CLAUDE.md  docs/00..08  docs/CLAUDE.md (stale old copy)  .gitignore
├── backend/  pyproject.toml  alembic.ini  README.md  .env.example  .env(ignored)
│   ├── app/  main.py  config.py
│   │   ├── core/          database security permissions encryption     (no exceptions.py)
│   │   ├── models/        base enums user platform_setting audit_log business business_setting
│   │   │                  operating_hours schedule_exception service customer booking payment
│   │   │                  conversation message escalation faq embedding webhook_event
│   │   ├── schemas/       auth business(+service DTOs) hours_faqs chat
│   │   ├── routers/       auth chat  admin/{business,services,hours,faqs}
│   │   ├── services/      auth_service booking_flow(1200 lines) chat_graph(586) slot_finder
│   │   │                  date_parser conversation_store embedding_sync rag
│   │   └── integrations/  embeddings llm resend_email
│   ├── alembic/versions/  20260422_1245_8c5d604ee81d_extensions_and_enums
│   │                      20260425_0156_858813776375_create_all_17_tables   <- head
│   ├── scripts/  create_super_admin seed_demo_data fix_demo_data set_escalation_email
│   │             backfill_embeddings verify_{tables,db_session,demo_data,embeddings,rag,chat}
│   │             check_state check_bookings
│   └── tests/    conftest test_auth test_admin_services test_admin_hours_faqs
│                 test_booking_helpers test_llm_parsers test_booking_flow      (flat, 136 tests)
└── frontend/  package.json pnpm-lock.yaml  .env.local(ignored)  README.md(stock stub)
    └── src/  app/{layout,page(stock),globals.css, (auth)/login, admin/{layout,page,services,hours,faqs,settings}, chat/[slug]}
              components/{ChatWidget, layout/admin-sidebar, ui/*}
              lib/{utils.ts, api/{client,chat,types}.ts, store/auth-store.ts}
```

**Booking-flow landmarks** (find by name; line numbers drift):
`booking_flow.py`: `booking_node` (dispatcher; cancel check before stage dispatch; COMPLETE → fresh draft) · `_handle_awaiting_service/date/slot/contact` · `booking_resume_prompt` (4.6.6d) · `_complete_booking` → `_finalize_booking` (re-check + write) · `_reoffer_after_conflict`
`slot_finder.py`: `resolve_hours` / `get_day_hours` (exceptions) · `compute_slots` (pure) · `find_available_slots` · `is_slot_still_available`
`chat_graph.py`: `looks_like_side_question` + sticky override in `classify_intent_node` · `answer_node` appends the resume prompt · `escalate_stub_node` (real email, name kept)
`integrations/llm.py`: `build_completion_kwargs` (reasoning-model handling) · `chat_completion`

**Not built yet:** `routers/{super,webhooks,voice,public}`, `routers/admin/{bookings,customers,conversations,escalations,analytics}`, `integrations/{stripe_client,vapi_client,supabase_storage}`, `services/{booking,payment,notification}_service`, `jobs/`, `utils/`, root `README.md`, Dockerfile.
**Test coverage:** booking flow, slot finder, date parser, slot matcher, side-question routing and the LLM wrapper are covered (LLM and embedding search faked). Still untested: `rag`, `embedding_sync`, the `/chat/{slug}` router itself.

---

## 9. Gotchas (don't re-hit these)

| # | Gotcha | Fix |
|---|---|---|
| 1 | hatchling can't find the package | `[tool.hatch.build.targets.wheel] packages = ["app"]` |
| 2 | `.env` typo `KEY=KEY=value` silently breaks config | sanity-check loaded settings |
| 3 | Secrets leaking into chat / logs | masked prints only; rotate anything exposed |
| 4 | Supabase direct host is IPv6-only | always use the pooler |
| 5 | `sa.Enum` ignores `create_type=False` in migrations | use `postgresql.ENUM(...)` |
| 6 | Circular FK `bookings` <-> `conversations` | create without FK, add with `op.create_foreign_key` after |
| 7 | Chat UI turns `file.py` into a link when copied | trust `git log --name-only`, not terminal text |
| 8 | `alembic check` exits non-zero when out of sync | intentional |
| 9 | Autogenerate drops DESC on indexes | grep migrations for `_desc`; use `sa.literal_column('created_at DESC')` |
| 10 | passlib 1.7.4 breaks with bcrypt 5.x | use bcrypt directly |
| 11 | asyncpg prepared statements vs pgbouncer | `statement_cache_size=0` (and see 18) |
| 12 | Free Supabase pauses after ~7 days idle ("tenant/user not found") | Resume in dashboard, only within 90 days |
| 13 | `PLATFORM_ENCRYPTION_KEY` must be a real Fernet key | generate one |
| 14 | `python -c` / settings only work from `backend\` | `cd backend` first |
| 15 | pytest-asyncio "Event loop is closed" | fresh `AsyncEngine` per test |
| 16 | `EmailStr` needs email-validator | depend on `pydantic[email]` |
| 17 | Real creds pasted in chat | don't, even local ones |
| 18 | `prepared statement ... does not exist` after a few requests | **`poolclass=NullPool`** |
| 19 | LangGraph state + `TYPE_CHECKING` imports -> `NameError` | state-schema types must be runtime imports |
| 20 | `conversations.session_token` NOT NULL, no default | `secrets.token_urlsafe(32)` |
| 21 | `customers` needs email OR phone | anonymous chat -> `anon-{customer_id}@chat.local`; create Customer before Conversation |
| 22 | PowerShell treats `[slug]` as a wildcard | `Get-Content -LiteralPath '...'` |
| 23 | Claude Code `str_replace` can "succeed" with no change | verify; for big edits recreate the file |
| 24 | In-place mutation of a JSONB dict isn't detected by SQLAlchemy | `_save_booking_draft` stores `dict(draft)` (confirmed at line 164) |
| 25 | Same bug on resumed conversations | `_get_booking_draft` returns `dict(draft)` (confirmed at line 124) |
| 26 | Stale uvicorn on port 8000, or code not reloaded | stop all, start one; restart after `pip install` |
| 27 | Windows needs `tzdata` for `zoneinfo` | in `pyproject.toml` since 2026-11-18 |
| 28 | Commands run from repo root instead of `backend\` | check the prompt path first |
| 29 | PowerShell breaks on multi-line `git commit -m` | single-line message |
| 30 | `tzdata` was missing from `pyproject.toml` (commit `ef5f79d` claimed it) | fixed 2026-11-18 |
| 31 | Stray empty files `bytes`, `modified`, `~26000`, `—` keep reappearing in repo root (again on Oct 27): pasted text containing `>` is treated as a redirect | don't paste prose into the terminal; delete them by name (`Remove-Item -LiteralPath ...`), not with `git clean -f`, which would also delete `CONTEXT.md` while it's untracked |
| 32 | Groq shut down `llama-3.1-8b-instant` / `llama-3.3-70b-versatile` on 2026-08-16 | defaults are now `openai/gpt-oss-20b` / `-120b`; check console.groq.com/docs/deprecations when chat errors mention a model |
| 33 | gpt-oss / Qwen3 are reasoning models: thinking tokens count against `max_tokens`, so `max_tokens=10` returns an empty answer | `chat_completion` raises the budget and sets low reasoning effort; never call the Groq SDK directly |
| 34 | `DemoBusiness` is a dataclass: a field with a default can't come before fields without one | add new defaulted fields at the end |

> 1–23 match `docs/08-session-log.md`. 24–34 were added later.

---

## 10. Backlog (in order)

1. **Finish 2026-11-18:** install, test, live chat check, commit (§11 "To finish")
2. **Phase 5:** Stripe Checkout → `pending_payment` → webhook (signature verify, `webhook_events` idempotency) → `confirmed` → customer + admin emails via Resend; payment card in widget; success/cancel pages
3. **Docs:** `docs/CLAUDE.md` is a stale copy (decide: delete) · `docs/04-folder-structure.md` doesn't match the real tree · no root `README.md` · `docs/08-session-log.md` stops at 4.7 (this file replaces it)
4. **Small debt:** test data piles up in Supabase (46 businesses from test runs) — add cleanup or a separate test database · a Postgres exclusion constraint on `bookings` would make double-booking impossible · 112 pre-existing ruff lint findings across `app/` (none new)
5. **Decide:** build 2.3 logo upload and the public landing page now, or defer
6. Phases 6–11 per `docs/05-build-phases.md`

**Not assessed by the audit:** drift between the code and `docs/01-schema`, `03-api`, `05-build-phases`; contents of `frontend/public/`; whether tracked files have uncommitted edits.

---

## 11. Session log (newest first)

### TEMPLATE
```
### YYYY-MM-DD — <one-line title>
- Done: <what changed, with commit messages>
- Verified by: <pytest / script / manual>
- Decisions: <anything that overrides docs>
- New gotchas: <or "none">
- Next: <first task tomorrow>
```

### 2026-11-18 — Phase 4.6.5 + 4.6.6d, Groq model switch (done by Claude, not yet committed)
- Done:
  - **Groq:** default models → `openai/gpt-oss-20b` (fast) / `openai/gpt-oss-120b` (smart); `llm.py` handles reasoning models (`config.py`, `.env.example`, `docs/06-env-vars.md`)
  - **4.6.5 edge cases:** holiday closures and special hours from `schedule_exceptions` now block/limit slots, with the reason in the reply · `max_daily_bookings` enforced · chosen slot re-checked before the Booking is written; if taken, new times are offered and contact details kept · a second booking in the same chat now works (was: "team will reach out", no booking) · idempotency key per draft · `conversations.booking_id` now set · a failed finalize rolls back so the reply still saves
  - **4.6.6d:** a clear side question mid-booking ("where are you located?") is answered, then the bot repeats the pending booking step; the draft is untouched. Short answers ("Saturday", "10:30") still go to the booking
  - **Housekeeping:** `tzdata` dependency · seed sets `currency="BDT"` · stale comments fixed · pytest `asyncio_default_fixture_loop_scope` set · `CLAUDE.md` points here
  - **Tests:** +122 (`test_booking_helpers.py`, `test_llm_parsers.py`, `test_booking_flow.py`)
- Verified by: 136/136 pytest on a local Postgres 16 + pgvector copy of the schema; seed run on an empty DB gives BDT for all 3 businesses. **Not yet verified:** a real chat against Groq's new models
- Decisions: idempotency key format `chat:{conversation_id}:{draft_id}`
- New gotchas: 32, 33, 34
- To finish (you run, from `backend\` with `.venv` active):
  1. `pip install -e ".[dev]"` (adds tzdata)
  2. `pytest` — expect 136 passed (slow against Supabase; the 8 flow tests create throwaway businesses)
  3. Restart uvicorn, open `/chat/dhaka-dental`, book a cleaning end to end; mid-way ask "Where are you located?"
  4. From the repo root: `git add -A backend docs CLAUDE.md CONTEXT.md` then `git commit -m "feat(phase-4.6.5-4.6.6d): booking edge cases, side questions, gpt-oss models, tests"` then `git push`
- Next: Phase 5

### 2026-10-22 — Resumed after 4.5 months; ground-truth audit
- Done: located repo (`E:\GitHub\AI_reservation`), ran read-only audit with Claude Code, rebuilt this file from it. No code changed
- Verified by: audit report only (static reading; nothing run, tests not executed)
- Decisions: `tzdata` and BDT-seed fixes go into the housekeeping commit
- New gotchas: 30, 31
- Next: §5A–F recovery, then housekeeping, then 4.6.5

### 2026-06-06 — Booking flow 4.6.2 -> 4.6.6b shipped
- Done: slot finding/selection, contact collection, real `Booking` row (UTC conversion, idempotency), demo data fix (USD->BDT), tighter name extraction, cancellation detection
- Verified by: browser booking test; a `pending_payment` booking at `starts_at` 2026-06-08T03:00Z (09:00 Dhaka)
- Decisions: cancellation checked at the dispatcher level, before stage dispatch
- New gotchas: 24, 25
- Next: 4.6.6d, 4.6.5, Phase 5

### Earlier
`git log --oneline` (48 commits): Phase 0 -> 4.8 in order.
