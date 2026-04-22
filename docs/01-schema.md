# Database Schema
## What this document is (plain English)

This is the blueprint for the database — every table, every column, every relationship. Think of it as the floor plan of a house before construction.

**Why it matters:** Every other part of the app (backend API, frontend forms, AI logic) reads from and writes to these tables. If the schema is wrong, everything built on top of it is wrong. We design it once, carefully, then build against it.

**How to read it:**
- **Tables** are the big boxes that hold data (users, businesses, bookings, etc.)
- **Columns** are the fields inside each table (name, email, price, etc.)
- **Foreign keys (FK)** are links between tables (e.g., a booking belongs to a business)
- **Indexes** make lookups fast (think: the index at the back of a book)
- **Enums** are fixed lists of allowed values (e.g., booking status can only be: pending_payment, confirmed, cancelled, completed, no_show)

**The 17 tables split into two groups:**
1. **Platform-level** (3 tables) — stuff the super admin owns: all users, global settings, audit logs
2. **Business-level** (14 tables) — stuff that belongs to one business: services, bookings, conversations, FAQs, etc. Every one of these has a `business_id` column so we know which business owns each row.

**The key security rule baked in:** every query for a business admin is filtered by their `business_id`. The AI for "Dhaka Dental" literally cannot see data belonging to "Dhaka HVAC" because the database query doesn't allow it.

**When Claude Code uses this document:** it creates SQLAlchemy models (Python classes) and Alembic migrations (SQL scripts) that match this schema exactly.

---
## Design principles
- PostgreSQL 16 with `pgvector`, `pgcrypto` (for gen_random_uuid), `citext` (case-insensitive emails) extensions
- All primary keys are UUIDs (`gen_random_uuid()`)
- All tables have `created_at` and `updated_at` timestamps (UTC, `timestamptz`)
- Business-scoped tables carry `business_id` with foreign key + index
- Soft delete via `deleted_at timestamptz NULL` on user-facing tables (businesses, services, bookings). Hard delete for logs, messages, embeddings.
- Foreign keys use `ON DELETE CASCADE` only where child data is meaningless without parent (e.g., messages when conversation deleted). Otherwise `ON DELETE RESTRICT`.
- All money stored as `numeric(10,2)` in a single currency per business (USD default, currency code on business).
- All enum-like fields use PostgreSQL native `ENUM` types for type safety.

## Enums (create first)

```sql
CREATE TYPE user_role AS ENUM ('super_admin', 'business_admin');
CREATE TYPE business_status AS ENUM ('active', 'suspended', 'pending');
CREATE TYPE booking_status AS ENUM ('pending_payment', 'confirmed', 'cancelled', 'completed', 'no_show');
CREATE TYPE payment_status AS ENUM ('pending', 'succeeded', 'failed', 'refunded');
CREATE TYPE conversation_channel AS ENUM ('chat', 'voice');
CREATE TYPE conversation_status AS ENUM ('active', 'completed', 'abandoned', 'escalated');
CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool');
CREATE TYPE escalation_status AS ENUM ('open', 'in_progress', 'resolved', 'dismissed');
CREATE TYPE escalation_priority AS ENUM ('low', 'medium', 'high');
CREATE TYPE embedding_source_type AS ENUM ('business', 'service', 'faq');
CREATE TYPE day_of_week AS ENUM ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun');
```

---

## Platform-level tables (no business_id)

### `users`
The only table where both super admin and business admins live. Super admin has `business_id = NULL`. Business admin has `business_id` set.

| column | type | notes |
|---|---|---|
| id | uuid PK | gen_random_uuid() |
| email | citext UNIQUE NOT NULL | case-insensitive |
| password_hash | text NOT NULL | bcrypt |
| full_name | text NOT NULL | |
| role | user_role NOT NULL | super_admin or business_admin |
| business_id | uuid NULL | FK → businesses.id, NULL for super_admin |
| is_active | boolean NOT NULL DEFAULT true | |
| last_login_at | timestamptz NULL | |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |
| deleted_at | timestamptz NULL | |

