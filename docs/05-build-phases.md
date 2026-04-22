## What this document is (plain English)

This is the **order in which to build the app**. A SaaS has ~300 things to build. If you try to build them all at once, you'll quit. If you build them in the wrong order, you'll hit walls (e.g., building the frontend before the API exists).

**Why it matters:** Each phase ends with something **working end-to-end** — even if tiny. Every phase you finish is a win you can see running. No phase takes more than ~1 week of focused work. Solo + Claude Code, this is achievable.

**How to read it:**
- Phases are **sequential**. Don't start Phase 3 until Phase 2 works.
- Each phase lists: **goal**, **what gets built**, **what's working at the end**, **time estimate**.
- Time estimates assume Claude Code Pro + focused daily work (~4–6h/day).
- Testing is inline in each phase, not a separate phase at the end.

**The "working slice" principle:** Phase 1 is a booking flow that works end-to-end for ONE hardcoded business, ugly UI, one service. Phases 2+ add breadth (more businesses, more features, better UI). Never build depth in one area while other areas are empty.

**When Claude Code uses this document:** you tell it "implement Phase 1" and it knows exactly what's in scope and what's not. No scope creep.

---

# Build Phases

## Phase 0 — Setup (1 day)

**Goal:** Empty project skeleton, both repos installable, CI-able.

Tasks:
1. Initialize `backend/` with `pyproject.toml`, FastAPI, uvicorn, SQLAlchemy, asyncpg, alembic, pydantic-settings. Create `app/main.py` with `/health` endpoint returning 200.
2. Initialize `frontend/` with `pnpm create next-app` (TS, App Router, Tailwind, src dir, import alias `@/*`).
3. Install `shadcn/ui` CLI, init, add: button, input, card, form, dialog, toast, table.
4. Create `backend/.env.example` and `frontend/.env.example`.
5. Create Supabase project, copy DB URL and anon key into `.env`.
6. Install `pgvector`, `pgcrypto`, `citext` extensions in Supabase via SQL editor.
7. Run `alembic init alembic`, configure `env.py` to read from settings.
8. First migration: just extensions + enums. Run it, verify in Supabase.
9. Backend: `uvicorn app.main:app --reload` → hit `/health` → 200.
10. Frontend: `pnpm dev` → default Next.js page loads.
11. Root `README.md` with run instructions.

**Done when:** both apps run locally, extensions exist in Supabase, first migration applied.

---

## Phase 1 — Data layer + auth (3–4 days)

**Goal:** All tables exist, you can register/login as super admin and business admin, JWT middleware works.

Tasks:
1. Create all SQLAlchemy models per `docs/01-schema.md`.
2. Generate Alembic migration `alembic revision --autogenerate -m "initial schema"`, review, run.
3. Verify all 17 tables in Supabase.
4. Implement `app/core/security.py`: password hashing (passlib/bcrypt), JWT encode/decode, `get_current_user` dependency.
5. Implement `app/core/permissions.py`: `require_super_admin`, `require_business_admin` dependencies.
6. Implement `app/routers/auth.py`: `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/refresh`. httpOnly cookies for tokens.
7. Write `scripts/create_super_admin.py` — one-off CLI to bootstrap first super admin.
8. Run the script, create your super admin.
9. Write `scripts/seed_demo_data.py` — creates 3 demo businesses (Dental, HVAC, Law) with:
   - 1 business admin user each
   - 5 services each
   - 7 days of operating hours each
   - 10 FAQs each
10. Run seed script, verify in Supabase.
11. Write 4 integration tests: register flow, login flow, protected route without auth (401), protected route with wrong role (403).

**Done when:**
- You can `curl POST /auth/login` with demo credentials and get a JWT cookie back
- You can `curl GET /auth/me` with that cookie and see your user + role
- Calling a business admin route as a non-admin returns 403

**Frontend in this phase:** none. Pure backend.

---

## Phase 2 — Business admin dashboard shell + core CRUD (4–5 days)

**Goal:** Business admin logs in, sees a dashboard, can CRUD their services and hours.

Backend tasks:
1. Implement `routers/admin/business.py`: GET/PATCH business, PATCH settings, POST logo upload.
2. Implement `routers/admin/services.py`: full CRUD. Skip embedding sync for now (stub).
3. Implement `routers/admin/hours.py`: GET/PUT operating hours, exceptions CRUD.
4. Implement `routers/admin/faqs.py`: CRUD. Skip embedding sync for now.
5. Implement `integrations/supabase_storage.py`: image upload helper.
6. Write integration tests for services CRUD (create, list, update, delete, scope enforcement).

