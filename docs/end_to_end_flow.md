# NegotiateIQ — End-to-End Flow (All Branches)

> **Audience:** Developers who need to trace every code path through the system.
> **Last updated:** 2026-10-11

---

## 1. Overview

NegotiateIQ is a multi-agent price-negotiation platform built on the A2A (Agent-to-Agent) protocol. A buyer-side Shopping Agent (AI or Human) negotiates with a rule-governed Merchant Agent over a product's price, quantity, delivery terms, and optional vouchers. The FastAPI orchestrator (port 8001) owns session lifecycle, sequencing, and persistence; two React+Vite UIs serve the buyer (port 5173) and merchant (port 5174). Gemini 3.5 Flash powers both AI agents, with all hard limits enforced by deterministic rules engines so Gemini controls only prose and negotiation judgment—never numbers. Real-time turn-by-turn updates are delivered to the browser via Server-Sent Events (SSE). Sessions transition through the status chain `active → accepted | rejected | expired`, with Firestore (or an in-memory dry-run fallback) storing the session document and LLM call metrics in a subcollection. Every code path—AI auto-play, human typing, LLM quota failure, force-reject override, stall detection, and dry-run simulation—converges on the same A2AMessage shape so the rest of the system is unaffected by which path ran.

---

## 2. Session Start Flow

```mermaid
flowchart TD
    A([Buyer UI]) -->|POST /session/start\nmode, persona, product_sku| B{Validate request}
    B -->|mode=ai AND no persona| ERR1([HTTP 400 — persona required])
    B -->|product_sku not found| ERR2([HTTP 404 — product not found])
    B -->|valid| C[Create NegotiationSession\nstatus=active\nturn_count=0]
    C --> D[create_session — Firestore / in-memory]
    D --> E([Return 201\nsession_id, mode, persona, status])
    E --> F([Browser opens SSE stream\nGET /session/id/stream])
    F --> G{mode?}
    G -->|AI| H[Browser POSTs first turn\nPOST /session/id/turn\nno message_text needed]
    G -->|Human| I([Wait for user to type\nand submit message])
    H --> J([run_turn executes])
    I --> J
```

**Key implementation notes:**
- `StartSessionRequest` is validated by `main.py:start_session()`.
- Persona is required only in AI mode; it is `None` in Human mode.
- The SSE stream (`GET /session/{id}/stream`) uses an `asyncio.Queue` keyed by `session_id`. The queue is created lazily on first access so both the stream opener and the turn runner share the same queue instance.
- In AI mode the browser fires the first `POST /session/{id}/turn` immediately after opening the SSE stream—there is no explicit trigger on the server side.

---

## 3. Full Turn Execution Flow

`POST /session/{session_id}/turn` → `main.py:run_turn()`

```mermaid
flowchart TD
    A([POST /session/id/turn]) --> B[Load session from Firestore]
    B --> C{session.status == ACTIVE?}
    C -->|no| ERR([HTTP 409 — session already ended])
    C -->|yes| D[Load product from Firestore]
    D --> E[Create StateMachine]
    E --> F[Snapshot metrics offset\nmetrics.total_call_count]

    F --> G[shopping_turn\nAI or Human path]
    G --> H{Parse / LLM error?}
    H -->|ValueError| ERR2([HTTP 400])
    H -->|NegotiationError| ERR3([HTTP 409])
    H -->|ok| I[shopping_msg returned]

    I --> J{Force-reject check:\nDid merchant previously send\nFINAL_OFFER AND shopping\nreply is not ACCEPT/REJECT?}
    J -->|yes — override| K[Replace shopping_msg with REJECT\nset session.status = rejected]
    J -->|no| L{session.status still ACTIVE?}
    K --> M[Push shopping event to SSE queue]
    L -->|no — buyer accepted or rejected| M
    L -->|yes| N[Push shopping event to SSE queue]

    M --> O[update_session Firestore]
    O --> P[Push status event to SSE queue]
    P --> Q[_close_stream — put None sentinel]
    Q --> R[calls_since offset → append_session_metrics Firestore]
    R --> S([Return HTTP response\nno merchant_turn])

    N --> T[merchant_turn]
    T --> U[Push merchant event to SSE queue]
    U --> V[update_session Firestore]
    V --> W{session.status still ACTIVE?}
    W -->|no| X[Push status event\n_close_stream]
    W -->|yes| Y[Skip close]
    X --> Z[calls_since offset → append_session_metrics]
    Y --> Z
    Z --> AA([Return HTTP response\nwith both turns])
```

