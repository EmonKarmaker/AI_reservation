## What this document is (plain English)

This is the **contract between frontend and backend** — every URL the frontend can call, what it sends, what it gets back, who's allowed to call it.

**Why it matters:** The frontend and backend are two separate programs talking over the internet. If they disagree on what an endpoint is called or what shape the data takes, nothing works. This document locks the contract so both sides build against the same spec.

**How to read it:**
- **Method + Path** = the URL (e.g., `POST /api/v1/auth/login`)
- **Auth** = who can call it (public, business_admin, super_admin)
- **Request body** = what the frontend sends
- **Response body** = what the backend returns
- **Errors** = what can go wrong and the HTTP status code

**Three roles, three access levels:**
- **Public** — no auth needed (login, chat widget, voice widget, Stripe/Vapi webhooks)
- **Business Admin** — JWT required, scoped to their `business_id`
- **Super Admin** — JWT required, can access any business

**When Claude Code uses this document:** it generates FastAPI routers, Pydantic request/response models, and authentication middleware matching this spec.

---

# API Surface

## Conventions

- Base URL: `/api/v1`
- All requests/responses are JSON unless noted
- Auth: JWT in httpOnly cookie named `access_token`, 15-minute expiry; refresh token in httpOnly cookie `refresh_token`, 7-day expiry
- All timestamps in ISO 8601 UTC
- All IDs are UUIDs (strings in JSON)
- Pagination: `?page=1&limit=20`, max limit 100
- Standard error shape: `{ "error": "code", "message": "human readable", "details": {} }`
- Business admin endpoints auto-filter by `business_id` from JWT — no `business_id` in URL
- Super admin endpoints take `business_id` as query param when targeting a specific business

## HTTP status codes
- 200 OK — success
- 201 Created — resource created
- 204 No Content — success, no body (deletes)
- 400 Bad Request — validation failed
- 401 Unauthorized — not logged in
- 403 Forbidden — logged in but not allowed
- 404 Not Found
- 409 Conflict — duplicate / idempotency
- 422 Unprocessable — semantic error (e.g., booking outside hours)
- 429 Rate Limited
- 500 Server Error

---

## 1. Auth (public)

### `POST /auth/register`
Super admin creates a new business + first business admin user in one call. Public in v1 for demo purposes; restrict later.

Request:
```json
{
  "business_name": "Dhaka Dental",
  "business_slug": "dhaka-dental",
  "industry": "dental",
  "timezone": "Asia/Dhaka",
  "admin_email": "owner@dhakadental.com",
  "admin_password": "...",
  "admin_full_name": "Dr. Rahman"
}
```

Response 201:
```json
{
  "business_id": "uuid",
  "user_id": "uuid",
  "message": "Business created, check email to confirm"
}
```

Errors: 409 if slug or email taken.

### `POST /auth/login`
Request:
```json
{ "email": "...", "password": "..." }
```

Response 200: sets cookies, returns user info.
```json
{
  "user": {
    "id": "uuid",
    "email": "...",
    "full_name": "...",
    "role": "business_admin",
    "business_id": "uuid | null"
  }
}
```

Errors: 401 invalid creds, 403 account suspended.

### `POST /auth/logout`
Clears cookies. Response 204.

### `POST /auth/refresh`
Uses refresh token cookie to issue new access token. Response 200 with user info.

### `GET /auth/me`
Returns current user from JWT. Response 200 with user info. 401 if not logged in.

---

## 2. Public chat + voice (no auth)

### `POST /chat/start`
Creates a new conversation. Returns session token.

Request:
```json
{ "business_slug": "dhaka-dental" }
```

Response 201:
```json
{
  "conversation_id": "uuid",
  "session_token": "opaque-string",
  "greeting": "Hi! I'm the receptionist for Dhaka Dental. How can I help?"
}
```

### `POST /chat/message`
Sends a user message, returns AI response.

