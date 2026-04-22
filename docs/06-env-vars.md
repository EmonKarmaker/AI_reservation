## What this document is (plain English)

This is **every key, password, and config value** the app needs — what each one does, where to get it, and which parts of the app use it.

**Why it matters:** Secrets in code get leaked to GitHub and abused. Missing env vars crash the app at the worst time (production, 2am, during a demo). Having them all documented in one place means: no surprises, no leaks, no 3am debugging sessions.

**How to read it:**
- **Variable name** = exact string to use in `.env`
- **Where to get it** = the service + exact steps
- **Used by** = which part of the app reads it
- **Required for phase** = which build phase first needs it (so you don't sign up for 8 services on day 1)

**The golden rules:**
1. Never commit `.env` to git. Only `.env.example` with dummy values.
2. Never paste a real secret into this chat, into ChatGPT, into Claude Code, or into anyone's DM.
3. Rotate keys if you suspect leak. Every service has a "regenerate" button.
4. Store production secrets in Render/Vercel dashboards, not in files.

**When Claude Code uses this document:** it creates `.env.example` files matching this spec, wires `app/config.py` to load them, and never hardcodes secrets.

---

# Environment Variables

## Backend (`backend/.env`)

### Database

**`DATABASE_URL`**
- *Purpose:* async connection string to PostgreSQL
- *Format:* `postgresql+asyncpg://user:pass@host:port/dbname`
- *Where to get:* Supabase → Project Settings → Database → Connection string → "URI" tab → replace `postgresql://` with `postgresql+asyncpg://`
- *Used by:* SQLAlchemy engine
- *Required for phase:* 0
- *Example:* `postgresql+asyncpg://postgres:xxx@db.abcdefgh.supabase.co:5432/postgres`

**`DATABASE_URL_SYNC`**
- *Purpose:* sync connection string, needed by Alembic (Alembic doesn't support async natively in simple setup)
- *Format:* `postgresql+psycopg2://user:pass@host:port/dbname`
- *Where to get:* same as above, different driver prefix
- *Used by:* Alembic
- *Required for phase:* 0
- *Example:* `postgresql+psycopg2://postgres:xxx@db.abcdefgh.supabase.co:5432/postgres`

### Security

**`JWT_SECRET_KEY`**
- *Purpose:* signs access + refresh tokens
- *Format:* random 64-byte base64 string
- *How to generate:* `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- *Used by:* `app/core/security.py`
- *Required for phase:* 1
- *Rotation:* rotating invalidates all sessions — warn before doing this in prod

**`JWT_ALGORITHM`**
- *Purpose:* JWT signing algorithm
- *Default:* `HS256`
- *Required for phase:* 1

**`JWT_ACCESS_EXPIRE_MINUTES`**
- *Default:* `15`

**`JWT_REFRESH_EXPIRE_DAYS`**
- *Default:* `7`

**`PLATFORM_ENCRYPTION_KEY`**
- *Purpose:* Fernet key for encrypting values in `platform_settings` table (like the Groq API key stored in DB)
- *Format:* 32-byte URL-safe base64
- *How to generate:* `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- *Used by:* `app/core/encryption.py`
- *Required for phase:* 1
- *Rotation:* rotating requires re-encrypting all rows in `platform_settings` — script this

### CORS + deployment

**`FRONTEND_ORIGIN`**
- *Purpose:* allowed CORS origin
- *Dev:* `http://localhost:3000`
- *Prod:* your Vercel URL, e.g. `https://ai-reservation.vercel.app`
- *Used by:* FastAPI CORSMiddleware
- *Required for phase:* 0

**`BACKEND_ORIGIN`**
- *Purpose:* this app's own base URL, used for building webhook URLs + cookie domain
- *Dev:* `http://localhost:8000`
- *Prod:* your Render/Fly URL
- *Required for phase:* 0

**`ENVIRONMENT`**
- *Values:* `dev` | `staging` | `prod`
- *Purpose:* controls debug mode, cookie `secure` flag, Swagger exposure
- *Required for phase:* 0

**`LOG_LEVEL`**
- *Default:* `INFO`
- *Values:* `DEBUG` | `INFO` | `WARNING` | `ERROR`

### LLM (Groq)

**`GROQ_API_KEY`**
- *Purpose:* LLM calls for intent classification, slot extraction, LLM-as-judge, etc.
- *Where to get:* console.groq.com → API Keys → Create API Key. Free tier.
- *Used by:* `app/ai/llm.py`
- *Required for phase:* 4
- *Cost:* free tier generous for dev. Rate-limited.
- *Note:* also stored encrypted in `platform_settings` table — `.env` value is the bootstrap default; super admin can change via dashboard later.

**`GROQ_MODEL_FAST`**
- *Purpose:* intent classification, small tasks
- *Default:* `llama-3.1-8b-instant`
- *Required for phase:* 4

**`GROQ_MODEL_SMART`**
- *Purpose:* slot extraction, judge, RAG answer
- *Default:* `llama-3.3-70b-versatile`
- *Required for phase:* 4

### Embeddings

**`EMBEDDING_MODEL`**
- *Purpose:* sentence-transformers model name
- *Default:* `sentence-transformers/all-MiniLM-L6-v2`
- *Note:* 384 dimensions. If you change this, update `vector(384)` in schema + migrate.
- *Required for phase:* 3

**`EMBEDDING_DEVICE`**
- *Values:* `cpu` | `cuda`
- *Default:* `cpu` (free hosting doesn't have GPU)
- *Required for phase:* 3

### Stripe

**`STRIPE_SECRET_KEY`**
- *Purpose:* API calls to Stripe
- *Where to get:* dashboard.stripe.com → Developers → API keys → Secret key. **Test mode starts with `sk_test_`**. Keep test mode for the whole portfolio demo.
- *Used by:* `app/integrations/stripe_client.py`
- *Required for phase:* 5

**`STRIPE_PUBLISHABLE_KEY`**
- *Purpose:* frontend uses this to render Checkout (if embedding Stripe Elements later)
- *Where to get:* same page as above, starts with `pk_test_`
- *Required for phase:* 5
- *Note:* also needs to go in `frontend/.env.local` as `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`

**`STRIPE_WEBHOOK_SECRET`**
- *Purpose:* verifies webhook signatures
- *Where to get:* Stripe Dashboard → Developers → Webhooks → Add endpoint → your `/webhooks/stripe` URL → copy "Signing secret" starting with `whsec_`
- *Used by:* `app/routers/webhooks/stripe.py`
- *Required for phase:* 5
- *Dev:* use Stripe CLI `stripe listen --forward-to localhost:8000/webhooks/stripe` — it gives you a different `whsec_` for local

**`STRIPE_SUCCESS_URL`**
- *Purpose:* redirect after successful payment
- *Dev:* `http://localhost:3000/demo/{slug}/booking/success?session_id={CHECKOUT_SESSION_ID}`
- *Required for phase:* 5

**`STRIPE_CANCEL_URL`**
- *Purpose:* redirect after cancelled payment
- *Required for phase:* 5

### Vapi (voice)

**`VAPI_PRIVATE_KEY`**
- *Purpose:* server-side Vapi API calls (create assistants, update configs)
- *Where to get:* vapi.ai dashboard → API Keys → Private Key
- *Required for phase:* 6

**`VAPI_PUBLIC_KEY`**
- *Purpose:* frontend widget uses this to initiate calls
- *Where to get:* same dashboard, Public Key
- *Required for phase:* 6
- *Also goes in frontend:* `NEXT_PUBLIC_VAPI_PUBLIC_KEY`

**`VAPI_WEBHOOK_SECRET`**
- *Purpose:* verifies Vapi webhook calls to `/voice/webhook`
- *Where to get:* Vapi dashboard → Assistant settings → Server URL → Secret
- *Required for phase:* 6

**`VAPI_ASSISTANT_ID_DEFAULT`**
- *Purpose:* fallback assistant if per-business not set
- *Where to get:* create one assistant in Vapi dashboard, copy ID
- *Required for phase:* 6

### Email (Resend)

**`RESEND_API_KEY`**
- *Purpose:* send confirmation and escalation emails
- *Where to get:* resend.com → API Keys. Free tier: 3,000 emails/month.
- *Required for phase:* 5
- *Used by:* `app/integrations/resend_client.py`

**`RESEND_FROM_EMAIL`**
- *Purpose:* "from" address on emails
- *Value:* your verified domain email, e.g. `hello@yourdomain.com`, OR `onboarding@resend.dev` for testing without a verified domain
- *Required for phase:* 5

**`RESEND_REPLY_TO`**
- *Purpose:* optional reply-to for escalation emails
- *Required for phase:* 7

### Supabase Storage

**`SUPABASE_URL`**
- *Purpose:* storage API base URL
- *Where to get:* Supabase → Project Settings → API → Project URL
- *Required for phase:* 2

**`SUPABASE_SERVICE_ROLE_KEY`**
- *Purpose:* server-side storage uploads (bypasses RLS)
- *Where to get:* Supabase → Project Settings → API → service_role key
- *Warning:* never expose to frontend. Server-only.
- *Required for phase:* 2

**`SUPABASE_STORAGE_BUCKET`**
- *Default:* `business-assets`
- *Note:* create this bucket in Supabase dashboard (Storage → New bucket → public read or signed URLs)
- *Required for phase:* 2

### Redis / cache (optional, Phase 10+)

**`REDIS_URL`**
- *Purpose:* rate limiting, task queue, caching
- *Values:* `redis://localhost:6379/0` dev, or Upstash free URL in prod
- *Optional:* skip until Phase 10 analytics or if you add rate limiting earlier

### Scheduler

**`SCHEDULER_ENABLED`**
- *Values:* `true` | `false`
- *Purpose:* disable APScheduler on certain deploys
- *Default:* `true`
- *Required for phase:* (reminders phase, optional stretch)

---

## Frontend (`frontend/.env.local`)

Next.js splits env vars into **`NEXT_PUBLIC_*`** (sent to browser, visible to users) and **server-only** (API routes only).

**`NEXT_PUBLIC_API_URL`**
- *Purpose:* base URL of FastAPI backend
- *Dev:* `http://localhost:8000/api/v1`
- *Prod:* `https://your-backend.onrender.com/api/v1`
- *Required for phase:* 2
- *Used by:* `lib/api/client.ts`

**`NEXT_PUBLIC_APP_URL`**
- *Purpose:* this Next.js app's own URL (for absolute links, OG tags)
- *Dev:* `http://localhost:3000`
- *Prod:* your Vercel URL
- *Required for phase:* 2

**`NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`**
- *Purpose:* frontend Stripe initialization (only if using embedded Elements later; not required for hosted Checkout)
- *Required for phase:* 5 (optional — can stay hosted-redirect only)

**`NEXT_PUBLIC_VAPI_PUBLIC_KEY`**
- *Purpose:* Vapi Web SDK init
- *Required for phase:* 6

**`NEXT_PUBLIC_ENABLE_VOICE`**
- *Values:* `true` | `false`
- *Purpose:* feature flag to hide voice button if Vapi credits exhausted
- *Default:* `true`
- *Required for phase:* 6

---

## `.env.example` (commit this) — backend

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ai_reservation
DATABASE_URL_SYNC=postgresql+psycopg2://postgres:password@localhost:5432/ai_reservation

# Security
JWT_SECRET_KEY=change-me-in-prod-use-secrets-token-urlsafe-64
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MINUTES=15
JWT_REFRESH_EXPIRE_DAYS=7
PLATFORM_ENCRYPTION_KEY=change-me-use-Fernet-generate-key

# Deployment
FRONTEND_ORIGIN=http://localhost:3000
BACKEND_ORIGIN=http://localhost:8000
ENVIRONMENT=dev
LOG_LEVEL=INFO

# LLM
GROQ_API_KEY=gsk_...
GROQ_MODEL_FAST=llama-3.1-8b-instant
GROQ_MODEL_SMART=llama-3.3-70b-versatile

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_SUCCESS_URL=http://localhost:3000/demo/{slug}/booking/success?session_id={CHECKOUT_SESSION_ID}
STRIPE_CANCEL_URL=http://localhost:3000/demo/{slug}/booking/cancelled

# Vapi
VAPI_PRIVATE_KEY=
VAPI_PUBLIC_KEY=
VAPI_WEBHOOK_SECRET=
VAPI_ASSISTANT_ID_DEFAULT=

# Email
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=onboarding@resend.dev
RESEND_REPLY_TO=

# Supabase Storage
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=business-assets

# Scheduler
SCHEDULER_ENABLED=true
```

## `.env.example` (commit this) — frontend

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
NEXT_PUBLIC_VAPI_PUBLIC_KEY=
NEXT_PUBLIC_ENABLE_VOICE=true
```

---

## Signup checklist (do these as you hit each phase, not all on day 1)

| Service | Phase | Account needed | Free tier |
|---|---|---|---|
| Supabase | 0 | yes | 500MB DB, 1GB storage, 7-day pause on inactivity |
| Groq | 4 | yes | generous rate limits |
| Stripe | 5 | yes | test mode free forever |
| Resend | 5 | yes | 3,000 emails/month |
| Vapi | 6 | yes | ~$10 starter credit |
| Render / Fly.io | 11 | yes | free web + db tier |
| Vercel | 11 | yes | generous free tier |
| UptimeRobot | 11 | yes | free 50 monitors |
| GitHub | 0 | yes | free |
| Twilio (optional) | stretch | optional | $15 trial |

Don't sign up for Vapi or Stripe on day 1. You don't need them until Phase 5+. Focus reduces setup overhead.

---

## Secret rotation policy

Rotate any secret if:
- You accidentally committed it
- Somebody else saw it
- 90 days have passed in prod
- Service emailed you about suspicious activity

To rotate: generate new value in provider dashboard → update Render/Vercel env → redeploy → delete old key in provider dashboard.

`PLATFORM_ENCRYPTION_KEY` is special — rotating it needs a script to re-encrypt `platform_settings` rows. Don't rotate casually.

---

## Dev convenience

For local dev, create a `.env` in `backend/` and a `.env.local` in `frontend/`. Both are in `.gitignore`.

A single `direnv` or `.envrc` at the repo root can auto-load the right env when you `cd` into each folder — optional, nice to have.

Never paste `.env` contents into this chat, Claude Code, GitHub issues, screenshots, Stack Overflow, or Slack. If it happens, rotate the key immediately.