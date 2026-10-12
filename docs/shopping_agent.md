# Shopping Agent — Implementation Reference

**File:** `orchestrator/src/shopping.py`  
**Called by:** `orchestrator/src/main.py` → `POST /session/{id}/turn`  
**Depends on:** `gemini.py`, `state_machine.py`, `models.py`

---

## What It Does

The Shopping Agent represents the buyer — the counterparty to the merchant. It operates in two distinct modes chosen at session creation:

| Mode | Who drives it | How it works |
|---|---|---|
| **AI mode** | Gemini + a persona | Persona rules engine → Gemini prose → safety clamp |
| **Human mode** | A real person typing in the UI | Text is regex-parsed into structured A2A terms |

Both modes produce identical `A2AMessage` shapes. The Merchant Agent cannot tell which mode is active.

---

## Entry Point

```python
async def shopping_turn(session, product, state_machine, message_text=None) -> A2AMessage
```

The public router. Called once per turn by `main.py`.

```
if session.mode == "ai":
    → shopping_turn_ai()   — Gemini generates the buyer move (with safety guardrails)

if session.mode == "human":
    → message_text is required (raises ValueError if blank)
    → shopping_turn_human()  — parses typed text into A2A terms
```

---

## AI Mode — safety pipeline

The AI mode is a **four-layer pipeline**, not a single LLM call. Each layer has a defined role and they run in order:

```
Layer 1 — required_action()
  Code decides ACCEPT/REJECT before Gemini is even called.
  Fires when: turn limit reached, stall limit reached, merchant rejected us.
  If it fires → skip all other layers, use its decision directly.

Layer 2 — Gemini call (with retry)
  Sends structured JSON context + persona system prompt to Gemini.
  Returns BuyerReply: { intent, unit_price, quantity, delivery_days, reasoning }
  Retry once if: parse error, schema mismatch, or wrong intent.
  Break immediately on 429 RESOURCE_EXHAUSTED (quota errors don't resolve on retry).

Layer 3 — clamp_counter()
  Post-LLM hard clamps applied to the returned terms:
  - Never bid above persona's walk-away price
  - Never raise own previous offer
  - Never bid above what merchant just offered
  - Clamp delivery_days to persona's max acceptable
  - Clamp quantity to persona's configured range

Layer 4 — fallback_proposal()
  Used when: DRY_RUN=true, or all Gemini attempts fail.
  Deterministic paced move: starts at persona's opening price,
  then moves toward the merchant's offer by a configured fraction each turn.
```

### Personas

Each persona is defined as a `PersonaSpec` dataclass in `shopping.py` with hard-coded negotiation parameters:

| Persona | File | Turn limit | Stall limit | Opening price | Walk-away |
|---|---|---|---|---|---|
| `budget_shopper` | `persona_budget_shopper.txt` | 8 turns | 3 stall | 70% of list | price_floor + 5% |
| `premium_buyer` | `persona_premium_buyer.txt` | 5 turns | 2 stall | 85% of list | price_floor + 12% (extended range) |
| `bulk_purchaser` | `persona_bulk_purchaser.txt` | 6 turns | 2 stall | 68% of list (qty<50), 62% (qty≥50) | price_floor + 3% |

**Turn limit** = how many turns before `required_action()` forces ACCEPT/REJECT.  
**Stall limit** = how many consecutive turns where the merchant's offer doesn't improve before the persona gives up.

---

## AI Mode — `shopping_turn_ai()` step-by-step

```
1. Simulated metrics (DRY_RUN=true only)
   → record_call(agent="shopping", model="gemini-3.8-flash [simulated]",
                 latency_ms=random, prompt_tokens=random, output_tokens=random)
   → Jump to fallback_proposal() — no Gemini call in dry-run

2. required_action() — code override before LLM
   → Returns (Intent, override_terms) if a forced move is needed, else None
   → If triggered: skip Gemini entirely, use override

3. _build_context(session, product, persona_spec)
   → Structured JSON: product details, persona limits, full turn history
   → Replaces old plain-text "Turn N of 8" format — richer signal for Gemini

4. Retry loop (up to 2 attempts):
   try:
     call_gemini_shopping(system_prompt, context, response_schema=BuyerReply)
     _intent_problem() → check if returned intent is valid for current state
     clamp_counter()  → apply hard limits to LLM's terms
     break
   except 429/RESOURCE_EXHAUSTED:
     break  # quota error — retrying won't help
   except other:
     inject corrective feedback into context for attempt 2

5. On all failures: fallback_proposal()
   → Deterministic paced move; session continues regardless

6. Per-turn structured log:
   {event, session_id, turn, persona, required, phase, stall, intent, source, attempts, latency_ms}
   source values: "llm" | "llm_repaired" | "override" | "fallback" | "dry_run"

7. Assemble A2AMessage, call state_machine.apply(msg), return
```

---

## `required_action()` — when code overrides Gemini

This runs before any Gemini call. It returns a forced decision if any of these conditions are true:

| Condition | Decision |
|---|---|
| Merchant just sent REJECT | ACCEPT last good offer (if acceptable) or REJECT |
| Turn count ≥ persona's turn limit | ACCEPT if last merchant offer is within walk-away, else REJECT |
| Stall count ≥ persona's stall limit (N turns with no merchant improvement) | ACCEPT if acceptable, else REJECT |

`is_acceptable()` validates the merchant's terms: price ≤ walk-away, delivery_days ≤ persona max, quantity in persona range. All three must pass.

---

## `clamp_counter()` — post-LLM hard limits

