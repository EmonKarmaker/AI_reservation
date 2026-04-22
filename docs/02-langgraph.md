## What this document is (plain English)

This is the **brain of the AI receptionist** — the step-by-step decision-making process the AI follows for every message, whether it came from chat or voice.

**Why it matters:** Without this document, the AI is just "one giant prompt" and it will hallucinate, double-book, miss details, and frustrate users. With this document, the AI is a **state machine**: small specialized steps, each doing one thing, glued together by plain Python code. This is the Dixon lesson applied — rules handle 85%, LLM handles 15%. Cheaper, faster, more reliable.

**How to read it:**
- **Nodes** = individual steps (like "classify intent" or "check availability"). Each node is a Python function.
- **Edges** = how the graph moves from one step to the next.
- **State** = a shared dictionary that carries data between nodes (current booking being built, user info, conversation history).
- **Intents** = what the user wants (book, cancel, ask a question, complain).
- **Sub-graphs** = smaller state machines for each intent.

**When Claude Code uses this document:** it generates the LangGraph Python code in `backend/app/ai/graph.py` — nodes, edges, state definitions — matching this blueprint exactly.

---

# LangGraph State Machine

## Core philosophy
- **Rules over LLM.** Python code handles deterministic work (DB queries, date math, validation). LLM handles only: understanding user, extracting slots, generating natural responses, and final judgment.
- **Same graph, two channels.** Chat and voice both enter the same graph. Only the input (text vs STT transcript) and output (JSON vs TTS text) layer differs.
- **State is JSON-serializable.** So we can persist it to `conversations.langgraph_state` between turns and resume.
- **Every node is testable in isolation.** No node calls another node directly — the graph does routing.

---

## State shape (Pydantic model)

```python
class AgentState(BaseModel):
    # Identity
    business_id: UUID
    conversation_id: UUID
    channel: Literal["chat", "voice"]
    
    # Current turn
    user_message: str
    stt_confidence: dict[str, float] | None  # voice only, per-word Deepgram scores
    
    # Intent routing
    current_intent: IntentType | None
    intent_confidence: float | None
    intent_history: list[IntentType]  # for detecting repeat failures
    
    # Booking slots (filled progressively)
    booking_slots: BookingSlots  # nested model, below
    
    # RAG context (when needed)
    rag_chunks: list[RagChunk]
    
    # Turn control
    turn_count: int
    consecutive_failures: int  # increments when AI fails to progress
    needs_verification: list[str]  # slot names awaiting user confirmation
    
    # Output
    response_text: str  # what AI will say/send
    response_actions: list[Action]  # side effects (create booking, send email)
    
    # Termination
    is_done: bool
    escalate: bool
    escalation_reason: str | None

class BookingSlots(BaseModel):
    service_id: UUID | None = None
    service_name_raw: str | None = None  # what user said
    service_match_confidence: float | None = None
    date: date | None = None
    time: time | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: EmailStr | None = None
    notes: str | None = None
    # per-slot confidence (0-1)
    slot_confidence: dict[str, float] = {}

class RagChunk(BaseModel):
    source_type: Literal["faq", "service", "business"]
    source_id: UUID
    content: str
    similarity: float

class Action(BaseModel):
    type: Literal["create_booking", "send_email", "create_stripe_session", 
                  "log_escalation", "update_customer"]
    payload: dict
```

---

## Intents (13 total)

```python
class IntentType(str, Enum):
    # Booking flow
    BOOK_APPOINTMENT = "book_appointment"
    CHECK_AVAILABILITY = "check_availability"
    
    # Post-booking
    CANCEL_BOOKING = "cancel_booking"
    RESCHEDULE_BOOKING = "reschedule_booking"
    CHECK_MY_BOOKING = "check_my_booking"
    
    # Informational (RAG territory)
    PRICING_INQUIRY = "pricing_inquiry"
    BUSINESS_HOURS = "business_hours"
    SERVICE_INFO = "service_info"
    GENERAL_QUESTION = "general_question"  # FAQ lookup
    
    # Meta
    GREETING = "greeting"
    GOODBYE = "goodbye"
    ESCALATE = "escalate"  # user explicitly asks for human
    UNCLEAR = "unclear"  # fall-through
```

---

## Node inventory (23 nodes)

### Entry + routing
1. `entry` — receives turn, hydrates state from DB conversation
2. `classify_intent` — LLM call, returns intent + confidence
3. `route_intent` — plain Python, sends to correct sub-graph
4. `check_frustration` — small LLM call, sentiment check. If angry → jump to escalation

