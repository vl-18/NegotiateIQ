# NegotiateIQ — End-to-End Pipeline

**What this document covers:** The complete flow from a user clicking "Start Negotiation" to seeing agent messages appear in the chat, and everything in between. Read this if you want to understand how all the pieces connect or if you are about to change any part of the system.

---

## System Map

```
┌────────────────────────────────────────────────────────────────┐
│                     Browser — Buyer UI (:5173)                 │
│  Product grid → Setup panel → Live chat (SSE-driven)           │
│  └─ EventSource (SSE)  ←─────────────────────────────────┐    │
│  └─ fetch() POST calls ──────────────────────────┐        │    │
└─────────────────────────────────────────────────────── ── │────┘
                                                    │        │
┌────────────────────────────────────────────────────────────────┐
│                  Browser — Merchant UI (:5174)                  │
│  Dashboard · Products · Config (editable) · Metrics tab        │
│  └─ fetch() polling every 10 s → GET /metrics                  │
└──────────────────────────────────────────────┬──────────────── ┘
                                               │
                              HTTP (REST + SSE)│
                                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Cloud Run — FastAPI Orchestrator (:8001)           │
│                             main.py                                  │
│                                                                      │
│  POST /session/start        → creates session in Firestore           │
│  POST /session/{id}/turn    → runs one full turn (shopping+merchant) │
│  GET  /session/{id}/stream  → SSE stream (EventSource)               │
│  GET  /session/{id}/status  → current state                          │
│  GET  /sessions             → list all sessions (merchant dashboard) │
│  GET  /products             → list products (merchant config)        │
│  PUT  /products/{sku}       → update product pricing                 │
│  GET  /config               → merchant agent config (name/role)      │
│  PUT  /config               → update agent identity                  │
│  GET  /metrics              → in-memory LLM call metrics             │
│  GET  /health                                                        │
│                                                                      │
│  In-memory: _sse_queues { session_id → asyncio.Queue }               │
│  In-memory: metrics store  (resets on server restart)                │
└──────┬────────────────────┬─────────────────┬──────────────────┬────┘
       │                    │                 │                  │
       ▼                    ▼                 ▼                  ▼
┌────────────┐   ┌──────────────────┐  ┌───────────────┐  ┌──────────┐
│  Firestore │   │  Merchant Agent  │  │  Shopping     │  │ In-Mem   │
│            │   │  merchant.py     │  │  Agent        │  │ Metrics  │
│  products/ │   │                  │  │  shopping.py  │  │ Store    │
│  sessions/ │   │  Rules engine    │  │               │  │          │
│  sessions/ │   │  + Gemini prose  │  │  Safety pipe  │  │ metrics  │
│  {id}/     │   │  (gemini-3.8)    │  │  + Gemini     │  │ .py      │
│  llm_calls │   └──────────────────┘  │  (gemini-3.8) │  └──────────┘
└────────────┘                         └───────────────┘
```

---

## Phase 1 — Starting a Session

### Trigger
User selects a product + mode (AI/Human) + persona (AI only) and clicks **Start Negotiation**.

### What happens

```
Browser
  └─ POST /session/start
       { product_sku, mode, persona }
       ↓
main.py → start_session()
  1. Validates: AI mode requires persona
  2. get_product(sku) → Firestore lookup (or dry-run in-memory dict)
     → Raises 404 if SKU not found
  3. Creates NegotiationSession object:
       session_id = new UUID
       mode, persona, product_sku
       status = "active"
       turns = []
  4. create_session(session) → writes to Firestore (or in-memory in dry-run)
  5. Returns { session_id, mode, persona, status }
       ↓
Browser
  └─ Stores session_id
  └─ Opens EventSource to GET /session/{id}/stream
  └─ Fires POST /session/{id}/turn to start first AI turn (AI mode only)
```

**Key file:** `orchestrator/src/main.py` → `start_session()`  
**Key file:** `orchestrator/src/firebase_db.py` → `create_session()`