Indexes: `email` (unique), `business_id`, `role`.
Constraint: `CHECK ((role = 'super_admin' AND business_id IS NULL) OR (role = 'business_admin' AND business_id IS NOT NULL))`

### `platform_settings`
Singleton-like table for global config (one row expected, but supports future multi-key needs).

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| key | text UNIQUE NOT NULL | e.g. 'groq_api_key', 'stripe_webhook_secret' |
| value_encrypted | text NOT NULL | Fernet-encrypted |
| description | text NULL | |
| updated_by | uuid NULL | FK → users.id |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `key` (unique).
Note: Encryption key lives in env var `PLATFORM_ENCRYPTION_KEY`, never in DB.

### `audit_logs`
Immutable log of sensitive admin actions.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| actor_user_id | uuid NOT NULL | FK → users.id |
| action | text NOT NULL | e.g. 'business.created', 'settings.updated' |
| entity_type | text NOT NULL | e.g. 'business', 'service' |
| entity_id | uuid NULL | the affected record |
| metadata | jsonb NOT NULL DEFAULT '{}' | before/after, context |
| ip_address | inet NULL | |
| created_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `actor_user_id`, `entity_type, entity_id`, `created_at DESC`.
No updated_at. Append-only.

---

## Business-level tables

### `businesses`
One row per tenant.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| slug | citext UNIQUE NOT NULL | URL-safe identifier, e.g. 'dhaka-dental' |
| name | text NOT NULL | display name |
| description | text NULL | |
| industry | text NULL | dental, hvac, law, salon, etc. |
| timezone | text NOT NULL DEFAULT 'UTC' | IANA, e.g. 'Asia/Dhaka' |
| currency | char(3) NOT NULL DEFAULT 'USD' | ISO 4217 |
| phone | text NULL | |
| email | citext NULL | |
| website | text NULL | |
| address | text NULL | |
| logo_url | text NULL | Supabase Storage URL |
| status | business_status NOT NULL DEFAULT 'active' | |
| ai_personality | text NULL | system prompt customization |
| ai_greeting | text NULL | first message the AI says |
| booking_window_days | int NOT NULL DEFAULT 60 | how far in advance bookings allowed |
| cancellation_hours | int NOT NULL DEFAULT 24 | hours before booking to allow cancel |
| stripe_account_id | text NULL | Stripe Connect (future, optional) |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |
| deleted_at | timestamptz NULL | |

Indexes: `slug` (unique), `status`, `deleted_at`.

### `business_settings`
Per-business configuration that may grow. Separate table avoids bloating `businesses`.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL UNIQUE | FK → businesses.id ON DELETE CASCADE |
| require_payment_at_booking | boolean NOT NULL DEFAULT true | |
| deposit_percentage | int NOT NULL DEFAULT 0 | 0 = full pay, 100 = full, 50 = deposit |
| auto_confirm_bookings | boolean NOT NULL DEFAULT true | |
| send_reminder_hours_before | int NOT NULL DEFAULT 24 | |
| escalation_email | citext NULL | override — else business.email |
| max_daily_bookings | int NULL | capacity cap, optional |
| custom_api_key_encrypted | text NULL | BYO Groq key if set (Fernet) |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

### `operating_hours`
Weekly recurring schedule.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| day_of_week | day_of_week NOT NULL | |
| open_time | time NOT NULL | |
| close_time | time NOT NULL | |
| is_closed | boolean NOT NULL DEFAULT false | if true, open/close ignored |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `business_id, day_of_week` (unique together).
Constraint: `CHECK (is_closed OR close_time > open_time)`

### `schedule_exceptions`
One-off closures or special hours (holidays, sick days).

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| exception_date | date NOT NULL | |
| is_closed | boolean NOT NULL DEFAULT true | |
| open_time | time NULL | if not fully closed |
| close_time | time NULL | |
| reason | text NULL | "Eid holiday" |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `business_id, exception_date` (unique together).

