# AI Reservation SaaS — Project Overview
## What this document is (plain English)

This is the **one-page summary** of the whole project. If someone asks "what are you building?" — this document answers it.

**Why it matters:** Every other document assumes you've read this. It locks in the scope (what's in, what's out), the tech stack (what tools we use), and the success criteria (how we know it's done). Without this anchor, scope creeps and the project never ships.

**When Claude Code uses this document:** it reads the non-negotiables section before every task and refuses to deviate (e.g., it won't swap PostgreSQL for MongoDB, won't add features outside scope).

---
## What we're building
A multi-tenant AI receptionist SaaS. Businesses (dental, HVAC, law, etc.) sign up, configure their services, and get a 24/7 AI receptionist that handles bookings via text chat and voice. Shared brain, multiple channels, real payments, full admin panels.

## Who uses it
- **Super Admin** (platform owner, single account): sees everything across all businesses
- **Business Admin** (one per business): sees only their own business data
- **End Customer** (no login): interacts with the AI receptionist via chat widget or voice widget

## Core features
- Multi-tenant with row-level isolation via `business_id`
- Business admin panel: manage services, hours, pricing, FAQs, view bookings, manage escalations
- Super admin panel: manage all businesses, platform settings, global analytics
- AI chatbot (LangGraph) for text bookings
- AI voice agent (Vapi web widget) for voice bookings
- 7-layer verification pipeline (Pydantic + reality checks + confidence gating + readback + LLM-as-judge + confirmation + idempotency)
- Stripe payments (test mode) with webhook auto-confirmation
- pgvector semantic search for service matching and FAQ RAG
- Image uploads via Supabase Storage
- Escalation flow with email notification + priority scoring + admin dashboard
- Email confirmations via Resend

## Tech stack (locked)
**Backend**
- FastAPI (async)
- PostgreSQL 16 + pgvector
- SQLAlchemy 2.x (async) + asyncpg
- Alembic migrations
- LangGraph + LangChain
- Pydantic v2 for validation
- Groq (LLM, free tier)
- sentence-transformers `all-MiniLM-L6-v2` (local embeddings, 384 dim)
- APScheduler (reminders, background jobs)
- Resend (email)
- Stripe (test mode)
- Vapi (voice)
- JWT auth (httpOnly cookies)

**Frontend**
- Next.js 14 (App Router) + TypeScript
- Tailwind CSS + shadcn/ui
- Zustand (client state)
- TanStack Query (server state)
- React Hook Form + Zod (forms)
- Tremor + Recharts (dashboards)
- assistant-ui (chat widget)
- `@vapi-ai/web` (voice widget)
- Lucide React (icons)
- Framer Motion (animations)

**Infrastructure**
- Supabase (Postgres + pgvector + Storage, free tier)
- Render or Fly.io (FastAPI, free tier)
- Vercel (Next.js, free tier)
- UptimeRobot (keep free services warm)

## Non-negotiables
- Every business-scoped table has `business_id` column
- Every API query from a business admin is auto-filtered by `business_id` middleware
- No secrets in code — all via environment variables
- All LLM outputs validated by Pydantic schemas
- All DB writes in transactions with proper rollback
- Timestamps: `created_at`, `updated_at` on every table, UTC
- Soft deletes via `deleted_at` where appropriate, hard deletes for junk data
- UUIDs for all primary keys (not sequential ints)

## Out of scope for v1
- SMS confirmations (email only)
- Real inbound phone number (Vapi web widget only)
- Multiple staff per business (one admin per business)
- Live human handoff (escalation creates a record + email, doesn't connect live)
- Payment providers other than Stripe
- LLM providers other than Groq (but architecture supports swap via admin panel later)

## Success criteria
A recruiter or interviewer can:
1. Open a public URL
2. Pick a demo business
3. Book an appointment via text chat end-to-end including test payment
4. Book an appointment via voice (browser mic) end-to-end
5. Log into the business admin dashboard with demo credentials and see their booking
6. Log into the super admin dashboard and see platform-wide stats

All on free infrastructure.