---

## Phase 2 — Opening the SSE Stream

### Trigger
Immediately after `start_session()` responds, the browser calls `openStream(sessionId, onEvent, onClose)`.

### What happens

```
Browser
  └─ new EventSource("/session/{id}/stream")
       ↓
main.py → stream_session()
  1. get_session(id) → confirms session exists (404 if not)
  2. _get_queue(session_id) → returns (or creates) asyncio.Queue for this session
  3. Returns StreamingResponse(event_generator(), media_type="text/event-stream")

event_generator() (async generator, runs until sentinel):
  loop:
    payload = await queue.get()    ← blocks until something is put in the queue
    if payload is None:            ← None is the close sentinel
        yield "event: close\ndata: {}\n\n"
        break
    yield f"data: {payload}\n\n"  ← standard SSE format

Browser EventSource:
  es.onmessage = (e) → parse JSON → onEvent(event)
  es.addEventListener("close", ...) → es.close(); onClose() → show DealSummary
```

The stream stays open for the entire session. Every turn pushed to the queue by `run_turn()` appears in the browser as it arrives — no polling, no refresh.

**Key file:** `orchestrator/src/main.py` → `stream_session()`, `_get_queue()`, `event_generator()`  
**Key file:** `ui/src/api.js` → `openStream()`

---

## Phase 3 — Running a Turn

One HTTP call drives two agent responses (shopping + merchant) and delivers both to the browser via SSE.

### Trigger
- **AI mode:** browser fires `POST /session/{id}/turn {}` immediately after opening the stream. After each HTTP response it fires again — chaining turns until session ends.
- **Human mode:** browser fires `POST /session/{id}/turn { message_text: "..." }` only when the user clicks Send.

### What happens inside `run_turn()`

```
POST /session/{id}/turn { message_text? }
  ↓
main.py → run_turn()

  ── Guard checks ──────────────────────────────────────────────
  1. get_session(id) → fetch from Firestore (404 if missing)
  2. session.status != ACTIVE → 409 (session already finished)
  3. get_product(session.product_sku) → fetch product
  4. sm = StateMachine(session)
  5. metrics_offset = _metrics.total_call_count()   ← snapshot for this turn's calls

  ── Shopping turn ──────────────────────────────────────────────
  6. shopping_turn(session, product, sm, message_text?)
     → AI mode: required_action() → Gemini (with retry) → clamp → fallback
     → Human mode: regex parse typed text → A2A terms
     → Returns shopping_msg (A2AMessage)
     → state_machine.apply(shopping_msg) called inside shopping.py

  7. _push_event(session_id, _msg_summary(shopping_msg))
     → Puts { type:"turn", turn, sender, intent, display_text, proposed_terms }
        into the asyncio.Queue for this session
     → SSE generator picks it up → user sees the message in chat immediately

  ── Check if buyer ended the session ──────────────────────────
  8. If session.status != ACTIVE (buyer ACCEPT or REJECT):
       new_calls = _metrics.calls_since(metrics_offset, session_id)
       await append_session_metrics(session_id, new_calls)  ← persist to Firestore
       update_session(session) → Firestore
       _push_event(session_id, { type:"status", status, final_deal })
       _close_stream(session_id) → None sentinel
       return _turn_response(shopping_msg, None, session)

  ── Merchant turn ──────────────────────────────────────────────
  9. Check if merchant already issued FINAL_OFFER on previous turn:
     If shopping counter-offers after FINAL_OFFER → force REJECT override
     (prevents buyer from gaming the final-offer boundary)

 10. merchant_turn(session, product, sm, shopping_msg)
     → Hard reject if buyer price < price_floor
     → Rules engine: apply_rules() → price, delivery, voucher
     → FINAL_OFFER: static firm message (no Gemini)
     → COUNTER_OFFER: Gemini call (with retry) → display_text
     → Returns merchant_msg (A2AMessage)

 11. _push_event(session_id, _msg_summary(merchant_msg))
     → Merchant message appears in browser chat

 12. new_calls = _metrics.calls_since(metrics_offset, session_id)
     await append_session_metrics(session_id, new_calls)  ← persist metrics

 13. update_session(session) → Firestore (full session persisted)

  ── Check if session ended after merchant turn ─────────────────
 14. If session.status != ACTIVE (REJECT, FINAL_OFFER resolution, or EXPIRED):
       _push_event(session_id, { type:"status", status, final_deal })
       _close_stream(session_id) → None sentinel → stream closes

 15. Return { shopping_turn, merchant_turn, session_status, turn_count, final_deal }
     (HTTP response — UI uses this as a backup if SSE events were missed)
```

