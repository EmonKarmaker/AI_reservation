## What this document is (plain English)

This is the **map of every file and folder** in the project. Before writing any code, we decide where each piece lives.

**Why it matters:** A messy folder structure kills solo projects faster than any bug. When you come back in 3 weeks and can't find where authentication lives, momentum dies. A clean structure means: every new feature has an obvious home, every file has one job, and Claude Code knows exactly where to put new code.

**How to read it:**
- Folder tree shows the hierarchy
- Files marked `*` are created by Claude Code in Phase 1 (first things built)
- Files marked `†` are created in later phases
- Each folder has a one-line "what lives here" comment

**The project is a monorepo:**
```
E:\GitHub\AI_reservation\
├── backend/     ← FastAPI (Python)
├── frontend/    ← Next.js (TypeScript)
├── docs/        ← all planning documents (you just made this)
└── CLAUDE.md    ← briefing for Claude Code
```

**When Claude Code uses this document:** it creates files in exactly these locations. No guessing, no drift.

---

# Folder Structure

## Project root

```
AI_reservation/
├── backend/              # FastAPI application
├── frontend/             # Next.js application
├── docs/                 # planning docs (this folder)
├── .gitignore *
├── README.md *
├── CLAUDE.md *           # Claude Code briefing
└── docker-compose.yml †  # optional local dev (postgres + redis)
```

---

