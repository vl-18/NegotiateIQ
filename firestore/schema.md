# Firestore Schema — NegotiateIQ

## Collection: `products`
Document ID = SKU string (e.g. `SKU-E01`)

```json
{
  "sku":               "SKU-E01",
  "name":              "Google Pixel 9 Pro",
  "list_price":        899.00,
  "price_floor":       719.00,
  "bulk_tiers": [
    { "min_qty": 10, "discount_pct": 8 },
    { "min_qty": 50, "discount_pct": 15 }
  ],
  "delivery_options":  ["standard_5d", "express_2d"],
  "vouchers_eligible": true,
  "image_url":         "https://picsum.photos/seed/pixel9pro/400/280"
}
```

**Notes:**
- `price_floor` — merchant will NEVER go below this; used by `apply_rules()` in `merchant.py`
- `bulk_tiers` — sorted by `min_qty` ascending; the highest-qualifying tier is applied
- `delivery_options` — valid keys: `"standard_5d"`, `"express_2d"`, `"next_day"`
- `image_url` — optional; displayed in the buyer product grid; can be a picsum URL or any stable HTTPS URL
- Seed: `node firestore/seed-products.js` (requires `FIREBASE_PROJECT_ID` env var)
- CSV import: Merchant Portal → Config → Import CSV (uses `data/catalogue_*.csv`)

---

## Collection: `sessions`
Document ID = session UUID (e.g. `f3a92c11-...`)

```json
{
  "session_id":  "f3a92c11-4b27-4f3e-9a12-abc123def456",
  "mode":        "ai",
  "persona":     "budget_shopper",
  "product_sku": "SKU-E01",
  "status":      "active",
  "turn_count":  4,
  "final_deal":  null,
  "created_at":  "2026-10-11T09:30:00+00:00",
  "turns": [
    {
      "a2a_version":  "1.0",
      "session_id":   "f3a92c11-...",
      "turn":         1,
      "sender":       "shopping-agent",
      "receiver":     "merchant-agent",
      "timestamp":    "2026-10-11T09:30:05+00:00",
      "intent":       "counter_offer",
      "product_id":   "SKU-E01",
      "display_text": "I'd like 25 units at $750 each.",
      "reasoning":    "Opening at 83% of list price per persona spec.",
      "constraints":  [],
      "proposed_terms": {
        "unit_price":        750.00,
        "quantity":          25,
        "delivery_days":     5,
        "voucher_requested": null
      }
    }
  ]
}
```

`status` values: `"active"` | `"accepted"` | `"rejected"` | `"expired"`  
`sender`/`receiver` values: `"shopping-agent"` | `"merchant-agent"` | `"human"`

---

## Subcollection: `sessions/{session_id}/llm_calls`
Document ID = auto-generated (one document per Gemini API call)

```json
{
  "ts":             "2026-10-11T09:30:05+00:00",
  "agent":          "merchant",
  "model":          "gemini-3.8-flash",
  "latency_ms":     1240,
  "prompt_tokens":  412,
  "output_tokens":  88,
  "thoughts_tokens": null,
  "session_id":     "f3a92c11-..."
}
```

Written by `firebase_db.append_session_metrics()` after each negotiation turn.  
Skipped entirely when `FIREBASE_DRY_RUN=true`.  
Token fields are `null` for failed calls (only latency is captured on error).

---

## Collection: `config`
Document ID = `"merchant"` (singleton)

```json
{
  "agent_name": "Alex",
  "role":       "Senior Sales Representative",
  "company":    "MadeinMind Commerce"
}
```

Editable from Merchant Portal → Config → Agent Identity section.
