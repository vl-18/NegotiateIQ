# Merchant Agent — Implementation Reference

**File:** `orchestrator/src/merchant.py`  
**Called by:** `orchestrator/src/main.py` → `POST /session/{id}/turn`  
**Depends on:** `gemini.py`, `state_machine.py`, `models.py`

---

## What It Does

The Merchant Agent represents the seller — MadeinMind Commerce, operated by a configurable agent named **Alex** (editable from the merchant portal Config tab). It responds to every buyer message with a structured counter-offer, a final offer, or a rejection.

It has a **two-layer design** which is the most important architectural decision in this file:

```
Layer 1 — Rules Engine (pure Python)
  Decides the actual numbers: price, quantity, delivery, voucher.
  Deterministic. Testable. Gemini cannot override this.

Layer 2 — Gemini (generative AI)
  Takes the numbers from Layer 1 and writes the natural-language message.
  Retries once on transient failure. If both attempts fail, plain fallback text is used.
  The negotiation continues regardless — Gemini failure is non-fatal.
```

**Why this split?** It prevents the LLM from hallucinating prices or accepting deals below the price floor. The rules engine is the source of truth; Gemini is just the voice.

---

## Entry Point

```python
async def merchant_turn(session, product, state_machine, buyer_msg) -> A2AMessage
```

Called once per turn by `main.py`. Returns a fully-formed `A2AMessage` ready to be pushed to the SSE queue and saved to Firestore.

### Step-by-step execution

```
1. Check if buyer's price is below the hard floor (product.price_floor)
   → If yes: emit REJECT immediately (no rules engine, no Gemini)

2. Rules engine: apply_rules(product, buyer_terms, turn, prev_price)
   → Returns (ProposedTerms, Intent)
   → Intent is FINAL_OFFER when offered price ≤ price_floor + FINAL_OFFER_EPSILON ($0.50)
   → Intent is COUNTER_OFFER otherwise

3. If FINAL_OFFER:
   → Use static firm message — Gemini is bypassed entirely on final offer turns

4. If COUNTER_OFFER:
   → Build negotiation context string (full turn history + decided terms)
   → Call Gemini with retry (up to 2 attempts):
       Attempt 1 → call_merchant_agent(context, session_id)
       If 429/quota error → break immediately, use fallback
       If other error → retry once
       If attempt 2 also fails → use static fallback text
   → On success: display_text and reasoning come from Gemini response

5. Assemble A2AMessage and call state_machine.apply(msg)
   → Updates session.status if REJECT or FINAL_OFFER resolution

6. Return the message
```

---

## Rules Engine

### `apply_rules()` — how the price is calculated

```
Start price = min(previous merchant offer, list price)
            → Merchant never increases their own offer

Bulk discount = check product.bulk_tiers for quantity thresholds
              → e.g. 10+ units → 8% off list price
              → 50+ units → 15% off list price

Offered price = min(start price, bulk-discounted price)
              → Takes the more favourable of the two

If buyer pushed lower:
  → Split the difference: (offered + buyer_ask) / 2
  → Clamp to price_floor — NEVER go below

Final offer trigger:
  → offered_price ≤ price_floor + FINAL_OFFER_EPSILON (default $0.50)
  → Issues FINAL_OFFER intent; subsequent counter is force-rejected by main.py

Delivery:
  → Default: standard (5 days)
  → If buyer requested < 5 days: offer express (2 days) if available
  → Express offered without reducing the price further

Voucher:
  → Only on the FINAL_OFFER turn
  → Only if product.vouchers_eligible = true
  → Code: "LOYALTY10"
```

### Hard reject — when to refuse immediately

If the buyer's offered price is below `product.price_floor`, the merchant rejects immediately with a polite message. No Gemini call, no rules engine — just a direct `REJECT` intent.

---

## Key Constants

| Constant | Value | Location | What It Controls |
|---|---|---|---|
| `FINAL_OFFER_EPSILON` | `0.50` | `merchant.py` | Within $0.50 of floor → issues FINAL_OFFER |
| `SAFETY_MAX_TURNS` | `50` | `state_machine.py` | Absolute backstop (bug guard only) |
| Voucher code | `"LOYALTY10"` | `merchant.py` `apply_rules()` | Voucher offered on final turn |

Turn limits are **per persona** in `shopping.py`, not global:
- Budget Shopper: 8 turns
- Premium Buyer: 5 turns
- Bulk Purchaser: 6 turns

---

## Product Object

```python
class Product:
    sku:               str    # "SKU-001"
    name:              str    # "Sony WH-1000XM6"
    list_price:        float  # 99.99
    price_floor:       float  # 79.99  ← merchant NEVER goes below this
    bulk_tiers:        list   # [{"min_qty": 10, "discount_pct": 8}, ...]
    delivery_options:  list   # ["standard_5d", "express_2d"]
    vouchers_eligible: bool   # True / False
    image_url:         str | None  # picsum or external URL for buyer grid display
```

Loaded from Firestore (or `_DRY_RUN_PRODUCTS` in dry-run mode) by `firebase_db.get_product()`. Read-only inside merchant logic.

---

## Gemini Integration

The merchant agent calls Gemini **only for prose** — never for pricing decisions.

```python
context = build_negotiation_context(session, product, config)
# Appends: "Your next offer (already decided by rules engine): $89.99/unit, qty 25, 2-day delivery."

# Retry loop — up to 2 attempts
for attempt in range(2):
    try:
        gemini_response = await call_merchant_agent(context, session_id=session.session_id)
        display_text = gemini_response.get("display_text", "")
        break
    except Exception as exc:
        log.warning("merchant Gemini attempt %d failed: %s: %s", attempt+1, type(exc).__name__, exc)
        is_quota = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
        if attempt == 1 or is_quota:
            display_text = f"For {terms.quantity} units, I can offer ${terms.unit_price:.2f}/unit..."
            break
```

If both attempts fail (or quota is exceeded), the static fallback is used. The session continues normally — the merchant's terms are still correct.

**System prompt:** `orchestrator/prompts/merchant_system.txt`  
**Gemini model:** `gemini-3.8-flash` (configurable via `MERCHANT_MODEL` env var)

---

## Metrics

Every real Gemini call (success or failure) records to the in-memory metrics store:

```python
# On success: tokens populated
_metrics.record_call(agent="merchant", model=MERCHANT_MODEL, session_id=session_id, **meta)

# On failure: latency recorded, tokens are None
_metrics.record_call(agent="merchant", model=MERCHANT_MODEL, latency_ms=elapsed, session_id=session_id)
```

Records are persisted to Firestore at `sessions/{session_id}/llm_calls` after each turn (no-op in `FIREBASE_DRY_RUN=true` mode).

---

## How to Update Logic

| Change | Where to edit |
|---|---|
| Change how price is calculated | `apply_rules()` in `merchant.py` |
| Change the final-offer trigger threshold | `FINAL_OFFER_EPSILON` in `merchant.py` |
| Change the voucher code or eligibility logic | `apply_rules()` in `merchant.py` |
| Change the merchant's personality/tone | `orchestrator/prompts/merchant_system.txt` |
| Change the Gemini model | `MERCHANT_MODEL` env var (default: `gemini-3.8-flash`) |
| Add a new bulk tier | Add to product document in Firestore (no code change) |
| Add a new product | Firestore `products` collection or `_DRY_RUN_PRODUCTS` in `firebase_db.py` |
| Edit agent name/role/company | Merchant portal → Config tab (persisted to Firestore) |