### `services`
Each bookable service.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| name | text NOT NULL | "Teeth Cleaning" |
| description | text NULL | |
| duration_minutes | int NOT NULL | 30, 60, 90 |
| buffer_minutes | int NOT NULL DEFAULT 0 | prep/cleanup time after |
| price | numeric(10,2) NOT NULL | |
| is_active | boolean NOT NULL DEFAULT true | |
| display_order | int NOT NULL DEFAULT 0 | sort order in UI |
| image_url | text NULL | Supabase Storage |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |
| deleted_at | timestamptz NULL | |

Indexes: `business_id`, `business_id, is_active`, `deleted_at`.
Constraint: `CHECK (duration_minutes > 0 AND buffer_minutes >= 0 AND price >= 0)`

### `customers`
End users who booked. No login, identified by phone+email per business.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| full_name | text NOT NULL | |
| email | citext NULL | |
| phone | text NULL | E.164 format preferred |
| notes | text NULL | admin-visible notes |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `business_id`, `business_id, phone`, `business_id, email`.
Constraint: `CHECK (email IS NOT NULL OR phone IS NOT NULL)`

### `bookings`
The central entity.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| customer_id | uuid NOT NULL | FK → customers.id ON DELETE RESTRICT |
| service_id | uuid NOT NULL | FK → services.id ON DELETE RESTRICT |
| conversation_id | uuid NULL | FK → conversations.id, where booking originated |
| starts_at | timestamptz NOT NULL | |
| ends_at | timestamptz NOT NULL | |
| status | booking_status NOT NULL DEFAULT 'pending_payment' | |
| total_amount | numeric(10,2) NOT NULL | snapshot at booking time |
| currency | char(3) NOT NULL | snapshot |
| notes | text NULL | customer-provided notes |
| admin_notes | text NULL | internal |
| idempotency_key | text UNIQUE NOT NULL | hash of conv+service+time+phone |
| cancelled_at | timestamptz NULL | |
| cancelled_reason | text NULL | |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |
| deleted_at | timestamptz NULL | |

Indexes: `business_id`, `business_id, starts_at`, `customer_id`, `service_id`, `status`, `idempotency_key` (unique).
Constraint: `CHECK (ends_at > starts_at)`

### `payments`
Stripe payment records. One-to-many with bookings (deposits, refunds).

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| booking_id | uuid NOT NULL | FK → bookings.id ON DELETE RESTRICT |
| amount | numeric(10,2) NOT NULL | |
| currency | char(3) NOT NULL | |
| status | payment_status NOT NULL DEFAULT 'pending' | |
| stripe_checkout_session_id | text NULL UNIQUE | |
| stripe_payment_intent_id | text NULL UNIQUE | |
| stripe_refund_id | text NULL | |
| failure_reason | text NULL | |
| paid_at | timestamptz NULL | |
| refunded_at | timestamptz NULL | |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `business_id`, `booking_id`, `status`, `stripe_checkout_session_id`, `stripe_payment_intent_id`.

### `conversations`
One row per chat session OR voice call. Shared table, distinguished by `channel`.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| customer_id | uuid NULL | FK → customers.id, set once identified |
| channel | conversation_channel NOT NULL | chat or voice |
| status | conversation_status NOT NULL DEFAULT 'active' | |
| session_token | text UNIQUE NOT NULL | client-side identifier |
| vapi_call_id | text NULL UNIQUE | for voice |
| langgraph_state | jsonb NOT NULL DEFAULT '{}' | serialized state between turns |
| intent_history | jsonb NOT NULL DEFAULT '[]' | list of classified intents |
| booking_id | uuid NULL | FK → bookings.id, if conversation resulted in booking |
| ended_at | timestamptz NULL | |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `business_id`, `business_id, created_at DESC`, `session_token`, `vapi_call_id`, `status`.

### `messages`
Every turn of every conversation.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| conversation_id | uuid NOT NULL | FK → conversations.id ON DELETE CASCADE |
| role | message_role NOT NULL | user, assistant, system, tool |
| content | text NOT NULL | |
| metadata | jsonb NOT NULL DEFAULT '{}' | intent, confidence, tool calls, etc. |
| tokens_used | int NULL | for cost tracking |
| latency_ms | int NULL | response latency |
| created_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `conversation_id`, `conversation_id, created_at`.
No updated_at, messages are immutable.