## Backend tree

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py *                    # FastAPI app factory, middleware, CORS, startup events
│   ├── config.py *                  # Settings class (pydantic-settings), loads .env
│   │
│   ├── core/                        # Cross-cutting infrastructure
│   │   ├── __init__.py
│   │   ├── database.py *            # async engine, session factory, get_db dependency
│   │   ├── security.py *            # JWT encode/decode, password hash, get_current_user
│   │   ├── permissions.py *         # require_super_admin, require_business_admin dependencies
│   │   ├── exceptions.py *          # custom exceptions + FastAPI exception handlers
│   │   ├── encryption.py *          # Fernet wrapper for platform_settings values
│   │   ├── pagination.py *          # reusable Page[T] model + query helpers
│   │   ├── audit.py *               # audit_log writer
│   │   └── rate_limit.py †          # slowapi config
│   │
│   ├── models/                      # SQLAlchemy ORM models (mirror schema doc 1:1)
│   │   ├── __init__.py *            # exports all models + Base
│   │   ├── base.py *                # Base, TimestampMixin, SoftDeleteMixin, UUIDMixin
│   │   ├── enums.py *               # all PG enums as Python Enum
│   │   ├── user.py *
│   │   ├── platform.py *            # platform_settings, audit_logs
│   │   ├── business.py *            # businesses, business_settings
│   │   ├── schedule.py *            # operating_hours, schedule_exceptions
│   │   ├── service.py *
│   │   ├── customer.py *
│   │   ├── booking.py *
│   │   ├── payment.py *
│   │   ├── conversation.py *        # conversations, messages
│   │   ├── escalation.py *
│   │   ├── faq.py *
│   │   ├── embedding.py *
│   │   └── webhook.py *             # webhook_events
│   │
│   ├── schemas/                     # Pydantic request/response DTOs
│   │   ├── __init__.py *
│   │   ├── common.py *              # PageParams, ErrorResponse, etc.
│   │   ├── auth.py *                # LoginRequest, RegisterRequest, UserOut
│   │   ├── business.py *
│   │   ├── service.py *
│   │   ├── schedule.py *
│   │   ├── customer.py *
│   │   ├── booking.py *
│   │   ├── payment.py *
│   │   ├── conversation.py *
│   │   ├── escalation.py *
│   │   ├── faq.py *
│   │   ├── chat.py *                # ChatStartRequest, ChatMessageRequest, ChatResponse
│   │   ├── voice.py *               # Vapi webhook shapes
│   │   ├── analytics.py †
│   │   └── super_admin.py *
│   │
│   ├── routers/                     # FastAPI routers (one per API section from doc 03)
│   │   ├── __init__.py *
│   │   ├── auth.py *                # /auth/*
│   │   ├── chat.py *                # /chat/*
│   │   ├── voice.py *               # /voice/*
│   │   ├── admin/                   # business_admin scope
│   │   │   ├── __init__.py *
│   │   │   ├── business.py *        # /admin/business
│   │   │   ├── services.py *
│   │   │   ├── hours.py *
│   │   │   ├── faqs.py *
│   │   │   ├── bookings.py *
│   │   │   ├── customers.py *
│   │   │   ├── conversations.py *
│   │   │   ├── escalations.py *
│   │   │   └── analytics.py †
│   │   ├── super/                   # super_admin scope
│   │   │   ├── __init__.py *
│   │   │   ├── businesses.py *
│   │   │   ├── analytics.py †
│   │   │   ├── settings.py *
│   │   │   └── audit_logs.py *
│   │   ├── webhooks/
│   │   │   ├── __init__.py *
│   │   │   ├── stripe.py *
│   │   │   └── vapi.py *            # same as voice, or merged
│   │   └── public.py *              # /businesses, /businesses/{slug}/public, /health
│   │
│   ├── services/                    # Business logic layer (no HTTP, no ORM leaks out)
│   │   ├── __init__.py *
│   │   ├── auth_service.py *
│   │   ├── business_service.py *
│   │   ├── service_service.py *     # yes the double name is fine
│   │   ├── schedule_service.py *
│   │   ├── booking_service.py *     # create, validate availability, cancel, refund
│   │   ├── payment_service.py *     # Stripe Checkout session creation
│   │   ├── customer_service.py *
│   │   ├── conversation_service.py *
│   │   ├── escalation_service.py *
│   │   ├── faq_service.py *
│   │   ├── embedding_service.py *   # sync on CRUD, search
│   │   ├── analytics_service.py †
│   │   └── notification_service.py * # Resend email wrapper
│   │
│   ├── ai/                          # LangGraph brain
│   │   ├── __init__.py *
│   │   ├── graph.py *               # builds and compiles the graph
│   │   ├── state.py *               # AgentState, BookingSlots, RagChunk, Action
│   │   ├── intents.py *             # IntentType enum
│   │   ├── llm.py *                 # Groq client wrapper
│   │   ├── embeddings.py *          # MiniLM loader + embed()
│   │   ├── nodes/
│   │   │   ├── __init__.py *
│   │   │   ├── entry.py *
│   │   │   ├── routing.py *
│   │   │   ├── booking.py *
│   │   │   ├── rag.py *
│   │   │   ├── cancel.py *
│   │   │   ├── escalation.py *
│   │   │   └── finalize.py *
│   │   └── prompts/
│   │       ├── __init__.py *
│   │       ├── system.py *
│   │       ├── intent.py *
│   │       ├── extract.py *
│   │       └── judge.py *
│   │
│   ├── integrations/                # Third-party wrappers, isolated
│   │   ├── __init__.py *
│   │   ├── stripe_client.py *
│   │   ├── vapi_client.py *
│   │   ├── resend_client.py *
│   │   └── supabase_storage.py *    # image upload helpers
│   │
│   ├── jobs/                        # Background tasks (APScheduler)
│   │   ├── __init__.py *
│   │   ├── scheduler.py *           # APScheduler setup, registers jobs
│   │   ├── reminder_job.py †        # send booking reminders N hours before
│   │   ├── no_show_sweeper.py †     # mark past unconfirmed as no_show
│   │   └── embedding_sync.py *      # catch-up re-embed orphans
│   │
│   └── utils/
│       ├── __init__.py *
│       ├── datetime_utils.py *      # tz conversion, parsing "Tuesday" to date
│       ├── phone_utils.py *         # E.164 validation
│       ├── slug.py *
│       └── idempotency.py *         # hash builder for booking keys
│
├── alembic/                         # DB migrations
│   ├── env.py *
│   ├── script.py.mako
│   └── versions/
│       └── (auto-generated *.py files)
├── alembic.ini *
│
├── scripts/                         # one-off tools
│   ├── seed_demo_data.py *          # creates demo businesses, services, super admin
│   ├── create_super_admin.py *      # one-off to bootstrap first super admin
│   └── reembed_all.py †             # rebuild all embeddings (rarely needed)
│
├── tests/
│   ├── __init__.py *
│   ├── conftest.py *                # pytest fixtures: test db, client, auth
│   ├── unit/
│   │   ├── test_security.py *
│   │   ├── test_datetime_utils.py *
│   │   ├── test_phone_utils.py *
│   │   ├── test_booking_service.py *
│   │   └── test_ai_nodes.py *
│   └── integration/
│       ├── test_auth_flow.py *
│       ├── test_booking_flow.py *
│       ├── test_chat_flow.py *
│       └── test_stripe_webhook.py *
│
├── .env.example *                   # all env vars with dummy values
├── .env                             # gitignored, real values
├── .gitignore
├── Dockerfile *                     # for Render deploy
├── pyproject.toml *                 # uv / poetry config
├── requirements.txt *               # if not using pyproject, pip-compiled
└── README.md *
```

### Backend layering rules (non-negotiable)

- **routers/** only: HTTP concerns (parse request, call service, return response). No SQL, no business logic.
- **services/** only: business logic. Takes Pydantic schemas or primitives, returns Pydantic schemas or primitives. Uses models/ and integrations/.
- **models/** only: SQLAlchemy ORM. No HTTP, no business logic.
- **schemas/** only: Pydantic DTOs. No logic beyond validators.
- **ai/** is its own world — services/ calls into `ai.graph.run_turn()` and that's the only seam.
- **integrations/** wraps every third party. No direct `stripe.Checkout.create()` in services — always `stripe_client.create_checkout(...)`.

This matters because Claude Code will respect it and future you will thank you.

---

## Frontend tree

```
frontend/
├── src/
│   ├── app/                         # Next.js 14 App Router
│   │   ├── layout.tsx *             # root layout: providers, fonts, metadata
│   │   ├── page.tsx *               # landing page (public demo)
│   │   ├── globals.css *            # Tailwind directives
│   │   ├── favicon.ico
│   │   │
│   │   ├── (public)/                # route group: no auth required
│   │   │   ├── layout.tsx *         # public layout (navbar, footer)
│   │   │   ├── demo/
│   │   │   │   └── [slug]/
│   │   │   │       └── page.tsx *   # per-business demo page (chat + voice widgets)
│   │   │   ├── login/
│   │   │   │   └── page.tsx *
│   │   │   └── register/
│   │   │       └── page.tsx *
│   │   │
│   │   ├── admin/                   # business_admin routes (JWT required)
│   │   │   ├── layout.tsx *         # sidebar, header, auth guard
│   │   │   ├── page.tsx *           # dashboard overview
│   │   │   ├── bookings/
│   │   │   │   ├── page.tsx *
│   │   │   │   └── [id]/page.tsx *
│   │   │   ├── services/
│   │   │   │   ├── page.tsx *
│   │   │   │   └── [id]/page.tsx *
│   │   │   ├── hours/page.tsx *
│   │   │   ├── faqs/page.tsx *
│   │   │   ├── customers/
│   │   │   │   ├── page.tsx *
│   │   │   │   └── [id]/page.tsx *
│   │   │   ├── conversations/
│   │   │   │   ├── page.tsx *
│   │   │   │   └── [id]/page.tsx *
│   │   │   ├── escalations/
│   │   │   │   ├── page.tsx *
│   │   │   │   └── [id]/page.tsx *
│   │   │   ├── analytics/page.tsx †
│   │   │   └── settings/page.tsx *  # business profile, logo, AI personality
│   │   │
│   │   ├── super/                   # super_admin routes (JWT required, role-checked)
│   │   │   ├── layout.tsx *
│   │   │   ├── page.tsx *           # platform overview
│   │   │   ├── businesses/
│   │   │   │   ├── page.tsx *
│   │   │   │   └── [id]/page.tsx *
│   │   │   ├── analytics/page.tsx †
│   │   │   ├── settings/page.tsx *  # platform settings (API keys)
│   │   │   └── audit-logs/page.tsx *
│   │   │
│   │   └── api/                     # Next.js API routes (BFF layer, thin)
│   │       ├── auth/
│   │       │   ├── login/route.ts * # proxies to FastAPI, sets httpOnly cookie
│   │       │   ├── logout/route.ts *
│   │       │   └── refresh/route.ts *
│   │       └── (rest of calls go directly from client to FastAPI)
│   │
│   ├── components/
│   │   ├── ui/                      # shadcn/ui components (auto-generated)
│   │   │   ├── button.tsx *
│   │   │   ├── input.tsx *
│   │   │   ├── card.tsx *
│   │   │   ├── dialog.tsx *
│   │   │   ├── form.tsx *
│   │   │   ├── select.tsx *
│   │   │   ├── table.tsx *
│   │   │   ├── toast.tsx *
│   │   │   ├── sidebar.tsx *
│   │   │   └── ... (add as needed)
│   │   │
│   │   ├── layout/
│   │   │   ├── admin-sidebar.tsx *
│   │   │   ├── super-sidebar.tsx *
│   │   │   ├── top-nav.tsx *
│   │   │   └── auth-guard.tsx *
│   │   │
│   │   ├── chat/
│   │   │   ├── chat-widget.tsx *    # the floating chat button + panel
│   │   │   ├── message-list.tsx *
│   │   │   ├── message-input.tsx *
│   │   │   ├── readback-card.tsx *  # rich confirmation UI
│   │   │   ├── confirmation-card.tsx *
│   │   │   └── payment-card.tsx *
│   │   │
│   │   ├── voice/
│   │   │   ├── voice-widget.tsx *   # wraps @vapi-ai/web
│   │   │   ├── mic-button.tsx *
│   │   │   └── voice-transcript.tsx *
│   │   │
│   │   ├── bookings/
│   │   │   ├── booking-list.tsx *
│   │   │   ├── booking-detail.tsx *
│   │   │   ├── booking-form.tsx *   # manual booking
│   │   │   └── booking-status-badge.tsx *
│   │   │
│   │   ├── services/
│   │   │   ├── service-list.tsx *
│   │   │   ├── service-form.tsx *
│   │   │   └── service-image-upload.tsx *
│   │   │
│   │   ├── hours/
│   │   │   └── hours-editor.tsx *
│   │   │
│   │   ├── escalations/
│   │   │   ├── escalation-list.tsx *
│   │   │   └── escalation-detail.tsx *
│   │   │
│   │   ├── analytics/
│   │   │   ├── stat-card.tsx *
│   │   │   ├── bookings-chart.tsx †
│   │   │   ├── conversion-chart.tsx †
│   │   │   └── top-services-table.tsx †
│   │   │
│   │   └── common/
│   │       ├── page-header.tsx *
│   │       ├── empty-state.tsx *
│   │       ├── loading-spinner.tsx *
│   │       ├── error-boundary.tsx *
│   │       └── confirm-dialog.tsx *
│   │
│   ├── lib/
│   │   ├── api/                     # typed API client
│   │   │   ├── client.ts *          # fetch wrapper, handles cookies, errors
│   │   │   ├── auth.ts *            # login, logout, me, register
│   │   │   ├── business.ts *
│   │   │   ├── services.ts *
│   │   │   ├── hours.ts *
│   │   │   ├── bookings.ts *
│   │   │   ├── customers.ts *
│   │   │   ├── faqs.ts *
│   │   │   ├── conversations.ts *
│   │   │   ├── escalations.ts *
│   │   │   ├── chat.ts *            # public chat API
│   │   │   ├── voice.ts *           # Vapi config fetch
│   │   │   ├── analytics.ts †
│   │   │   └── super.ts *
│   │   │
│   │   ├── hooks/                   # TanStack Query hooks
│   │   │   ├── use-auth.ts *
│   │   │   ├── use-businesses.ts *
│   │   │   ├── use-services.ts *
│   │   │   ├── use-bookings.ts *
│   │   │   ├── use-hours.ts *
│   │   │   ├── use-customers.ts *
│   │   │   ├── use-faqs.ts *
│   │   │   ├── use-conversations.ts *
│   │   │   ├── use-escalations.ts *
│   │   │   └── use-chat.ts *
│   │   │
│   │   ├── stores/                  # Zustand
│   │   │   ├── auth-store.ts *      # current user, business_id
│   │   │   └── ui-store.ts *        # sidebar collapsed, theme, etc.
│   │   │
│   │   ├── schemas/                 # Zod schemas mirroring backend DTOs
│   │   │   ├── auth.ts *
│   │   │   ├── business.ts *
│   │   │   ├── service.ts *
│   │   │   ├── booking.ts *
│   │   │   ├── hours.ts *
│   │   │   └── ... *
│   │   │
│   │   ├── utils/
│   │   │   ├── cn.ts *              # clsx + tailwind-merge
│   │   │   ├── format.ts *          # currency, date, phone formatters
│   │   │   ├── dates.ts *           # relative time, tz conversion
│   │   │   └── validators.ts *
│   │   │
│   │   └── constants.ts *           # app-wide constants
│   │
│   ├── providers/
│   │   ├── query-provider.tsx *     # TanStack Query
│   │   ├── theme-provider.tsx *
│   │   └── toast-provider.tsx *
│   │
│   ├── types/
│   │   ├── api.ts *                 # shared API response types
│   │   ├── models.ts *              # domain types (Business, Service, etc.)
│   │   └── env.d.ts *
│   │
│   └── styles/
│       └── tremor.css *             # Tremor overrides if needed
│
├── public/
│   ├── logo.svg
│   ├── og-image.png
│   └── robots.txt
│
├── .env.example *                   # NEXT_PUBLIC_API_URL, VAPI_PUBLIC_KEY, etc.
├── .env.local                       # gitignored
├── .eslintrc.json *                 # or biome.json
├── .gitignore
├── components.json *                # shadcn/ui config
├── next.config.mjs *
├── package.json *
├── pnpm-lock.yaml
├── postcss.config.mjs *
├── tailwind.config.ts *
├── tsconfig.json *
└── README.md *
```

### Frontend conventions (non-negotiable)

- **Server components by default.** Add `"use client"` only when you need state, effects, or browser APIs. Chat, voice, forms, dashboards with interactivity → client. Static pages (landing sections, public business info) → server.
- **One component per file.** Named same as the file (`BookingList` in `booking-list.tsx`).
- **File naming:** kebab-case for files, PascalCase for components.
- **API calls go through `lib/api/*`.** Never `fetch()` directly in components.
- **Data fetching via TanStack Query hooks.** Never raw `useEffect` + `fetch`.
- **Forms via React Hook Form + Zod.** Schema lives in `lib/schemas/`, imported by both the form and the API call.
- **Auth state in Zustand.** Synced on login/logout, hydrated from `/auth/me` on mount.
- **Zero business logic in components.** Components render. Logic lives in hooks and utils.

---

## .gitignore (root, applies to both)

```
# Dependencies
node_modules/
.venv/
venv/
__pycache__/
*.pyc

# Env
.env
.env.local
.env.*.local

# Build
.next/
dist/
build/
*.egg-info/

# Editor
.vscode/
.idea/
*.swp

# Claude Code
.claude/

# OS
.DS_Store
Thumbs.db

# Logs
*.log
npm-debug.log*

# Testing
.coverage
.pytest_cache/
htmlcov/
coverage/
```

---

## Size estimate

- Backend: ~120 Python files when fully built
- Frontend: ~180 TypeScript/TSX files when fully built
- Total LOC estimate: 15,000–20,000 lines

This is a real, ship-able SaaS, not a toy. The folder structure handles that scale cleanly.