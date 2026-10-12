# NegotiateIQ

> Smarter deals. Zero friction. Agent-native commerce.

A real-time, agent-to-agent (A2A) negotiation platform built on Google Cloud. Two AI agents — a Merchant and a Shopper — conduct structured multi-turn commercial negotiations over price, quantity, delivery, and loyalty perks. Live demo UI hosted on Firebase.

## Structure

```
negotiateiq/
├── orchestrator/           # Python FastAPI backend — all agent logic lives here
│   ├── src/
│   │   ├── main.py         # FastAPI app (3 endpoints)
│   │   ├── models.py       # Pydantic data shapes (A2AMessage, NegotiationSession …)
│   │   ├── state_machine.py# Turn progression and negotiation lifecycle
│   │   ├── merchant.py     # Merchant Agent: rules engine + Gemini call
│   │   ├── shopping.py     # Shopping Agent: AI persona or human relay
│   │   ├── gemini.py       # Thin async Gemini API wrapper
│   │   └── firebase_db.py  # Firestore + Firebase Realtime DB integration
│   ├── prompts/            # System prompts for Merchant Agent and buyer personas
│   ├── tests/              # Unit + smoke tests (80 tests, all passing)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── ui/                     # React frontend (Firebase Hosting) — Phase 2
├── firestore/              # Firestore schema reference + product seed script
├── functions/              # Cloud Functions placeholder (future: escalation handler)
├── infra/                  # Deployment scripts (Cloud Run + Firebase)
└── docs/                   # Spec and documentation
```

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/session/start` | Create a new negotiation session |
| `POST` | `/session/{id}/turn` | Run one full turn (shopping → merchant) |
| `GET` | `/session/{id}/status` | Get session state and full turn history |
| `GET` | `/health` | Liveness check for Cloud Run |

## Quick Start (Local Dev)

See `docs/spec.md` Sections 13–14 for full GCP setup and local dev workflow.

```bash
# 1. Create and activate venv
cd orchestrator
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up env vars
cp .env.example .env
# Fill in GEMINI_API_KEY and FIREBASE_DATABASE_URL

# 4. Run the server
uvicorn src.main:app --reload --port 8080

# 5. Run all tests (no services needed — fully mocked)
python -m pytest tests/ -v
```

## Build Log

See [build_log.md](build_log.md) for progress tracking.