### `escalations`
When AI hands off to human.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| conversation_id | uuid NOT NULL | FK → conversations.id ON DELETE RESTRICT |
| customer_name | text NULL | snapshot |
| customer_phone | text NULL | |
| customer_email | citext NULL | |
| reason | text NOT NULL | 'explicit_request', 'repeated_failure', 'frustration', 'complaint', 'low_confidence' |
| priority | escalation_priority NOT NULL DEFAULT 'medium' | |
| status | escalation_status NOT NULL DEFAULT 'open' | |
| transcript_snapshot | jsonb NOT NULL | frozen copy of messages at escalation |
| suggested_response | text NULL | LLM-drafted reply suggestion |
| admin_notes | text NULL | |
| resolved_by | uuid NULL | FK → users.id |
| resolved_at | timestamptz NULL | |
| email_sent_at | timestamptz NULL | when admin was notified |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `business_id`, `business_id, status`, `priority, created_at DESC`, `conversation_id`.

### `faqs`
Per-business knowledge base content, feeds RAG.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| question | text NOT NULL | |
| answer | text NOT NULL | |
| category | text NULL | 'pricing', 'policy', 'hours', etc. |
| is_active | boolean NOT NULL DEFAULT true | |
| display_order | int NOT NULL DEFAULT 0 | |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `business_id`, `business_id, is_active`.

### `embeddings`
Polymorphic vector store. One row per embeddable piece of content.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| business_id | uuid NOT NULL | FK → businesses.id ON DELETE CASCADE |
| source_type | embedding_source_type NOT NULL | 'business', 'service', 'faq' |
| source_id | uuid NOT NULL | the record being embedded |
| content | text NOT NULL | the actual text that was embedded |
| embedding | vector(384) NOT NULL | MiniLM output, 384 dims |
| metadata | jsonb NOT NULL DEFAULT '{}' | |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Indexes:
- `business_id`
- `source_type, source_id` (unique together — one embedding per source record)
- HNSW index on `embedding` for fast cosine similarity: `CREATE INDEX embeddings_hnsw_idx ON embeddings USING hnsw (embedding vector_cosine_ops);`

Auto-sync: trigger on services/faqs/businesses CRUD (application-level, not DB trigger) re-embeds.

### `webhook_events`
Idempotency log for Stripe and Vapi webhooks.

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| source | text NOT NULL | 'stripe', 'vapi' |
| event_id | text NOT NULL | provider-given event id |
| event_type | text NOT NULL | 'checkout.session.completed', etc. |
| payload | jsonb NOT NULL | raw event |
| processed | boolean NOT NULL DEFAULT false | |
| processed_at | timestamptz NULL | |
| error | text NULL | if processing failed |
| created_at | timestamptz NOT NULL DEFAULT now() | |

Indexes: `source, event_id` (unique together), `processed, created_at`.

---

## Views (optional, defer to later if Alembic doesn't like)

- `v_business_stats` — per-business booking count, revenue, avg conversion rate
- `v_platform_stats` — super admin aggregates

Skip for v1; build as application-level queries first.

---

## Summary table count
15 tables: `users`, `platform_settings`, `audit_logs`, `businesses`, `business_settings`, `operating_hours`, `schedule_exceptions`, `services`, `customers`, `bookings`, `payments`, `conversations`, `messages`, `escalations`, `faqs`, `embeddings`, `webhook_events` = **17 tables.**

## Migration order (Alembic)
1. Extensions (pgcrypto, citext, pgvector)
2. Enums
3. Platform tables: `users`, `platform_settings`, `audit_logs`
4. Business core: `businesses`, `business_settings`
5. Schedule: `operating_hours`, `schedule_exceptions`
6. Catalog: `services`, `faqs`
7. Customer + booking: `customers`, `bookings`, `payments`
8. AI: `conversations`, `messages`, `escalations`, `embeddings`
9. Infra: `webhook_events`
10. Indexes (especially HNSW on embeddings — do this last, after seed data if testing)

Users FK to businesses is a chicken-and-egg (users need business_id, businesses are created by users). Resolve by: create first super admin via seed script after businesses table exists, or allow `business_id NULL` and create super admin first.