**Key file:** `orchestrator/src/main.py` → `run_turn()`

---

## Phase 3a — Shopping Turn Detail

### AI mode

```
required_action(session, persona_spec)
  → If turn limit, stall limit, or merchant-rejected: force ACCEPT or REJECT
  → Bypasses Gemini entirely

_build_context(session, product, persona_spec)
  → Structured JSON: product, persona limits, full turn history

Retry loop (up to 2 attempts):
  call_gemini_shopping(system_prompt, context, schema=BuyerReply, timeout_s=10)
    → Gemini 3.8 Flash with persona system prompt
    → Returns (raw_text, metadata)
  Parse BuyerReply from raw_text
  _intent_problem() → check intent is valid; if not, inject corrective feedback and retry
  clamp_counter(terms, persona_spec, session)
    → Hard limits: walk-away, never-raise-own-offer, delivery cap, qty range
    → If something clamped: source becomes "llm_repaired"
  Break on success OR on 429 RESOURCE_EXHAUSTED (quota; retry won't help)

On failure: fallback_proposal(session, persona_spec)
  → Deterministic paced move (no Gemini)
  → source = "fallback" (or "dry_run" if DRY_RUN=true)

state_machine.apply(msg)
  → Appends turn to session.turns
  → If ACCEPT: session.status=ACCEPTED, session.final_deal set
  → If REJECT: session.status=REJECTED
  → Validates sender alternation; checks max turns
```

### Human mode

```
Regex extracts: price, quantity, delivery_days, voucher_code from message_text
Detects intent: ACCEPT | REJECT | COUNTER_OFFER | QUERY (fallback)
Assembles A2AMessage { sender=HUMAN, intent=detected, display_text=message_text, proposed_terms=extracted }
state_machine.apply(msg)
```

---

## Phase 3b — Merchant Turn Detail

```
merchant_turn(session, product, state_machine, buyer_msg)
  ↓
  should_reject(product, buyer_terms)?
    → True if buyer_price < product.price_floor
    → Emit REJECT immediately — no rules engine, no Gemini
    → state_machine.apply(reject_msg) → session.status=REJECTED
    → return

  apply_rules(product, buyer_terms, previous_merchant_price)
    → Start price = min(prev_merchant_offer, list_price)
    → Apply bulk discount for buyer's quantity
    → If buyer pushed lower: split the difference, clamp to price_floor
    → offered_price ≤ price_floor + $0.50 → Intent.FINAL_OFFER
    → Delivery: standard (5d) by default; express (2d) if buyer requested < 5d
    → Voucher "LOYALTY10" on FINAL_OFFER if product.vouchers_eligible
    → Returns (ProposedTerms, Intent)

  If FINAL_OFFER:
    → Static firm message — no Gemini call (static message is unambiguous)

  If COUNTER_OFFER:
    → build_negotiation_context(session, product, config)
       Appends: "Your next offer (already decided): $X/unit, qty Y, Z-day delivery."
    → Retry loop (up to 2 attempts):
         call_merchant_agent(context, session_id=session.session_id)
         Break on success OR on 429 RESOURCE_EXHAUSTED
         On failure: log.warning(...) then static fallback display_text
    → display_text + reasoning from Gemini (or static fallback)

  Assemble A2AMessage { sender=MERCHANT_AGENT, terms, display_text, reasoning }
  state_machine.apply(msg)
  return msg
```