### Shared booking sub-graph
5. `extract_slots` — LLM with Pydantic structured output, fills `booking_slots`
6. `validate_service` — DB + pgvector. Match `service_name_raw` to real service. If no match → ask user
7. `validate_phone` — regex + E.164 check
8. `validate_email` — regex + optional MX lookup
9. `resolve_date_time` — normalize "Tuesday" → actual date. Rejects past dates, out-of-window dates
10. `check_availability` — DB query: operating hours + existing bookings + buffer
11. `identify_missing_slots` — plain Python: what's still empty?
12. `ask_for_missing` — LLM generates natural question for missing slot(s)
13. `readback_critical_slots` — plain Python: if name/phone/email/date low-confidence or just set → generate readback
14. `llm_judge` — LLM reviews full booking + transcript, returns `{valid, issues}`
15. `explicit_confirmation` — asks user final "shall I book it?"
16. `create_booking_action` — plain Python: build idempotency key, append `create_booking` to `response_actions`
17. `create_payment_action` — append `create_stripe_session` to `response_actions`

### RAG sub-graph (for info intents)
18. `rag_search` — embed query, pgvector similarity search, top 3 chunks
19. `rag_answer` — LLM generates grounded answer from chunks

### Cancel/reschedule sub-graph
20. `lookup_booking` — ask for customer phone/email, search bookings
21. `confirm_cancel_reschedule` — explicit confirmation
22. `cancel_booking_action` / `reschedule_booking_action`

### Escalation + exit
23. `escalate_to_human` — creates escalation record, sets `escalate=True`
24. `finalize` — serializes state back to DB, builds final response

---

## Graph topology (simplified)

```
entry
  ↓
check_frustration ──(angry)──→ escalate_to_human → finalize
  ↓ (calm)
classify_intent
  ↓
route_intent ──┬──(BOOK_APPOINTMENT)──→ [booking sub-graph] → finalize
               ├──(CHECK_AVAILABILITY)──→ validate_service → check_availability → finalize
               ├──(CANCEL/RESCHEDULE)──→ [lookup sub-graph] → finalize
               ├──(INFO intents)──→ rag_search → rag_answer → finalize
               ├──(GREETING/GOODBYE)──→ small canned response → finalize
               ├──(ESCALATE)──→ escalate_to_human → finalize
               └──(UNCLEAR)──→ clarify_question → finalize
```

### Booking sub-graph detail

```
extract_slots
  ↓
validate_service ──(no match)──→ ask_for_missing(service) → finalize
  ↓ (matched, high conf)
validate_phone ──(invalid)──→ ask_for_missing(phone) → finalize
  ↓
validate_email ──(invalid)──→ ask_for_missing(email) → finalize
  ↓
resolve_date_time ──(invalid)──→ ask_for_missing(date/time) → finalize
  ↓
check_availability ──(unavailable)──→ suggest_alternatives → finalize
  ↓ (available)
identify_missing_slots ──(missing)──→ ask_for_missing → finalize
  ↓ (complete)
readback_critical_slots ──(needs readback)──→ finalize with readback
  ↓ (readback done previously, user confirmed)
llm_judge ──(issues found)──→ ask clarifying question → finalize
  ↓ (valid)
explicit_confirmation ──(not confirmed yet)──→ finalize with confirm prompt
  ↓ (user said yes)
create_booking_action → create_payment_action → finalize
```

---

## The 7-layer verification mapping

| Layer | Where it lives in graph |
|---|---|
| 1. Pydantic structured output | `extract_slots` (LLM call uses Pydantic schema) |
| 2. Reality checks (DB/regex) | `validate_service`, `validate_phone`, `validate_email`, `resolve_date_time`, `check_availability` |
| 3. Confidence gating | In `identify_missing_slots`: low-confidence slots added to `needs_verification` |
| 4. Critical-slot readback | `readback_critical_slots` node |
| 5. LLM-as-judge | `llm_judge` node (second opinion before commit) |
| 6. Explicit confirmation | `explicit_confirmation` node |
| 7. Idempotency + soft commit | `create_booking_action` builds idempotency key; booking saved as `pending_payment` until Stripe webhook fires |

---

## Escalation triggers (consolidated)

Escalation fires from any of these:

1. **Explicit user ask.** `classify_intent` returns `ESCALATE`.
2. **Frustration detected.** `check_frustration` returns angry/frustrated.
3. **Repeated failure.** `consecutive_failures >= 3` (same intent, no progress).
4. **Low intent confidence.** `intent_confidence < 0.5` on two consecutive turns.
5. **Complaint/refund intent.** Certain intents auto-escalate (if added later).
6. **LLM judge rejects 2+ times.** Booking won't validate even after re-extraction.

