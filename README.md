# NegotiateIQ

> Smarter deals. Zero friction. Agent-native commerce.

**NegotiateIQ is a Merchant Agent that negotiates autonomously over Google's A2A protocol, inside the merchant's own rules.**

Shoppers already haggle, and soon their AI agents will do it at machine speed, around the clock. Merchants who can't answer lose the sale; merchants who concede by hand lose margin. NegotiateIQ answers every offer on price, quantity, delivery and vouchers, and it never sells below the price floor.

The shopper side in this repo (three AI personas, or a typed human message) is a demo counterparty that shows the Merchant Agent at work. The product is the merchant.

Built on Google Cloud: Gemini, Cloud Run, Firestore and Firebase Hosting.

## Why it's different

- **AI writes. Rules govern.** A Python rules engine decides every number (price, delivery, voucher). Gemini only writes the prose around terms that are already fixed, so a prompt cannot move a price.
- **Merchant-first.** Most agentic-commerce demos shop for the buyer. This one sells for the merchant.
- **Open standard.** Built on A2A v1.0 (`a2a-sdk`, structured offers in DataParts), so any compliant shopping agent can negotiate with it.
- **Humans and agents.** Typed text from a person and structured offers from an AI agent become the same A2A message. The Merchant Agent handles both identically.
- **Clean endings.** Every negotiation ends in a deal, a polite decline, or a final offer at the floor.

## How the Merchant Agent decides each turn

1. **Floor check.** If the shopper's price is below the price floor, decline politely (no LLM call).
2. **Rules engine.** Start from the lower of the last offer and list price, apply the bulk tier, split the difference with the shopper, never go below the floor, then set delivery (standard 5 days; express 2 days if asked) and voucher.
3. **Final-offer gate.** Within $0.50 of the floor, send a firm `FINAL_OFFER` with a static message (plus the `LOYALTY10` voucher if the product is eligible).
4. **Gemini prose.** Otherwise Gemini writes the counter-offer wording around the decided terms (two attempts, then a static fallback with the same terms).
5. **A2A reply.** The structured offer goes back to the shopper, is stored, and is streamed live to the UI.

Enforced in code, not in the prompt:

- The Merchant Agent never sells below the price floor.
- Gemini cannot change price, delivery or voucher.
- A counter-offer after a final offer is force-rejected.
- If Gemini fails or is over quota, the reply falls back to static text with the same terms.

### Session outcomes

| Outcome | Trigger | Status |
|---|---|---|
| Deal closed | Shopper accepts | `accepted` |
| Shopper walks away | Shopper rejects | `rejected` |
| Merchant declines | Offer below the price floor | `rejected` |
| Final offer refused | Shopper counters after a final offer | `rejected` |
| Turn limit reached | Persona turn limit hit | `expired` |

### Demo shopper personas

| Persona | Turn limit | Stall limit |
|---|---|---|
| Budget Shopper | 8 | 3 |
| Premium Buyer | 5 | 2 |
| Bulk Purchaser | 6 | 2 |

A shopper can also be a human typing in plain words. Typed offers are parsed (price, quantity, delivery, voucher) into the same structured message.

## Architecture

```
Firebase Hosting ── Merchant portal (React)     Buyer demo UI (React)
        │   HTTPS · /api/* rewrite · REST + SSE      │
        └───────────────────┬─────────────────────────┘
                            ▼
          Cloud Run · FastAPI Orchestrator
   A2A routing · turn state machine · SSE · LLM metrics · persistence
                 │                          │
                 ▼  A2A v1.0 (DataParts)    ▼
   Merchant Agent (A2A server)     Demo Shopping Agent (A2A client)
   Rules engine + Gemini 3.5 Flash   Gemini 3.5 Flash-Lite · personas · human relay
                 │
                 ▼
   Firestore · Secret Manager · Artifact Registry · Vertex AI · Cloud Logging (planned)
```

- Live turns stream to the browser over **Server-Sent Events** (`EventSource`), with no Firebase JS SDK and no Realtime Database.
- **Firestore** stores products, sessions and per-session LLM call records.
- **Models:** Gemini 3.5 Flash for the Merchant Agent, Gemini 3.5 Flash-Lite for the demo shopper. Set the exact model IDs with `MERCHANT_MODEL` and `SHOPPING_MODEL`.

## Merchant console

A password-gated portal (separate Vite app, port 5174) for the merchant:

- **Dashboard:** sessions, win rate, average discount, outcome breakdown, recent sessions.
- **Products:** full pricing rules, including price floor and bulk tiers (never shown in the buyer portal).
- **Negotiations:** history of completed sessions.
- **Config:** edit products and agent identity.
- **Metrics:** LLM calls, tokens and p50 / p95 latency per agent, refreshed every 10 s.

> The demo password is `merchant123`. It is a convenience gate, not a security boundary. Replace it before any real use.

## Structure