Applied to every LLM-generated counter-offer to prevent the model from violating persona constraints:

```python
# 1. Never go above walk-away price
if proposed_price > persona.walk_away_price:
    proposed_price = persona.walk_away_price

# 2. Never raise own offer (buyer never bids against themselves)
if proposed_price > last_buyer_price:
    proposed_price = last_buyer_price

# 3. Never bid above the merchant's current offer (redundant but safe)
if proposed_price >= merchant_price:
    proposed_price = merchant_price - 0.01

# 4. Delivery: never demand faster than persona max
if proposed_delivery < persona.max_delivery_days:
    proposed_delivery = persona.max_delivery_days (or skip field)

# 5. Quantity: clamp to persona's min/max range
quantity = max(persona.min_qty, min(persona.max_qty, proposed_qty))
```

If the repair notes list is non-empty (something was clamped), the source field becomes `"llm_repaired"` in the turn log.

---

## `fallback_proposal()` — deterministic paced move

Used when Gemini is unavailable or in dry-run mode. Produces a reasonable counter-offer without any LLM:

```python
# Pace from opening price toward merchant's price by fraction per turn
progress = min(turn / (turn_limit - 1), 1.0)
paced_price = opening_price + (merchant_price - opening_price) * progress * pace_fraction
# Clamp to walk-away and floor
offered_price = max(walk_away, min(paced_price, merchant_price - 0.01))
```

The persona's `pace_fraction` is configured in `PersonaSpec` (e.g. 0.4 = moves 40% of the gap per turn).

---

## Human Mode — `shopping_turn_human()`

No Gemini. Regex-parses the typed message to extract structured terms:

```
Extraction patterns:
  Price:    "$99.99", "99.99 per unit", "at 99", "offer 99"
  Quantity: "25 units", "qty 50", "order of 10"
  Delivery: "2-day", "next day", "express"
  Voucher:  "LOYALTY10" or any word matching [A-Z0-9]{3,12}

Intent detection:
  ACCEPT → "accept", "deal", "agreed", "yes", "ok", "I'll take it"
  REJECT → "no deal", "reject", "walk away", "too expensive"
  COUNTER_OFFER → if a price was extracted
  QUERY → fallback (price not extracted, no accept/reject keyword)

Sender = Sender.HUMAN (state machine treats same as SHOPPING_AGENT for alternation)
```

The merchant receives free-text in `display_text` and structured terms in `proposed_terms` — both populated from the single typed message.

---

## Gemini Integration

**Model:** `gemini-3.8-flash` (configurable via `SHOPPING_MODEL` env var)  
**System prompt:** persona file from `orchestrator/prompts/persona_*.txt`  
**Output mode:** Gemini JSON-mode with `BuyerReply` Pydantic schema as `response_schema`

```python
class BuyerReply(BaseModel):
    intent: str          # "counter_offer" | "accept" | "reject"
    unit_price: float | None
    quantity: int | None
    delivery_days: int | None
    reasoning: str       # internal reasoning (not shown to merchant)
```

**Context format:** Structured JSON (not plain text), containing:
- Product: name, SKU, list_price
- Persona limits: walk-away price, max delivery, quantity range, turns remaining
- Turn history: each message as `{turn, sender, intent, price, qty, days}`

**Metrics:** Every real Gemini call records to the in-memory metrics store:
```python
# On success: full metadata
_metrics.record_call(agent="shopping", session_id=session_id, **meta)
# On failure: latency only (tokens are None)
_metrics.record_call(agent="shopping", model=SHOPPING_MODEL, latency_ms=elapsed, session_id=session_id)
```

Records are persisted to Firestore at `sessions/{session_id}/llm_calls` after each turn.

---

## Structured Turn Log (per turn, stdout)

Every AI turn emits a JSON log line for observability:

```json
{
  "event": "shopping_turn",
  "session_id": "...",
  "turn": 3,
  "persona": "budget_shopper",
  "required": false,
  "phase": "negotiating",
  "stall": 0,
  "intent": "counter_offer",
  "source": "llm",
  "attempts": 1,
  "latency_ms": 1240,
  "llm": { "model": "gemini-3.8-flash", "prompt_tokens": 512, "output_tokens": 88 }
}
```

`source` values:
- `"llm"` — Gemini's answer used as-is
- `"llm_repaired"` — Gemini's answer used but clamped by `clamp_counter()`
- `"override"` — `required_action()` decided before Gemini was called
- `"fallback"` — Gemini failed; deterministic `fallback_proposal()` used
- `"dry_run"` — DRY_RUN=true; `fallback_proposal()` always used, simulated metric recorded

---

## How to Update Logic

| Change | Where to edit |
|---|---|
| Change a persona's price limits, turn budget, stall limit | `PERSONAS` dict in `shopping.py` (`PersonaSpec` fields) |
| Change a persona's negotiation tone and LLM behavior | `orchestrator/prompts/persona_*.txt` |
| Add a new persona | New `PersonaSpec` in `PERSONAS`, new prompt file, add to `PERSONA_PROMPT_FILES` in `gemini.py`, add to UI `PERSONAS` array in `NegotiationScreen.jsx` |
| Change the Gemini model for shopping | `SHOPPING_MODEL` env var (default: `gemini-3.8-flash`) |
| Change how human mode parses typed text | Regex patterns in `shopping_turn_human()` |
| Change the walk-away acceptance logic | `is_acceptable()` in `shopping.py` |
| Change how turns are forced to end | `required_action()` in `shopping.py` |
| Change the deterministic fallback offer | `fallback_proposal()` in `shopping.py` |