Escalation priority:
- **High:** explicit frustration, complaint
- **Medium:** explicit ask for human, repeated failure
- **Low:** low confidence, unclear

---

## Channel-specific differences

| Concern | Chat | Voice |
|---|---|---|
| Input | text | Deepgram STT → text |
| Confidence source | LLM self-report (Pydantic field) | Deepgram per-word scores |
| Readback format | visual card with edit buttons | spoken phonetic ("E-M-O-N") |
| Explicit confirmation | button click ("Confirm" / "Change") | verbal "yes" / "no" |
| Response style | can use markdown, lists | short sentences, no markdown |
| Repair flow | user edits form | dedicated `repair` node listening for "no", "wrong", "I said..." |
| Escalation | inline message | AI says it + email sent |
| Max response length | ~300 chars preferred | ~150 chars preferred (TTS cost + listenability) |

---

## Prompts (outlines, not final text)

### System prompt (shared, channel-injected)
```
You are {business.ai_greeting_name or 'the AI receptionist'} for {business.name}, 
a {business.industry} business. Help customers book appointments, answer questions, 
and identify when they need a human.

BUSINESS CONTEXT:
- Timezone: {business.timezone}
- Hours: {formatted operating hours}
- Services: {top 10 services with prices}
- Cancellation policy: {business.cancellation_hours}h notice

RULES:
- Never invent services, prices, or hours — only use what's provided
- If unsure, say so and offer to escalate
- Keep responses {'short, no markdown' if channel='voice' else 'concise'}
- Ask one question at a time
- Always use 24-hour clock internally, convert for display
```

### Intent classifier prompt
```
Classify the user's intent into exactly one of: {list of 13 intents}.
Return JSON: {"intent": "...", "confidence": 0.0-1.0, "reasoning": "..."}
```

### Slot extractor prompt (Pydantic-enforced output)
```
Extract booking details from the user's message AND prior context.
Return the BookingSlots schema. For each field, also provide confidence 0-1.
Only fill fields you're confident about. Leave others null.
```

### LLM-as-judge prompt
```
Review this booking against the full conversation. Is the extracted data 
correct and complete? Any red flags?
Return: {"valid": bool, "issues": ["..."], "severity": "low|medium|high"}
```

---

## Performance targets

- Classify intent: <500ms (small Groq model, Llama 3.1 8B)
- Extract slots: <1s (Groq Llama 3.3 70B with structured output)
- Reality checks: <50ms (DB + regex, plain Python)
- LLM-as-judge: <800ms (Groq)
- Full turn (chat): <2s end-to-end
- Full turn (voice): <1.5s (latency-critical)

Cache what's cacheable:
- System prompt with business context → cached per business, rebuilt on business/service update
- Embeddings → computed once on write, never on read

---

## Testing strategy (for later)

- Unit tests per node (mock LLM, mock DB)
- Integration tests per sub-graph (happy path, each failure mode)
- End-to-end tests for top 10 conversation scripts (booking, cancel, FAQ, escalation)
- Evaluation set: 50 real-ish transcripts scored by a second LLM (correctness, tone, efficiency)

---

## File layout (for backend)

```
backend/app/ai/
├── graph.py              # builds the LangGraph
├── state.py              # AgentState, BookingSlots, enums
├── nodes/
│   ├── __init__.py
│   ├── entry.py
│   ├── routing.py        # classify_intent, route_intent, check_frustration
│   ├── booking.py        # all booking sub-graph nodes
│   ├── rag.py            # rag_search, rag_answer
│   ├── cancel.py         # lookup, cancel, reschedule
│   ├── escalation.py     # escalate_to_human
│   └── finalize.py
├── prompts/
│   ├── system.py
│   ├── intent.py
│   ├── extract.py
│   └── judge.py
├── llm.py                # Groq client wrapper with retries
├── embeddings.py         # MiniLM wrapper, pgvector helpers
└── intents.py            # IntentType enum
```

---

## Open decisions (flag for later, not blocking)

- **Streaming responses in chat?** Yes for v2, skip for v1 (simpler).
- **Function calling vs structured output?** Use structured output — more reliable with Groq.
- **Persist full LangGraph checkpoints or just final state?** Just final state in `conversations.langgraph_state` for v1.
- **Multi-turn intent switching?** If user pivots mid-booking ("actually forget that, what are your hours?") — supported via re-classify on every turn, state retains booking_slots in case they come back.