```
negotiateiq/
├── orchestrator/           # Python FastAPI backend, all agent logic
│   ├── src/
│   │   ├── main.py         # FastAPI app: sessions, SSE stream, products, config, metrics
│   │   ├── models.py       # Pydantic data shapes (A2AMessage, NegotiationSession ...)
│   │   ├── state_machine.py# Turn progression, alternation, expiry
│   │   ├── merchant.py     # Merchant Agent: rules engine + Gemini prose
│   │   ├── shopping.py     # Demo shopper: AI personas (with safety pipeline) or human relay
│   │   ├── gemini.py       # Async Gemini wrapper, prompt loading, metrics recording
│   │   ├── metrics.py      # In-memory LLM call store (p50 / p95, tokens)
│   │   └── firebase_db.py  # Firestore CRUD + in-memory dry-run fallback
│   ├── prompts/            # Merchant system prompt + one prompt per buyer persona
│   ├── tests/              # pytest suite, fully mocked
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── ui/                     # React + Vite: buyer demo UI (:5173) and merchant portal (:5174)
├── firestore/              # Firestore schema reference + product seed script
├── functions/              # Cloud Functions placeholder (future: escalation handler)
├── infra/                  # Deployment scripts (Cloud Run + Firebase)
└── docs/                   # Spec and architecture documentation
```

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/session/start` | Create a negotiation session (product, mode, persona) |
| `POST` | `/session/{id}/turn` | Run one full turn (shopper, then merchant) |
| `GET` | `/session/{id}/stream` | SSE stream of turns and the final status |
| `GET` | `/session/{id}/status` | Session state and full turn history |
| `GET` | `/sessions` | List sessions (merchant dashboard) |
| `GET` | `/products` | List products |
| `PUT` | `/products/{sku}` | Update product pricing (merchant config) |
| `GET` / `PUT` | `/config` | Read or update merchant agent identity |
| `GET` | `/metrics` | In-memory LLM call metrics |
| `GET` | `/health` | Liveness check for Cloud Run |

In deployment, Firebase Hosting rewrites `/api/*` to the Cloud Run service, and the Vite dev proxy does the same locally.

## Quick start (local dev)

See `docs/spec.md` for full GCP setup and the local-to-cloud workflow.

```bash
# 1. Backend: create and activate a venv
cd orchestrator
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up env vars
cp .env.example .env
# Add GEMINI_API_KEY (an AI Studio key is fine for local dev)

# 4. Run the server
uvicorn src.main:app --reload --port 8001

# 5. Run all tests (no services needed, fully mocked)
python -m pytest tests/ -v
```

```bash
# 6. UI (in a second terminal)
cd ui
npm install
npm run dev              # buyer demo UI    -> http://localhost:5173
npm run dev:merchant     # merchant portal  -> http://localhost:5174
```

### No credentials? Use dry-run

| Flag | Effect |
|---|---|
| `DRY_RUN=true` | Skips Gemini calls for the demo shopper and returns deterministic moves, with simulated metrics so the dashboard is populated |
| `FIREBASE_DRY_RUN=true` | Replaces Firestore with in-memory dicts (data is lost on restart) |

Both can be combined. This is the quickest way to run the full demo without any GCP setup.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Live mode | Google AI Studio key (local dev). On Cloud Run, use Vertex AI with a service account |
| `MERCHANT_MODEL` | No | Gemini model for the Merchant Agent (Gemini 3.5 Flash) |
| `SHOPPING_MODEL` | No | Gemini model for the demo shopper (Gemini 3.5 Flash-Lite) |
| `DRY_RUN` | No | `true` skips Gemini calls (default `false`) |
| `FIREBASE_DRY_RUN` | No | `true` uses in-memory storage (default `false`) |
| `GCP_PROJECT` | Firestore | GCP project ID |
| `GCP_REGION` | Firestore | GCP region |

Never commit `.env` or any service-account key file. `.env.example` is safe to commit.

## Deployment

- **Backend:** one container on **Cloud Run**, with the image in Artifact Registry. Use a service account with minimum permissions (Firestore read/write only).
- **Frontends:** **Firebase Hosting** with two targets, `buyer` and `merchant`, each serving its own build and rewriting `/api/*` to Cloud Run.
- **Secrets:** Secret Manager in production, `.env` locally.

## Quality

- 96 pytest tests, including A2A round trips through the real SDK types.
- A 33-scenario negotiation harness (11 hostile scenarios across 3 personas, also run over the A2A wire).
- Live runs against a rule-based mock merchant: 6 of 6 closed in a valid deal, median shopper turn about 1.6 s.

## Status and roadmap

**Built:** autonomous Merchant Agent, rules engine, final offer at the floor, delivery and voucher trade-offs, merchant console and LLM metrics, A2A v1.0 messaging, live SSE trace, human and AI demo shopper.

**Next:**

- Cloud Logging audit trail of every A2A message, with an exportable deal summary
- Human manager escalation for deals beyond every threshold (Pub/Sub + Cloud Functions)
- Persistent deal history (win rate, average discount, most contested SKUs over time)
- Webhook integrations (Slack, ERP, CRM)

## Notes

- The in-memory metrics store resets on every backend restart. Per-session LLM call records are also written to Firestore.
- Cloud Run is sized for demo scale (single instance, in-memory SSE queues).