Request:
```json
{
  "session_token": "...",
  "message": "I need to book a cleaning"
}
```

Response 200:
```json
{
  "response": "Sure! What day works for you?",
  "actions": [],
  "conversation_status": "active",
  "ui_hints": {
    "type": "text" | "readback_card" | "confirmation_card" | "payment_link",
    "payload": { /* structured data for rich UI */ }
  }
}
```

`ui_hints` lets the frontend render confirmation cards instead of plain text when appropriate.

Errors: 404 session not found, 429 rate limited.

### `POST /chat/end`
Request: `{ "session_token": "..." }`. Response 204. Marks conversation `completed`.

### `GET /voice/vapi-config`
Returns Vapi assistant configuration for a business (called by frontend before starting voice widget).

Request query: `?business_slug=dhaka-dental`

Response 200:
```json
{
  "assistant_id": "vapi-assistant-uuid",
  "server_url": "https://api.yourapp.com/api/v1/voice/webhook",
  "variable_values": {
    "business_name": "Dhaka Dental",
    "greeting": "...",
    "system_prompt": "..."
  }
}
```

### `POST /voice/webhook`
Vapi calls this on every voice turn. Non-public in practice (Vapi secret header verified), but no JWT.

Request (Vapi format):
```json
{
  "type": "function-call" | "assistant-request" | "end-of-call-report",
  "call": { "id": "...", "assistantId": "...", "customer": { "number": "..." } },
  "message": { "role": "user", "content": "...", "confidence": 0.95 }
}
```

Response 200: Vapi-format response with AI's reply text (gets TTS'd).

---

## 3. Business admin — my business (JWT: business_admin)

All endpoints below auto-filter by `business_id` from JWT. Super admin can also call these with `?business_id=` override.

### `GET /admin/business`
Returns the admin's business details.

### `PATCH /admin/business`
Updates business info.

Request (any subset):
```json
{
  "name": "...",
  "description": "...",
  "phone": "...",
  "email": "...",
  "website": "...",
  "address": "...",
  "ai_personality": "...",
  "ai_greeting": "...",
  "booking_window_days": 60,
  "cancellation_hours": 24
}
```

### `PATCH /admin/business/settings`
Updates `business_settings` table.

### `POST /admin/business/logo`
Multipart upload, image. Returns new `logo_url`.

---

## 4. Services CRUD (business_admin)

### `GET /admin/services?include_inactive=false`
Response: list of services.

### `POST /admin/services`
Request:
```json
{
  "name": "Teeth Cleaning",
  "description": "...",
  "duration_minutes": 30,
  "buffer_minutes": 10,
  "price": 80.00,
  "display_order": 0
}
```
Response 201 with created service. **Triggers embedding sync.**

### `GET /admin/services/{id}`
### `PATCH /admin/services/{id}` — triggers re-embedding if name/description changed.
### `DELETE /admin/services/{id}` — soft delete (sets `deleted_at`). Hard delete only if no bookings reference it.
### `POST /admin/services/{id}/image` — multipart upload.

---

## 5. Operating hours (business_admin)

### `GET /admin/hours`
Returns 7 rows (one per day).

### `PUT /admin/hours`
Bulk update all 7 days.

Request:
```json
{
  "hours": [
    { "day_of_week": "mon", "open_time": "09:00", "close_time": "18:00", "is_closed": false },
    ...
  ]
}
```

### `GET /admin/schedule-exceptions?from=&to=`
### `POST /admin/schedule-exceptions`
Request:
```json
{
  "exception_date": "2026-04-25",
  "is_closed": true,
  "reason": "Eid holiday"
}
```
### `DELETE /admin/schedule-exceptions/{id}`

---

## 6. FAQs (business_admin)