**Source references:** `main.py` lines 427–521.

---

## 4. Shopping Agent — AI Mode Flow

`shopping.py:shopping_turn_ai()`

```mermaid
flowchart TD
    A([shopping_turn_ai called]) --> B[Resolve PersonaSpec from session.persona]
    B --> C[Build NegotiationState from session history]
    C --> D[required_action — code decides the mandatory move]

    D --> E{Result?}
    E -->|reject — merchant walked away| FRC([force reject path])
    E -->|accept — terms acceptable\nor stall/turn limit hit| FAC([force accept path])
    E -->|counter — normal mid-game| CNT([counter path])

    FRC --> DRY
    FAC --> DRY
    CNT --> DRY

    DRY{is_dry_run?}
    DRY -->|yes| SIM[Record simulated metric\nlatency 500–2200ms\ntokens 300–800 prompt\n50–180 output\nsource=dry_run]
    DRY -->|no| LLM1

    SIM --> FIN

    LLM1[Attempt 1 — call_gemini_shopping\nsystem=persona_prompt\nuser=JSON context] --> R1{Result?}
    R1 -->|parse ok AND intent ok| GOOD[reply accepted\nsource=llm]
    R1 -->|429 RESOURCE_EXHAUSTED| QUOTA[Break immediately\nno retry\nsource=fallback]
    R1 -->|parse error or wrong intent| FB1[Set feedback string\nnotes.append error detail]

    FB1 --> LLM2[Attempt 2 — call_gemini_shopping\nwith _correction field in context]
    LLM2 --> R2{Result?}
    R2 -->|parse ok AND intent ok| GOOD2[reply accepted\nsource=llm]
    R2 -->|any failure| FALLBACK[Both attempts failed\nsource=fallback\nuse fallback_proposal — deterministic]

    GOOD --> CLAMP
    GOOD2 --> CLAMP
    FALLBACK --> FIN
    QUOTA --> FIN

    CLAMP[clamp_counter — apply hard limits\nwalk-away floor cap\ndelivery day cap\nqty bracket enforcement\nnever bid above merchant\nnever lower own prior offer] --> REPAIR{Any repairs?}
    REPAIR -->|yes| REWRITE[source=llm_repaired\nswap dollar amount in prose if price changed\nclear prose if qty or delivery changed]
    REPAIR -->|no| FIN

    REWRITE --> FIN
    FIN[_finalize — produce A2A envelope\noverride source if forced terminal\nfallback prose if reasoning empty] --> APPLY[state_machine.apply msg\nupdate session.turns\nupdate session.status]
    APPLY --> RET([Return A2AMessage])
```

**Key source references:**
- `required_action()` — `shopping.py` lines 382–403
- LLM retry loop — `shopping.py` lines 821–855
- `clamp_counter()` — `shopping.py` lines 416–466
- `fallback_proposal()` — `shopping.py` lines 469–496
- `_finalize()` — `shopping.py` lines 581–670

**Source field values:** `llm` | `llm_repaired` | `override` | `fallback` | `dry_run`

**Turn/stall limits by persona:**

| Persona | Turn limit | Stall limit |
|---|---|---|
| budget_shopper | 8 | 3 |
| premium_buyer | 5 | 2 |
| bulk_purchaser | 6 | 2 |

---

## 5. Shopping Agent — Human Mode Flow

`shopping.py:shopping_turn_human()`