Frontend tasks:
1. Build `app/(public)/login/page.tsx` + Zustand auth store.
2. Build `lib/api/client.ts` — fetch wrapper with cookies, error normalization.
3. Build `components/layout/admin-sidebar.tsx` + `admin/layout.tsx` with auth guard (redirects to login if no user).
4. Build `app/admin/page.tsx` — empty dashboard with stat card placeholders (stats stubbed).
5. Build `app/admin/services/page.tsx` + `[id]/page.tsx` — list, create, edit, delete services.
6. Build `app/admin/hours/page.tsx` — 7-day editor.
7. Build `app/admin/faqs/page.tsx` — list, create, edit, delete FAQs.
8. Build `app/admin/settings/page.tsx` — edit business info, upload logo.

**Done when:**
- Log in as `owner@dhakadental.com` → see sidebar → click Services → see 5 seeded services → edit one → see change persist
- Edit hours → see change in Supabase
- Upload logo → see it on dashboard

---

## Phase 3 — Embeddings + pgvector + public business page (2 days)

**Goal:** pgvector works. Services and FAQs auto-embed on create/update. Public demo page exists.

Backend tasks:
1. Implement `app/ai/embeddings.py`: load MiniLM, `embed(text) -> list[float]`.
2. Implement `services/embedding_service.py`: sync on service/FAQ/business CRUD, upsert to `embeddings` table.
3. Wire up in services/faqs/business update paths (remove earlier stubs).
4. Implement `services/embedding_service.search(business_id, query, top_k)`.
5. Implement `routers/public.py`: `/businesses` list, `/businesses/{slug}/public` detail, `/health`.
6. Write `scripts/reembed_all.py` for catch-up.
7. Run reembed on seeded data.

Frontend tasks:
1. Build `app/page.tsx` — landing with business selector (fetches `/businesses`).
2. Build `app/(public)/demo/[slug]/page.tsx` — shows business name, services, hours. Empty placeholders for chat + voice widgets (next phase).

**Done when:**
- Public landing shows 3 demo businesses
- Clicking one shows its services, hours, info
- SQL `SELECT count(*) FROM embeddings` shows rows for each service and FAQ
- Embedding search query returns relevant results (manually test via Python REPL)

---

## Phase 4 — Chat receptionist: minimal LangGraph (5–7 days) 🎯 biggest phase

**Goal:** The chat widget works end-to-end. User can book an appointment via text chat for a demo business. Payment step stubbed.

Backend tasks:
1. Implement `app/ai/state.py` — AgentState, BookingSlots, etc.
2. Implement `app/ai/intents.py` — IntentType enum.
3. Implement `app/ai/llm.py` — Groq client, structured output wrapper, retries.
4. Implement `app/ai/prompts/*` — system, intent, extract, judge.
5. Implement `app/ai/nodes/` — start with just: `entry`, `classify_intent`, `route_intent`, `extract_slots`, `validate_service`, `validate_phone`, `resolve_date_time`, `check_availability`, `identify_missing_slots`, `ask_for_missing`, `readback_critical_slots`, `explicit_confirmation`, `create_booking_action`, `finalize`.
6. Skip for this phase: `llm_judge`, `rag`, `escalation`, `cancel`, `reschedule`. Add later.
7. Implement `app/ai/graph.py` — wire nodes.
8. Implement `services/conversation_service.py`: create, load, save langgraph_state.
9. Implement `routers/chat.py`: `/chat/start`, `/chat/message`, `/chat/end`.
10. Implement `services/booking_service.create_booking()` (without payment yet — just insert with status `pending_payment`).
11. Write integration test: full happy path booking via chat API.

Frontend tasks:
1. Build `components/chat/chat-widget.tsx` — floating button, panel, uses `lib/api/chat.ts`.
2. Build `message-list.tsx`, `message-input.tsx`.
3. Build `readback-card.tsx` — displays structured slots with edit, from `ui_hints`.
4. Build `confirmation-card.tsx` — Confirm / Change buttons, from `ui_hints`.
5. Add widget to demo page `app/(public)/demo/[slug]/page.tsx`.
6. Use assistant-ui components where they fit, custom where not.

**Done when:**
- Open demo page for Dhaka Dental, click chat button
- Type "I need a cleaning next Tuesday at 2pm"
- AI extracts service, asks for your name, phone, email
- You see a readback card with all details
- Click Confirm → booking appears in Supabase with status `pending_payment`
- Booking visible in business admin's Bookings page (even without payment)

**This phase is the "soul" of the project. Take your time. Test each node in isolation first.**

---

## Phase 5 — Stripe payments + email confirmations (2–3 days)

**Goal:** After booking, user gets a Stripe Checkout link, pays with test card, booking flips to `confirmed`, email sent.