### `GET /admin/faqs?include_inactive=false`
### `POST /admin/faqs`
Request:
```json
{
  "question": "Do you accept insurance?",
  "answer": "Yes, we accept Blue Cross, Delta Dental, and Cigna.",
  "category": "insurance",
  "display_order": 0
}
```
**Triggers embedding sync.**
### `PATCH /admin/faqs/{id}` — re-embeds on content change.
### `DELETE /admin/faqs/{id}` — hard delete.

---

## 7. Bookings (business_admin)

### `GET /admin/bookings`
Query params: `?status=`, `?from=`, `?to=`, `?customer_id=`, `?service_id=`, `?page=`, `?limit=`.

Response:
```json
{
  "items": [
    {
      "id": "uuid",
      "customer": { "id": "...", "full_name": "...", "phone": "...", "email": "..." },
      "service": { "id": "...", "name": "...", "duration_minutes": 30 },
      "starts_at": "...",
      "ends_at": "...",
      "status": "confirmed",
      "total_amount": 80.00,
      "currency": "USD",
      "notes": "...",
      "created_at": "..."
    }
  ],
  "total": 152,
  "page": 1,
  "limit": 20
}
```

### `GET /admin/bookings/{id}`
Detailed view with payment info, source conversation link.

### `PATCH /admin/bookings/{id}`
Request (any subset):
```json
{
  "status": "confirmed" | "cancelled" | "completed" | "no_show",
  "admin_notes": "...",
  "cancelled_reason": "..."
}
```

### `POST /admin/bookings/{id}/refund`
Initiates Stripe refund.

### `POST /admin/bookings` (manual booking by admin)
Bypasses AI. Request:
```json
{
  "customer": { "full_name": "...", "phone": "...", "email": "..." },
  "service_id": "uuid",
  "starts_at": "...",
  "notes": "...",
  "skip_payment": true
}
```

---

## 8. Customers (business_admin)

### `GET /admin/customers?search=&page=&limit=`
Search by name/phone/email within the business.

### `GET /admin/customers/{id}`
Customer detail with booking history.

### `PATCH /admin/customers/{id}`
Update name, email, phone, notes.

---

## 9. Conversations + messages (business_admin, read-only)

### `GET /admin/conversations?channel=&status=&from=&to=&page=&limit=`
### `GET /admin/conversations/{id}`
Full detail including all messages.

### `GET /admin/conversations/{id}/messages`
Paginated messages.

---

## 10. Escalations (business_admin)

### `GET /admin/escalations?status=open&priority=&page=`
### `GET /admin/escalations/{id}`
Full transcript snapshot.

### `PATCH /admin/escalations/{id}`
Request:
```json
{
  "status": "in_progress" | "resolved" | "dismissed",
  "admin_notes": "..."
}
```

---

## 11. Analytics (business_admin)

### `GET /admin/analytics/overview?period=7d|30d|90d`
Response:
```json
{
  "bookings_total": 45,
  "bookings_confirmed": 38,
  "bookings_cancelled": 4,
  "revenue_total": 3420.00,
  "conversations_total": 120,
  "conversion_rate": 0.375,
  "avg_booking_value": 90.00,
  "escalation_rate": 0.05,
  "top_services": [
    { "service_id": "...", "name": "Cleaning", "count": 20, "revenue": 1600.00 }
  ]
}
```

### `GET /admin/analytics/bookings-trend?period=30d&granularity=day`
Response: array of `{ date, count, revenue }`.

### `GET /admin/analytics/conversations-trend?period=30d&granularity=day`
Response: array of `{ date, count, booked, escalated }`.

### `GET /admin/analytics/intents?period=30d`
Response: intent distribution for the period.

---

## 12. Super admin — platform level (JWT: super_admin)

### `GET /super/businesses?status=&search=&page=`
All businesses. Response includes mini-stats per business.

### `POST /super/businesses`
Creates a business + admin user (same as `/auth/register` but super admin initiated).

### `GET /super/businesses/{id}`
### `PATCH /super/businesses/{id}`
Can update status (suspend/activate).

### `DELETE /super/businesses/{id}`
Soft delete. Cascades logically (bookings remain but business hidden).