```mermaid
flowchart TD
    A([User types message\nin Buyer UI]) --> B[POST /session/id/turn\nmessage_text = typed string]
    B --> C[shopping_turn routes to\nshopping_turn_human]

    C --> D[Regex extraction pass]
    D --> D1{_RX_PRICE matches?} -->|yes| E1[found unit_price = float]
    D --> D2{_RX_QTY matches?} -->|yes| E2[found quantity = int]
    D --> D3{next-day/overnight?} -->|yes| E3[found delivery_days = 1]
    D --> D4{express?} -->|yes| E4[found delivery_days = 2]
    D --> D5{_RX_DAYS matches?} -->|yes| E5[found delivery_days = int]
    D --> D6{_RX_VOUCHER matches?} -->|yes| E6[found voucher_requested = LOYALTY10]

    E1 & E2 & E3 & E4 & E5 & E6 --> INT[Intent detection]

    INT --> IA{_RX_ACCEPT matches\nAND merchant has spoken?} -->|yes| ACC[intent = ACCEPT]
    INT --> IR{_RX_REJECT matches\nAND merchant has spoken?} -->|yes| REJ[intent = REJECT]
    INT --> IF{any field found?} -->|yes| CNT[intent = COUNTER_OFFER]
    INT --> ELSE[intent = QUERY]

    ACC & REJ --> ECHO[proposed_terms = copy of\nlast merchant turn's terms]
    CNT & ELSE --> BUILD[proposed_terms from found dict]

    ECHO & BUILD --> WRAP[Wrap in A2AMessage\nsender=HUMAN\ndisplay_text = raw typed text]
    WRAP --> SM[state_machine.apply msg]
    SM --> RET([Return A2AMessage\nidentical shape to AI path])
```

**Key point:** Human and AI paths produce identical `A2AMessage` shapes. The Merchant Agent cannot distinguish which path ran.

---

## 6. Merchant Agent Flow

`merchant.py:merchant_turn()`

```mermaid
flowchart TD
    A([merchant_turn called]) --> B{should_reject?\nbuyer_price < price_floor}
    B -->|yes| HARDREJ[Static rejection message\nno Gemini call\nintent = REJECT\nstate_machine.apply\nsession.status = rejected]
    B -->|no| RULES

    HARDREJ --> RET([Return A2AMessage])

    RULES[apply_rules — pure rules engine] --> R1[Base price = min of\nlast merchant offer, bulk-discounted list price]
    R1 --> R2{buyer_price < offered_price?}
    R2 -->|yes| R3[Split the difference\nnew = offered + buyer / 2\nclamped to price_floor]
    R2 -->|no| R4[offered = max offered price_floor]
    R3 & R4 --> R5{offered - price_floor\n<= FINAL_OFFER_EPSILON\n0.50?}
    R5 -->|yes — at floor| FINAL[intent = FINAL_OFFER\noffered_price = price_floor exactly\nvoucher = LOYALTY10 if eligible]
    R5 -->|no| COUNTER[intent = COUNTER_OFFER]

    FINAL --> STATICMSG[Static firm message\nno Gemini call\ndisplay_text hardcoded]
    COUNTER --> GEM1[Get merchant config\nBuild context text\nCall call_merchant_agent Attempt 1]
    GEM1 --> G1{Result?}
    G1 -->|ok| PROSE[display_text = Gemini prose\nreasoning = Gemini reasoning]
    G1 -->|429 RESOURCE_EXHAUSTED| GFALLBACK[Static fallback text\nbreak immediately]
    G1 -->|other error| RETRY[Attempt 2]
    RETRY --> G2{Result?}
    G2 -->|ok| PROSE
    G2 -->|any failure| GFALLBACK

    STATICMSG & PROSE & GFALLBACK --> BUILD[Build A2AMessage\nterms from rules engine only\ndisplay_text from above path\nstate_machine.apply]
    BUILD --> RET
```

**Key rules engine facts:**
- `FINAL_OFFER_EPSILON = 0.50` (defined in `merchant.py` line 62)
- Delivery: defaults to 5 days; switches to 2 days if buyer requested faster than 5 days
- Voucher `LOYALTY10` is added only on `FINAL_OFFER` if `product.vouchers_eligible` is true
- Gemini controls only prose; `terms` always come from `apply_rules()`

---