Backend tasks:
1. Implement `integrations/stripe_client.py` — Checkout session creation.
2. Implement `services/payment_service.py` — create session, handle webhook events.
3. Implement `routers/webhooks/stripe.py` — signature verify, idempotency via `webhook_events` table.
4. Integrate: LangGraph `create_payment_action` → creates Stripe session → returns URL in `ui_hints`.
5. Webhook handler: on `checkout.session.completed` → mark payment succeeded, booking confirmed, trigger email.
6. Implement `integrations/resend_client.py` — send email helper.
7. Implement `services/notification_service.py` — `send_booking_confirmation(booking_id)`.
8. Write integration test: mock Stripe webhook event, assert booking + payment state.

Frontend tasks:
1. Build `components/chat/payment-card.tsx` — shows "Pay now" button opening Stripe Checkout in new tab.
2. Add success/cancel redirect pages: `/demo/[slug]/booking/success`, `/demo/[slug]/booking/cancelled`.
3. Poll booking status on success page until webhook confirms (max 10s, fallback message).

**Done when:**
- Full booking flow → click Pay → Stripe test card `4242 4242 4242 4242` → redirect back → booking status `confirmed` in admin → confirmation email received in inbox

---

## Phase 6 — Voice receptionist via Vapi web widget (3–4 days)

**Goal:** "Talk to receptionist" button on demo page → browser mic → real voice booking end-to-end.

Backend tasks:
1. Implement `integrations/vapi_client.py`.
2. Implement `routers/voice.py`: `/voice/vapi-config` (returns assistant config per business), `/voice/webhook` (Vapi server events).
3. Webhook: map Vapi events to same LangGraph brain. Reuse `conversation_service`, reuse graph. Channel-aware prompts (shorter for voice).
4. Handle STT confidence in state (Deepgram scores come in Vapi payload).
5. Implement repair node (`app/ai/nodes/repair.py`) — listens for "no", "wrong", "I said" in user message.

Vapi setup (one-time, via Vapi dashboard or API):
1. Create Vapi assistant with Groq as LLM (custom LLM URL pointing to your backend).
2. OR use Vapi's built-in orchestration: set server URL to your `/voice/webhook`, Vapi calls you for each turn.
3. Configure cheapest Deepgram TTS voice.

Frontend tasks:
1. Build `components/voice/voice-widget.tsx` using `@vapi-ai/web`.
2. Mic permission flow, start/stop call, show live transcript.
3. Add to demo page.
4. Add usage limit: 1 call per session (localStorage flag) to protect Vapi credit.

**Done when:**
- Click "Talk to receptionist" on demo page
- Grant mic permission
- Speak: "I want to book a cleaning for Tuesday at 2"
- AI responds verbally, asks for name, etc.
- Completes booking same as chat
- Booking appears in admin

---

## Phase 7 — Escalation flow (2 days)

**Goal:** AI can hand off to human. Escalation records + email + admin dashboard UI.

Backend tasks:
1. Implement `app/ai/nodes/escalation.py` — triggers per doc 02 rules.
2. Add `check_frustration` node with small LLM sentiment call.
3. Track `consecutive_failures` and intent repetition in state.
4. Implement `services/escalation_service.py` — create record, snapshot transcript, generate suggested response, send email.
5. Implement `routers/admin/escalations.py` — list, detail, patch (resolve, note).
6. Wire LLM to generate `suggested_response` on escalation creation.

Frontend tasks:
1. Build `app/admin/escalations/page.tsx` — list with priority badges, status filter.
2. Build `app/admin/escalations/[id]/page.tsx` — transcript viewer, customer contact, suggested response (copyable), notes, resolve button.
3. Badge in sidebar showing open escalations count.

**Done when:**
- Say "this is ridiculous, I want to talk to a real person" in chat → AI offers to connect → collects contact info → creates escalation → admin email fires → escalation visible in dashboard with suggested response

---

## Phase 8 — RAG (FAQ grounded answers) + LLM judge (2 days)

**Goal:** AI answers business-specific questions from FAQs. Judge validates bookings.

Backend tasks:
1. Implement `app/ai/nodes/rag.py` — `rag_search`, `rag_answer`.
2. Wire for intents `PRICING_INQUIRY`, `BUSINESS_HOURS`, `SERVICE_INFO`, `GENERAL_QUESTION`.
3. Implement `app/ai/nodes/booking.py::llm_judge`.
4. Wire judge into booking sub-graph before `explicit_confirmation`.
5. Add handling for judge-rejected bookings (re-ask user, max 2 retries before escalation).

**Done when:**
- Ask "do you accept Blue Cross?" mid-chat → AI answers from FAQ correctly
- Ask nonsense FAQ not in DB → AI says "I don't have that info, let me escalate"
- Judge catches an obvious mistake (seed a bad transcript, verify rejection)