### `GET /super/analytics/overview?period=30d`
Response:
```json
{
  "businesses_total": 12,
  "businesses_active": 10,
  "bookings_total": 340,
  "revenue_total": 28400.00,
  "conversations_total": 890,
  "escalations_open": 3,
  "platform_conversion_rate": 0.38,
  "top_businesses": [
    { "business_id": "...", "name": "...", "bookings": 45, "revenue": 3400.00 }
  ]
}
```

### `GET /super/analytics/ai-performance?period=30d`
Intent classification accuracy, avg turns per booking, escalation reasons breakdown.

### `GET /super/settings`
Returns platform settings (keys visible, values masked).

### `PATCH /super/settings`
Request:
```json
{
  "key": "groq_api_key",
  "value": "gsk_..."
}
```
Encrypted server-side before storage. Response: `{ "success": true }`.

### `GET /super/audit-logs?actor_user_id=&entity_type=&from=&page=`

### `GET /super/conversations` (cross-business)
Same as business admin but no business_id filter.

### `GET /super/escalations` (cross-business)

---

## 13. Webhooks (no JWT, signature verified)

### `POST /webhooks/stripe`
Stripe event receiver. Verifies signature via `STRIPE_WEBHOOK_SECRET`.

Handles events:
- `checkout.session.completed` → mark payment succeeded, booking confirmed, send email
- `charge.refunded` → mark payment refunded
- `checkout.session.expired` → mark payment failed, release booking slot

All events stored in `webhook_events` table first (idempotency via event_id).

Response 200 always (Stripe requires 2xx).

### `POST /webhooks/vapi`
Already covered under `POST /voice/webhook`. Same endpoint, just how Vapi refers to it.

---

## 14. Utility

### `GET /health`
Response: `{ "status": "ok", "db": "ok", "version": "..." }`. For UptimeRobot.

### `GET /businesses/{slug}/public`
Public business info for the demo landing page. No auth.

Response:
```json
{
  "id": "uuid",
  "name": "Dhaka Dental",
  "slug": "dhaka-dental",
  "description": "...",
  "industry": "dental",
  "logo_url": "...",
  "address": "...",
  "hours": [...],
  "services": [...],
  "timezone": "Asia/Dhaka"
}
```

### `GET /businesses`
List of demo businesses (for the landing page selector). No auth.

---

## Auth middleware behavior

Pseudocode order for every protected route:
1. Extract JWT from `access_token` cookie
2. If missing/expired → 401
3. Decode → `{ user_id, role, business_id, exp }`
4. Load user from DB, check `is_active`, `deleted_at`
5. For `/admin/*` routes: reject if role != business_admin AND role != super_admin
6. For `/super/*` routes: reject if role != super_admin
7. Attach `request.state.user` and `request.state.business_id_filter`
8. All DB queries for business-scoped tables add `WHERE business_id = request.state.business_id_filter` unless super admin override

---

## Rate limits (per IP, via slowapi or similar)

- Auth endpoints: 10/minute
- Chat endpoints: 30/minute per session_token
- Admin endpoints: 120/minute per user
- Super admin: 300/minute
- Webhooks: no limit (signature verified instead)

---

## Pagination envelope (reused everywhere)

```json
{
  "items": [...],
  "total": 152,
  "page": 1,
  "limit": 20,
  "has_more": true
}
```

---

## OpenAPI / Swagger

FastAPI auto-generates docs at `/docs` (Swagger UI) and `/redoc`. These are **gated** in production — require super admin JWT to view. In dev, open.

---

## Endpoint count summary

- Auth: 5
- Public chat/voice: 5
- Business admin: ~40 across services, hours, FAQs, bookings, customers, conversations, escalations, analytics, settings
- Super admin: ~12
- Webhooks: 2
- Utility: 3

**Total: ~65 endpoints.** Build in phases per `05-build-phases.md` — not all at once.