## 7. Session End Scenarios

| # | Trigger | Who triggers | `session.status` | `final_deal` populated | What the user sees |
|---|---|---|---|---|---|
| 1 | Shopping Agent (AI or Human) sends `ACCEPT` | Buyer side | `accepted` | Yes — last merchant terms copied to `final_deal` | DealSummary card with agreed price, qty, delivery, optional voucher |
| 2 | Shopping Agent (AI or Human) sends `REJECT` | Buyer side | `rejected` | No | "Negotiation closed" message in NegotiationScreen |
| 3 | Merchant Agent sends `REJECT` (buyer below price floor) | Merchant side via `should_reject()` | `rejected` | No | Merchant's rejection message rendered; stream closes |
| 4 | Turn limit reached for persona (budget=8, premium=5, bulk=6) | `required_action()` in shopping.py | `expired` | No (if rejected) / Yes (if final merchant terms were acceptable) | "Session expired" status; no further turns possible |
| 5 | Merchant sent `FINAL_OFFER`, shopping counters rather than accept/reject | `main.py` force-reject override | `rejected` | No | Shopping bubble shows override text: "The merchant's final price could not be matched." |

**StateMachine transitions** are enforced in `state_machine.py` and called via `state_machine.apply(msg)` at the end of both `shopping_turn_ai` and `merchant_turn`.

---

## 8. Real-Time SSE Event Flow

```mermaid
sequenceDiagram
    participant Browser as Buyer Browser
    participant API as FastAPI (main.py)
    participant Queue as asyncio.Queue[session_id]
    participant SSE as GET /session/id/stream

    Browser->>API: POST /session/id/turn
    API->>API: shopping_turn() completes
    API->>Queue: _push_event(shopping_msg_summary)
    Queue-->>SSE: payload dequeued
    SSE-->>Browser: data: {"type":"turn","sender":"shopping-agent",...}
    Browser->>Browser: Render Shopping bubble immediately

    API->>API: merchant_turn() completes
    API->>Queue: _push_event(merchant_msg_summary)
    Queue-->>SSE: payload dequeued
    SSE-->>Browser: data: {"type":"turn","sender":"merchant-agent",...}
    Browser->>Browser: Render Merchant bubble

    alt session still active
        API-->>Browser: HTTP 200 response with both turns
    else session ended
        API->>Queue: _push_event(status event)
        Queue-->>SSE: status payload dequeued
        SSE-->>Browser: data: {"type":"status","status":"accepted",...}
        API->>Queue: _close_stream (put None)
        Queue-->>SSE: None sentinel dequeued
        SSE-->>Browser: event: close\ndata: {}
        Browser->>Browser: Close EventSource\nRender DealSummary or closure message
    end
```

**SSE event shapes:**

| Event type | Fields |
|---|---|
| `turn` | `type, turn, sender, intent, display_text, proposed_terms` |
| `status` | `type, status, final_deal` |
| `close` | SSE event named `close`, empty data `{}` |

**Implementation:** The SSE generator (`main.py:stream_session`) loops on `await queue.get()`. A `None` sentinel is the only way to break the loop and close the stream cleanly. The queue is in-memory; safe for single-instance Cloud Run (demo scale).

---

## 9. Metrics Collection Flow

```mermaid
flowchart TD
    A[Gemini API call completes\ncall_gemini_shopping or call_merchant_agent] --> B[metrics.record_call\nagent, model, latency_ms\nprompt_tokens, output_tokens\nsession_id]
    B --> C[Append to _calls list in-memory\nprocess-scoped Python list]

    D[Dry-run path] --> E[record_call with simulated values\nmodel tagged with simulated\nrandom latency and tokens] --> C

    F[main.py — before turn] --> G[metrics_offset = total_call_count\nsnapshot index position]
    H[main.py — after turn] --> I[calls_since offset session_id\nreturns only this turn's calls]
    I --> J[append_session_metrics\nsession_id new_calls\nFirestore sessions/id/llm_calls subcollection\nno-op if dry_run]

    K[GET /metrics endpoint] --> L[metrics.get_metrics\nreturns summary + last 100 raw calls\nby_agent breakdown for merchant and shopping]
    L --> M([Merchant Portal Metrics Screen\ndisplays latency p50 p95 max\ntotal tokens by agent])
```