---

## Phase 9 — Cancel + reschedule (1–2 days)

**Goal:** Customer can cancel/reschedule via chat.

Backend tasks:
1. Implement `app/ai/nodes/cancel.py` — lookup booking by phone/email, confirm, cancel/reschedule.
2. Implement `services/booking_service.cancel_booking()`, `reschedule_booking()`.
3. Stripe refund for cancellations within policy window.

Frontend: no new UI.

**Done when:**
- "I need to cancel my appointment" → AI asks phone → looks up → reads back → confirms → cancels → email fires

---

## Phase 10 — Analytics + super admin (3–4 days)

**Goal:** Both dashboards show real data.

Backend tasks:
1. Implement `services/analytics_service.py`.
2. Implement `routers/admin/analytics.py` + `routers/super/analytics.py`.
3. Implement `routers/super/businesses.py`, `routers/super/settings.py`, `routers/super/audit_logs.py`.
4. Wire `audit.py` writer into sensitive mutations (business create/suspend, settings update).
5. Implement `integrations/` for platform_settings encryption key management.

Frontend tasks:
1. Build `app/admin/analytics/page.tsx` with Tremor stat cards + Recharts trend.
2. Build `app/admin/page.tsx` dashboard overview (replace stubs).
3. Build all `app/super/*` pages.
4. Super admin: businesses list, detail, suspend/activate, settings editor (masked keys), audit log viewer.

**Done when:**
- Business admin dashboard shows real booking count, revenue, conversion rate
- Super admin sees all 3 demo businesses, can suspend/activate, can rotate Groq API key

---

## Phase 11 — Polish + deploy (3–4 days)

**Goal:** Live on the internet. Presentable.

Tasks:
1. Landing page design pass (hero, features, demo selector, "Try chatbot" / "Talk to receptionist" CTAs).
2. Loading states, empty states, error boundaries everywhere.
3. Mobile responsive check (admin dashboard can be desktop-only, demo must be mobile-friendly).
4. SEO meta tags, og-image, favicon.
5. Deploy backend: Render or Fly.io. Env vars configured. UptimeRobot pinging `/health` every 5 min.
6. Deploy frontend: Vercel. Env vars. Point `NEXT_PUBLIC_API_URL` to live backend.
7. Configure Stripe webhook to point at live backend URL.
8. Configure Vapi assistant server URL to live backend.
9. Test full flow on live URL.
10. Record 30-second phone call demo video (use Twilio trial credit for one week).
11. GitHub repo README with architecture diagram, demo URL, tech stack badges, demo credentials.
12. Add `docs/ARCHITECTURE.md` for public consumption (interview fodder).

**Done when:** you send a friend a link, they book an appointment, nothing breaks.

---

## Phase 12 (optional) — Stretch features

Pick 1–2 based on what's impressive for target roles:

- **Streaming chat responses** (Next.js server-sent events, Groq streaming)
- **Multi-language support** (Bangla + English — you have prior experience here)
- **Admin-facing AI assistant** (ask questions about your business data in natural language)
- **Calendar sync** (Google Calendar two-way sync)
- **SMS confirmations** (Twilio, real cost)
- **Live phone number** (Twilio + Vapi inbound, real cost)
- **Multi-staff per business** (invite team members, roles)
- **Custom domain per business** (white-label: dental.dhakadental.com)

---

## Total timeline

| Phase | Days |
|---|---|
| 0. Setup | 1 |
| 1. Data + auth | 3–4 |
| 2. Admin dashboard + CRUD | 4–5 |
| 3. Embeddings + public page | 2 |
| 4. Chat receptionist | 5–7 |
| 5. Payments + email | 2–3 |
| 6. Voice receptionist | 3–4 |
| 7. Escalation | 2 |
| 8. RAG + judge | 2 |
| 9. Cancel/reschedule | 1–2 |
| 10. Analytics + super admin | 3–4 |
| 11. Polish + deploy | 3–4 |
| **Total** | **31–42 days** |

At 5 focused days/week, this is **6–8 weeks** solo with Claude Code. Realistic. Tight but real.

---

## Rules that apply to every phase

1. **Commit after every working feature.** Small commits. Good messages.
2. **Never start Phase N+1 until Phase N's "Done when" is true.**
3. **If a phase slips >50% over estimate, stop and re-plan — something is wrong.**
4. **Keep a `PHASE_LOG.md`** in root: jot lessons, gotchas, decisions made. Interview gold.
5. **Test as you build.** No "testing phase at the end" — that phase never happens.
6. **Tell Claude Code which phase you're in** at the start of every session. Paste the phase's task list. Scope control.