---

## Phase 4 — Session End

A session ends in one of five ways:

| Trigger | Who | `session.status` | `final_deal` |
|---|---|---|---|
| Buyer sends ACCEPT | Shopping agent / human | `ACCEPTED` | Merchant's last terms |
| Merchant sends REJECT | Merchant agent | `REJECTED` | `null` |
| Buyer sends REJECT | Shopping agent (walk-away) | `REJECTED` | `null` |
| Buyer counters after FINAL_OFFER | Force-rejected by `run_turn()` | `REJECTED` | `null` |
| Turn limit reached | State machine | `EXPIRED` | Last merchant terms |

In all cases:
1. `append_session_metrics()` persists LLM call records to Firestore subcollection
2. `update_session()` saves final state to Firestore
3. `_push_event(session_id, { type:"status", status, final_deal })` is sent to SSE queue
4. `_close_stream(session_id)` puts `None` sentinel in queue
5. SSE generator receives `None` → yields `"event: close\ndata: {}\n\n"` → closes
6. Browser `EventSource` receives `"event: close"` → calls `onClose()` → chat shows `DealSummary`

---

## Metrics Pipeline

```
Every Gemini call (merchant or shopping):
  └─ gemini.py calls _metrics.record_call(agent, model, latency_ms, tokens, session_id)
      → Appends to in-memory list in metrics.py
      → Even on failure: latency recorded, tokens are None

After each turn (run_turn in main.py):
  └─ _metrics.calls_since(offset, session_id) → new records since turn started
  └─ append_session_metrics(session_id, new_calls) → Firestore subcollection
      → sessions/{session_id}/llm_calls/{auto-id}
      → No-op in FIREBASE_DRY_RUN=true mode

GET /metrics:
  └─ Returns _metrics.get_metrics():
      { calls: last 100, summary: {total_calls, avg/p50/p95/max latency, tokens},
        by_agent: { merchant: {...}, shopping: {...} } }
  └─ Consumed by MerchantMetricsScreen.jsx — auto-refreshes every 10 s

DRY_RUN=true:
  └─ Both agents record simulated metrics (random latency + random tokens)
  └─ Dashboard always shows data in demo mode
```

---

## State Machine Rules

The `StateMachine` (`state_machine.py`) enforces these invariants on every `apply()` call:

| Rule | What it enforces |
|---|---|
| Session must be active | Blocks any turn on a finished session (raises `NegotiationError`) |
| Alternation | Shopping side must go first; then strict shopping → merchant → shopping → ... |
| Max turns | `SAFETY_MAX_TURNS = 50` absolute backstop (bug guard only; personas have lower per-persona limits) |
| ACCEPT captures deal | Sets `session.final_deal` from the accepting message's terms or last merchant offer |
| REJECT marks rejected | Sets `session.status = REJECTED` |

---

## Data Persistence

All persistence goes through `firebase_db.py`. In dry-run mode (`DRY_RUN=true` and/or `FIREBASE_DRY_RUN=true`) the same function signatures are backed by in-memory Python dicts.

| Function | Firestore operation | When called |
|---|---|---|
| `get_product(sku)` | `products/{sku}` GET | Every turn (product fetched fresh) |
| `create_session(session)` | `sessions/{id}` SET | Once at session start |
| `get_session(id)` | `sessions/{id}` GET | Start of every turn + stream open |
| `update_session(session)` | `sessions/{id}` SET (merge) | After each complete turn |
| `list_sessions()` | `sessions/` stream | Merchant dashboard |
| `list_products()` | `products/` stream | Merchant config screen |
| `update_product(sku, updates)` | `products/{sku}` SET (merge) | Merchant config save |
| `get_merchant_config()` | `config/merchant` GET | Each merchant turn (via merchant.py) |
| `save_merchant_config(updates)` | `config/merchant` SET (merge) | Merchant config save |
| `append_session_metrics(id, calls)` | `sessions/{id}/llm_calls/` ADD (per call) | After each turn |