**In-memory store details:**
- `_calls` is a module-level Python list in `metrics.py`; it resets on server restart.
- `total_call_count()` returns `len(_calls)` — used as a snapshot offset before each turn.
- `calls_since(offset, session_id)` slices `_calls[offset:]` and filters by session_id.
- The Firestore write (`append_session_metrics`) is a no-op when `DRY_RUN=true`.
- The `/metrics` endpoint returns the last 100 raw call records plus summary stats (avg, p50, p95, max latency; total prompt and output tokens).

---

## 10. Dry-Run vs Live Mode

`DRY_RUN` is read from the environment variable. It is checked in `gemini.py:is_dry_run()` and in `shopping.py:shopping_turn_ai()`.

| Component | `DRY_RUN=false` (Live) | `DRY_RUN=true` (Dry-run) |
|---|---|---|
| **Shopping Agent LLM** | Calls Gemini with persona prompt; up to 2 attempts; retry with feedback; 429 breaks immediately | Skips Gemini entirely; uses `fallback_proposal()` deterministically |
| **Shopping Agent metrics** | Real latency and token counts recorded via `record_call()` | Simulated `record_call()` with random latency (500–2200ms) and random token counts; model name tagged `[simulated]` |
| **Shopping Agent source** | `llm` / `llm_repaired` / `override` / `fallback` | `dry_run` |
| **Merchant Agent LLM** | Calls Gemini for prose; up to 2 attempts; static fallback on failure | Not affected — merchant always calls Gemini unless `FINAL_OFFER` or below-floor reject; no dry-run bypass in merchant path |
| **Firestore session persistence** | `create_session`, `update_session`, `get_session` write/read Firestore documents | Falls back to in-memory dict store if Firestore unavailable (controlled in `firebase_db.py`) |
| **Firestore metrics persistence** | `append_session_metrics` writes to `sessions/{id}/llm_calls` subcollection | `append_session_metrics` is a no-op — no Firestore writes for metrics |
| **GET /metrics** | Returns real call records from `_calls` list | Returns records with simulated values — dashboard is populated but shows fake numbers |
| **Session lifecycle** | Full turn loop; all end conditions apply | Full turn loop; all end conditions apply — dry-run only affects Gemini bypass and metrics persistence |
| **SSE stream** | Real-time push as turns complete | Same — SSE is not affected by dry-run mode |

---

## Appendix: Key File Map

| File | Role |
|---|---|
| `orchestrator/src/main.py` | FastAPI app; `run_turn`; SSE queue management; all HTTP endpoints |
| `orchestrator/src/shopping.py` | Shopping Agent; persona specs; `required_action`; `clamp_counter`; `fallback_proposal`; human regex parser |
| `orchestrator/src/merchant.py` | Merchant Agent; `apply_rules`; `should_reject`; Gemini prose call |
| `orchestrator/src/gemini.py` | Gemini client wrappers; `is_dry_run`; `call_gemini_shopping`; `call_merchant_agent` |
| `orchestrator/src/metrics.py` | In-memory LLM call store; `record_call`; `calls_since`; `get_metrics` |
| `orchestrator/src/firebase_db.py` | Firestore CRUD; `append_session_metrics`; in-memory fallback |
| `orchestrator/src/models.py` | Pydantic models: `NegotiationSession`, `A2AMessage`, `ProposedTerms`, enums |
| `orchestrator/src/state_machine.py` | `StateMachine`; enforces legal intent transitions; sets `session.status` and `final_deal` |
| `ui/src/MerchantApp.jsx` | Merchant React root |
| `ui/src/api.js` | Buyer UI API calls |
| `ui/src/components/NegotiationScreen.jsx` | Buyer turn UI; SSE EventSource; renders turn bubbles and DealSummary |
| `ui/src/components/MerchantMetricsScreen.jsx` | Merchant metrics dashboard |