---

## File Map

| File | Responsibility |
|---|---|
| `orchestrator/src/main.py` | FastAPI endpoints, SSE queue, orchestration of turn flow, metrics persistence |
| `orchestrator/src/models.py` | All Pydantic data shapes: `A2AMessage`, `NegotiationSession`, enums |
| `orchestrator/src/state_machine.py` | Turn lifecycle, alternation enforcement, expiry logic |
| `orchestrator/src/merchant.py` | Merchant rules engine + Gemini prose generation (with retry + 429 detection) |
| `orchestrator/src/shopping.py` | Shopping agent safety pipeline: required_action → Gemini retry → clamp → fallback |
| `orchestrator/src/gemini.py` | Async Gemini SDK wrapper, prompt loading, JSON parsing, metrics recording |
| `orchestrator/src/firebase_db.py` | Firestore CRUD + dry-run in-memory fallback + session metrics subcollection |
| `orchestrator/src/metrics.py` | In-memory LLM call store: record_call(), get_metrics(), calls_since() |
| `orchestrator/prompts/merchant_system.txt` | Merchant agent system prompt (personality + output format) |
| `orchestrator/prompts/persona_*.txt` | Buyer persona system prompts (one per persona) |
| `ui/src/api.js` | Browser-side: startSession, runTurn, openStream, fetchMetrics |
| `ui/src/App.jsx` | Buyer root layout: Products → Negotiate → DealSummary |
| `ui/src/MerchantApp.jsx` | Merchant root layout: Dashboard · Products · Negotiations · Config · Metrics |
| `ui/src/components/NegotiationScreen.jsx` | Setup panel + live chat (SSE → TurnMessage) |
| `ui/src/components/TurnMessage.jsx` | Single message bubble (intent badge, proposed terms) |
| `ui/src/components/DealSummary.jsx` | Outcome card shown when session ends |
| `ui/src/components/MerchantConfigScreen.jsx` | Product + agent identity editing (calls PUT /products, PUT /config) |
| `ui/src/components/MerchantMetricsScreen.jsx` | LLM metrics dashboard: KPI tiles, sparkline, calls table |
| `ui/src/components/ProductsScreen.jsx` | Google Shopping-style product grid with search + filters (buyer) |

---

## How to Trace a Bug

**"The merchant offered a wrong price"**  
→ Add a `print()` in `apply_rules()` in `merchant.py` after the `offered_price` calculation to log the computed value.

**"The session didn't end when the buyer accepted"**  
→ Check `state_machine.apply()` — verify `msg.intent == Intent.ACCEPT` is being matched and `session.status` is set.

**"SSE messages aren't appearing in the browser"**  
→ Check that `_push_event()` is called in `run_turn()` after each agent step. Confirm the browser EventSource is open before the first turn fires (DevTools → Network → EventStream).

**"Session expired but the UI didn't show it"**  
→ Verify `_push_event(session_id, { type:"status", ... })` and `_close_stream()` are called. Check the browser handles `"event: close"` in `openStream()`.

**"Metrics tab shows no data"**  
→ Confirm the backend was restarted after the latest code changes (metrics store is in-memory). Run a negotiation turn — metrics appear after the first Gemini call. If Gemini quota is exhausted (429), failed calls still record latency; token columns show "—".

**"A new persona isn't working"**  
→ Confirm: prompt file exists in `orchestrator/prompts/`, `PersonaSpec` added to `PERSONAS` dict in `shopping.py`, persona key mapped in `PERSONA_PROMPT_FILES` in `gemini.py`, entry in `PERSONAS` array in `ui/src/components/NegotiationScreen.jsx`.
