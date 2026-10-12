# NegotiateIQ — Agent-to-Agent Negotiation Platform
### Technical Specification & Demo Blueprint
**Version:** 1.0 | **Target Audience:** Google Demo | **Stack:** Google Cloud (end-to-end)

---

## 1. Project Overview

**NegotiateIQ** is a real-time, agent-to-agent (A2A) negotiation platform built entirely on Google Cloud. It demonstrates how autonomous AI agents can conduct structured, multi-turn commercial negotiations — covering price, quantity, delivery, and loyalty perks — in the context of e-commerce retail.

A **Merchant Agent** (fully scoped, always autonomous) negotiates with a **Shopping Agent** that can be driven either by a Gemini-powered AI or by a live human — switchable at demo time. Both agents communicate via the **A2A Protocol**, and every negotiation turn is visualised in real time through a polished side-by-side chat UI hosted on Firebase.

### Why This Matters for Google
This demo showcases the power of Google Cloud's full AI stack: Vertex AI for agent hosting, Gemini for reasoning, A2A for structured inter-agent communication, and Firebase for real-time front-end delivery — all working together in a single, cohesive, production-realistic system.

---

## 2. Project Name

**NegotiateIQ**
*Tagline: "Smarter deals. Zero friction. Agent-native commerce."*

---

## 3. Goals

| # | Goal |
|---|---|
| G1 | Demonstrate autonomous multi-turn A2A negotiation between two agents |
| G2 | Show Merchant Agent intelligence: dynamic pricing, deal scoring, and autonomous deal closure |
| G3 | Support dual shopping modes — AI agent and human-in-the-loop — with a mode toggle |
| G4 | Provide a visually compelling, real-time negotiation trace UI for live demos |
| G5 | Run 100% on Google Cloud with zero external dependencies |

---

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Firebase Hosting                         │
│                  NegotiateIQ Demo UI (React)                    │
│   ┌──────────────────┐        ┌──────────────────────────────┐  │
│   │  Shopping Panel  │        │      Merchant Panel          │  │
│   │  (AI or Human)   │        │   (Always Autonomous)        │  │
│   └────────┬─────────┘        └────────────┬─────────────────┘  │
│            │    SSE (EventSource browser API)   │               │
│            └──────────────┬────────────────┘                   │
└───────────────────────────┼─────────────────────────────────────┘
                            │ HTTP + SSE  (FastAPI / Cloud Run)
         ┌──────────────────┴──────────────────────┐
         │              Cloud Run                   │
         │     Python FastAPI Orchestration Layer   │
         │  (A2A routing, state machine, SSE push,  │
         │   Firestore persistence, audit log)      │
         └──────┬──────────────────────┬────────────┘
                │                      │
    ┌───────────▼──────┐    ┌──────────▼───────────┐
    │    Gemini 2.5    │    │   Gemini 2.5 Flash   │
    │      Flash       │    │        Lite           │
    │  Merchant Agent  │    │   Shopping Agent      │
    │  - Pricing rules │    │  - Buyer persona      │
    │  - Deal scoring  │    │  - Preference profile │
    │  - Auto-closure  │    │  - Counter-offer logic│
    └──────────────────┘    └──────────────────────┘
```

> **Architecture note (updated):** Firebase Realtime Database has been replaced with
> Server-Sent Events (SSE) directly from the FastAPI orchestrator. The UI uses the
> native browser `EventSource` API — no Firebase JS SDK required. Firestore is kept
> for session and product persistence.

---

## 5. Core Components

### 5.1 Merchant Agent (Full Scope)

**Model:** Gemini 2.5 Flash on Vertex AI
**Hosting:** Vertex AI Agent Builder / Cloud Run

**Capabilities:**

| Capability | Description |
|---|---|
| Price Negotiation | Maintains a price floor per SKU; calculates acceptable discount bands dynamically |
| Quantity / Bulk Deals | Applies tier-based pricing (e.g., 10+ units → 8% off, 50+ → 15% off) |
| Delivery Timeline | Negotiates delivery windows based on stock availability and shipping SLAs |
| Loyalty / Vouchers | Offers vouchers, early access, or reward points as sweeteners to close a deal |
| Deal Scoring | Internally scores each proposed deal (margin impact, relationship value, urgency) |
| Counter-Offering | Generates structured counter-proposals with reasoning traces |
| Auto-Closure | At turn N-1 emits a `final_offer`; accepts or rejects based on buyer response |
| Memory | Maintains negotiation state across turns using session context in Firestore |

**Autonomy Model:**
- **Fully autonomous** within pre-configured rules: discount bands, delivery windows, voucher eligibility
- If buyer demand exceeds all configured thresholds, the agent issues a polite final rejection — no human loop required in the current scope
- _(Human escalation to a manager is planned as a future enhancement — see Section 16)_

**System Prompt Design Highlights:**
- Role-plays as a senior sales representative for a fictional e-commerce brand
- Has a configurable personality dial: `collaborative` ↔ `firm`
- Emits structured A2A messages with explicit `intent`, `offer`, `justification`, and `constraints` fields

---

### 5.2 Shopping Agent

**Model:** Gemini 2.5 Flash-Lite on Vertex AI
**Hosting:** Vertex AI Agent Builder / Cloud Run

**Dual-Mode Design:**

| Mode | Trigger | Behaviour |
|---|---|---|
| **AI Mode** | Toggle switch in UI | Gemini-powered agent with a buyer persona auto-drives the negotiation |
| **Human Mode** | Toggle switch in UI | Chat input box appears; human messages are wrapped in A2A envelope and sent |

Both modes are indistinguishable to the Merchant Agent — they produce identical A2A message structures.

**AI Mode — Buyer Persona:**
- Configurable at demo time: "Budget Shopper", "Premium Buyer", "Bulk Purchaser"
- Each persona has a preference profile (price sensitivity, brand loyalty, delivery urgency)
- Generates realistic counter-offers, pushback, and acceptance signals

**Human Mode:**
- Firebase-hosted chat input
- Messages typed by the human are wrapped in an A2A envelope by the front-end
- No AI inference needed on the shopping side — Cloud Run relays directly to Merchant Agent

---

### 5.3 A2A Protocol Layer

**Transport:** HTTP over Cloud Run (Python FastAPI + uvicorn)
**Message Schema:**

```json
{
  "a2a_version": "1.0",
  "session_id": "uuid",
  "turn": 3,
  "sender": "shopping-agent | human",
  "receiver": "merchant-agent",
  "timestamp": "ISO8601",
  "message": {
    "intent": "counter_offer | accept | reject | query | final_offer",
    "product_id": "SKU-001",
    "proposed_terms": {
      "unit_price": 89.99,
      "quantity": 25,
      "delivery_days": 5,
      "voucher_requested": "LOYALTY10"
    },
    "reasoning": "string (optional, for AI agents)",
    "constraints": ["max_budget: 2500", "delivery_by: 2026-10-15"]
  }
}
```

**State Machine — Negotiation Turns:**
```
INITIATED → SHOPPING_OFFER → MERCHANT_COUNTER → [loop] → FINAL_OFFER → ACCEPTED | REJECTED
```

- Maximum configurable turns (default: 8)
- Auto-resolution at turn limit: best available offer is surfaced

---

### 5.4 React UI

**Hosting:** Firebase Hosting (serves the static React build)
**Realtime:** Server-Sent Events via `EventSource` browser API → FastAPI `/session/{id}/stream` endpoint
**Branding:** MadeinMind · NegotiateIQ · Google Cloud colour palette (dark theme)
> No Firebase JS SDK or Realtime Database required. Turns are pushed directly from the orchestrator.

**Role-Based UI — Buyer Portal vs Merchant Dashboard:**

The UI has two distinct modes controlled by a `role` state in App.jsx:

| Role | How to access | What is visible |
|---|---|---|
| `buyer` | Default (no login) | Products (sanitised), Negotiate |
| `merchant` | Password login (`merchant123`) | Dashboard, Products (full), Negotiations, Config |

Merchant-internal data (price floor, exact bulk discount %) is **never shown in the buyer portal**.

**Buyer Portal Layout:**
```
┌────────────────┬──────────────────────────────────────────────┐
│ MadeinMind     │  Products tab:                               │
│ NegotiateIQ    │    2×2 product cards — list price + volume   │
│                │    discount badge only (no price floor shown)│
│ ● Products     │                                              │
│ ● Negotiate    │  Negotiate tab (setup):                      │
│                │    Left:  Merchant side (our agent, fixed)   │
│ 🔐 Merchant    │    Right: Counterparty — Shopping Agent      │
│   login        │           (AI persona or Human — demo config)│
│ Powered by     │                                              │
│ Google Cloud   │  Negotiate tab (live chat):                  │
│ © 2026         │    Full-width SSE chat transcript            │
└────────────────┴──────────────────────────────────────────────┘
```

**Merchant Dashboard Layout:**
```
┌────────────────┬──────────────────────────────────────────────┐
│ MadeinMind     │  Dashboard tab:                              │
│ NegotiateIQ    │    Metrics: total sessions, win rate,        │
│ [MERCHANT]     │    avg discount, rejected/expired counts     │
│                │    Outcome bar chart + recent sessions table │
│ ● Dashboard    │                                              │
│ ● Products     │  Products tab (merchant):                    │
│ ● Negotiations │    Full data — list price + price floor +    │
│ ● Config       │    exact bulk tier %s + delivery options     │
│                │                                              │
│ ← Exit         │  Negotiations tab:                           │
│ Powered by     │    History of all completed sessions         │
│ Google Cloud   │    Status, product, persona, final price     │
└────────────────┴──────────────────────────────────────────────┘
```

**Negotiate tab — live chat (once session starts):**
```
┌────────────────────────────────────────────────────────────────┐
│  Sony WH-1000XM6 · AI · budget shopper · Session 3f2a1b…      │
│  ● Active                                                      │
├────────────────────────────────────────────────────────────────┤
│  Shopping Agent (Counterparty)      Merchant Agent (MadeinMind)│
│                                                                │
│  [Budget Shopper]                                             │
│  "I'd like 25 units. Can you                                  │
│   do $82 per unit?"                                           │
│                                              [Counter Offer]  │
│                                    "Thanks for your interest! │
│                                     For 25 units I can offer  │
│                                     $92.99 + standard ship."  │
│  [Counter Offer]                                              │
│  "Let's try $87. Can we                                       │
│   add 2-day delivery?"                                        │
│                                              [Final Offer ★]  │
│                                    "My final offer: $89.99,   │
│                                     2-day delivery included." │
│  [Accepted ✓]                                                 │
│  "Deal! Let's go."                                            │
├────────────────────────────────────────────────────────────────┤
│  🤝 Deal Closed! · $89.99/unit · qty 25 · 2-day delivery      │
└────────────────────────────────────────────────────────────────┘
```

**Human Mode:** text input bar appears at bottom; shopping agent messages come from the user.
**Shopping Agent framing:** clearly labelled "Counterparty" — mode and persona are demo-only controls.

---

## 6. Google Cloud Services Map

| Service | Role |
|---|---|
| **Gemini 2.5 Flash** | Merchant Agent reasoning, deal scoring, counter-offer generation |
| **Gemini 2.5 Flash-Lite** | Shopping Agent persona reasoning (AI mode) |
| **Cloud Run** | Python FastAPI orchestration layer; A2A routing; SSE streaming; state machine |
| **Firebase Hosting** | Demo UI front-end (React static build) |
| **Firestore** | Product catalogue, negotiation session storage |
| **Secret Manager** | API keys, model config, pricing thresholds |
| **Cloud Logging** | Full A2A message audit trail |

> **Removed:** Firebase Realtime Database — replaced by SSE from the FastAPI orchestrator (simpler, no extra SDK required).
> **Removed:** Vertex AI Agent Builder — agents run directly inside Cloud Run via the Gemini API (sufficient for demo scale).
| **Artifact Registry** | Container images for Cloud Run services |

---

## 7. Data Models

### 7.1 Product Catalogue (Firestore)
```json
{
  "sku": "SKU-001",
  "name": "Sony WH-1000XM6",
  "list_price": 99.99,
  "price_floor": 79.99,
  "stock": 500,
  "inventory_reserve": 100,
  "bulk_tiers": [
    { "min_qty": 10, "discount_pct": 8 },
    { "min_qty": 50, "discount_pct": 15 }
  ],
  "delivery_options": ["standard_5d", "express_2d", "next_day"],
  "vouchers_eligible": true
}
```

### 7.2 Negotiation Session (Firestore)
```json
{
  "session_id": "uuid",
  "mode": "ai | human",
  "persona": "budget_shopper | premium_buyer | bulk_purchaser | null",
  "product_sku": "SKU-001",
  "turns": [...],
  "status": "active | accepted | rejected | expired",
  "final_deal": { ... },
  "created_at": "ISO8601"
}
```

---

## 8. Negotiation Logic — Merchant Agent Rules

| Rule | Detail |
|---|---|
| Anchor Price | Always opens at or near list price |
| Discount Band | Autonomous up to configurable threshold (default 20%) |
| Bulk Sweetener | Auto-applies tier pricing when quantity crosses threshold |
| Delivery Trade-off | Offers faster delivery in exchange for reduced discount |
| Loyalty Sweetener | Offers voucher/points if buyer is close to acceptance |
| Final Offer | At turn N-1, emits a `final_offer` intent — no further movement |
| Hard Rejection | If buyer exceeds all thresholds, agent politely declines and closes session |

---

## 9. Demo Script (Suggested Flow)

### Phase 1 — AI vs AI (2 min)
1. Select product, choose "Bulk Purchaser" persona, set to AI Mode
2. Hit **Start Negotiation**
3. Watch both agents negotiate in real time — 6–8 turns
4. Deal closes autonomously — show deal summary panel

### Phase 2 — Human vs Merchant Agent (2 min)
1. Toggle to Human Mode
2. Type buyer messages manually ("Can you do better on price?", "What if I take 50 units?")
3. Merchant Agent responds autonomously each turn
4. Push an aggressive ask to see the agent issue a firm Final Offer and close the deal

### Phase 3 — Architecture Walkthrough (1 min)
1. Show Cloud Logging: full A2A message trace per turn
2. Show Vertex AI: active agent sessions
3. Show Cloud Logging: SSE event stream and A2A message trace

---

## 10. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Turn response latency | < 3 seconds (Gemini 2.5 Flash-Lite for Shopping), < 4s (Gemini 2.5 Flash for Merchant) |
| UI update latency | < 500ms (SSE push from FastAPI — no polling) |
| Demo reliability | 99%+ uptime during demo window (Cloud Run min instances = 1) |
| Session statefulness | Full turn history maintained per session |
| Scalability | Not a concern for demo; single-tenant is fine |

---

## 11. Phased Build Plan

### Phase 1 — Core Agents & A2A ✅ COMPLETE
> Stack: Python 3.14, FastAPI, google-genai SDK, firebase-admin, Pydantic v2
> Tests: 80/80 passing (fully mocked — no real services needed to run tests)

- [x] Define A2A message schema (`models.py` — Pydantic models)
- [x] Build negotiation state machine (`state_machine.py` — turn progression, alternation, expiry)
- [x] Gemini API wrapper (`gemini.py` — async, prompt loading, JSON parsing, fallback)
- [x] Write system prompts for Merchant Agent and 3 buyer personas (`orchestrator/prompts/`)
- [x] Implement Merchant Agent rules engine + Gemini call (`merchant.py`)
  - Price floor, bulk tiers (10+ / 50+ units), delivery negotiation, loyalty voucher
  - Two-layer design: rules engine decides numbers, Gemini generates prose
- [x] Implement Shopping Agent — AI persona + human relay (`shopping.py`)
- [x] Firebase + Firestore integration (`firebase_db.py` — session CRUD, live turn push)
- [x] FastAPI orchestration layer (`main.py` — 4 endpoints)
- [x] Product catalogue: 4 SKUs (Sony, Apple, Samsung, Logitech)
- [x] Cleaned up folder structure (removed redundant `merchant-agent/`, `shopping-agent/`, `shared/`)

**Decisions made during Phase 1:**
- Backend language: **Python** (not Node.js)
- Gemini SDK: **google-genai** v2.27+ (replaced deprecated `google-generativeai`)
- Product catalogue: **4 products** (not fixed single SKU — OQ1 resolved)
- Demo mode: **Live on GCP** (OQ4 resolved — no offline/air-gapped path)

### Phase 2 — React UI ✅ COMPLETE (dry-run verified)
> Stack: React + Vite (Node v24), Tailwind CSS via CDN, native EventSource API (no Firebase JS SDK)
> Live streaming: SSE from FastAPI `/session/{id}/stream` endpoint
> Branding: MadeinMind · NegotiateIQ · Google colour palette (dark theme)
> DRY_RUN mode: runs fully without GCP credentials — in-memory sessions + canned Gemini responses

**Orchestrator changes:**
- [x] SSE endpoint `GET /session/{id}/stream` in `main.py`
- [x] In-memory asyncio.Queue per session for SSE events
- [x] Firebase Realtime DB stripped from `firebase_db.py` (Firestore only)
- [x] `DRY_RUN=true` mode in `gemini.py` + `firebase_db.py` for local demo without GCP creds
- [x] `orchestrator/.env` with `DRY_RUN=true` (gitignored)
- [x] 25/25 tests passing

**React UI:**
- [x] Sidebar navigation — role-based (buyer: Products + Negotiate; merchant: Dashboard + Products + Negotiations + Config)
- [x] `api.js` — `startSession()`, `runTurn()`, `openStream()` (EventSource)
- [x] `ProductsScreen.jsx` — buyer view: 2×2 product card grid, no price floor shown, volume discount badge only
- [x] `MerchantProductsScreen.jsx` — merchant view: full internal data (price floor, exact bulk tier %s)
- [x] `MerchantConfigScreen.jsx` — merchant rules dashboard (read-only, matches Python rules engine)
- [x] `NegotiationScreen.jsx` — two-column setup + live chat; fires `onSessionComplete(summary)` on session end
- [x] `TurnMessage.jsx` — message bubble, Google colour intent badges
- [x] `DealSummary.jsx` — outcome card (accepted / rejected / expired)
- [x] `MerchantLogin.jsx` — password gate (demo: `merchant123`); full-screen, no sidebar
- [x] `MerchantDashboard.jsx` — session metrics (total, win rate, avg discount, outcome breakdown, recent sessions table)
- [x] `App.jsx` — role state (`buyer` | `login` | `merchant`); completedSessions array; negotiation history inline
- [x] `Sidebar.jsx` — two nav configs; merchant login link (buyer) / logout button (merchant)
- [x] `npm run build` clean — 40 modules, 0 errors
- [x] Dry-run verified: FastAPI (:8000) + Vite (:5173) both confirmed live

### Phase 3 — Polish & Demo Hardening
- [ ] Seed 4-product catalogue into Firestore (`firestore/seed-products.js`)
- [ ] Add deal summary + export panel in UI
- [ ] Add Cloud Logging audit trail view
- [ ] Stress-test demo flow (3 personas × 2 modes)
- [ ] Deploy orchestrator to Cloud Run (min instances = 1)
- [ ] Deploy UI to Firebase Hosting
- [ ] Rehearse demo script (Sections 9 and 15)

---

## 12. Open Questions / Decisions

| # | Question | Status | Decision |
|---|---|---|---|
| OQ1 | Product catalogue fixed or dynamic? | ✅ Resolved | 4 curated demo SKUs (Sony, Apple, Samsung, Logitech) |
| OQ2 | Should deal history persist across demo sessions or reset? | ⏳ Open | Each session has its own UUID; UI will show current session only. Cross-session history is FS4 (future scope). |
| OQ3 | Slide-deck-style explainer overlay in UI? | 🔜 Future Scope | Deferred — added as FS8 in Section 16 |
| OQ4 | Live (online) or air-gapped (local)? | ✅ Resolved | Live on GCP — no offline fallback path needed |

---

## 13. GCP First-Timer Setup Guide
> **Who this is for:** Complete step-by-step for someone setting up Google Cloud for the first time. Every step is numbered and must be done in order. No step assumes prior GCP knowledge.

### What You Actually Need (and Why)

Before touching anything, here is a plain-English map of what each Google service does in this project and why you need it:

| Service | What it is in plain English | Why NegotiateIQ needs it |
|---|---|---|
| **Google Cloud Project** | A container/folder that groups all your cloud resources and billing together | Every GCP service you use must belong to a project |
| **Vertex AI** | Google's platform for running AI models and agents in the cloud | Hosts both the Merchant Agent and Shopping Agent |
| **Gemini (via Vertex AI)** | The actual LLM brain that powers agent reasoning | Generates negotiation responses, counter-offers, deal scoring |
| **Cloud Run** | Runs your backend code as a container — no server to manage | Hosts the A2A orchestration layer that routes messages between agents |
| **Firestore** | A cloud database (like a smart JSON store) | Stores product catalogue, negotiation sessions, deal history |
| **Firebase Realtime Database** | A database that pushes live updates to browsers instantly | Streams each negotiation turn to the UI in real time |
| **Firebase Hosting** | Static website hosting with a CDN | Serves the React demo UI |
| **Secret Manager** | A secure vault for API keys and passwords | Stores Gemini API keys so they are never hardcoded |
| **Artifact Registry** | Stores your Docker container images | Cloud Run pulls your container from here to deploy it |
| **Cloud Logging** | Captures all logs from every service | Shows the full A2A message audit trail during the demo |

---

### Step-by-Step: GCP Account & Project Setup

#### STAGE 1 — Google Account & Billing (Do Once, Takes ~15 min)

**Step 1: Use or create a Google account**
- Use a personal Gmail that has NEVER activated a Google Cloud free trial before
- If your main Gmail has been used before, create a new one — the $300 credit is per account, first-time only

**Step 2: Activate the Google Cloud Free Trial**
1. Go to `https://cloud.google.com/free`
2. Click **Get started for free**
3. Sign in with your Google account
4. Enter your country (India) and agree to terms
5. Enter a credit card — this is required to verify identity but **you will NOT be charged** until you manually upgrade and spend all $300
6. You now have $300 in credits valid for 90 days

**Step 3: Create a GCP Project**
1. Go to `https://console.cloud.google.com`
2. Click the project dropdown at the top → **New Project**
3. Project name: `negotiateiq`
4. Leave organisation as-is
5. Click **Create**
6. Wait ~30 seconds, then select `negotiateiq` from the project dropdown
7. Note your **Project ID** (shown under the project name) — you will use this in almost every command. It looks like `negotiateiq-123456`

**Step 4: Enable billing on the project**
1. In the GCP Console left menu → **Billing**
2. Click **Link a billing account** → select the billing account created in Step 2
3. This connects your $300 credits to this project

**Step 5: Set a billing budget alert (important — do this before anything else)**
1. Billing → **Budgets & Alerts** → **Create Budget**
2. Set three alerts: $50, $150, $250
3. Add your email for notifications
4. This ensures you never accidentally overspend the $300

---

#### STAGE 2 — Enable APIs (Do Once, Takes ~5 min)

All the GCP services you use must be "enabled" for your project first. Think of this as switching on features.

**Step 6: Enable all required APIs in one go**

Go to `https://console.cloud.google.com/apis/library` and search for + enable each of these:

| API to enable | Search term |
|---|---|
| Vertex AI API | `Vertex AI` |
| Cloud Run Admin API | `Cloud Run` |
| Cloud Build API | `Cloud Build` |
| Artifact Registry API | `Artifact Registry` |
| Secret Manager API | `Secret Manager` |
| Firebase Management API | `Firebase` |
| Cloud Firestore API | `Firestore` |
| Cloud Logging API | `Cloud Logging` (usually pre-enabled) |

Or run this single command in Cloud Shell (the terminal icon `>_` at the top right of GCP Console) to enable them all at once:

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  firebase.googleapis.com \
  firestore.googleapis.com \
  logging.googleapis.com
```

---

#### STAGE 3 — Firebase Setup (Do Once, Takes ~10 min)

Firebase is Google's app platform — it sits on top of GCP and shares the same project.

**Step 7: Create a Firebase project linked to your GCP project**
1. Go to `https://console.firebase.google.com`
2. Click **Add project**
3. Select your existing GCP project `negotiateiq` from the dropdown (do NOT create a new project — link to existing)
4. Follow the prompts, disable Google Analytics (not needed)
5. Click **Continue** — Firebase is now linked to your GCP project

**Step 8: Enable Firebase services**

Inside Firebase Console (`console.firebase.google.com` → select `negotiateiq`):

- **Realtime Database:** Build → Realtime Database → Create Database → choose `asia-south1` (Mumbai, closest to Pune) → Start in **test mode** for now
- **Firebase Hosting:** Build → Hosting → Get started (follow the short wizard)

**Step 9: Get your Firebase web config**
1. Firebase Console → Project Settings (gear icon) → General → Your apps
2. Click **Add app** → Web (`</>` icon)
3. App nickname: `negotiateiq-ui`
4. Copy the config object that appears — you'll paste this into your React app's `.env` file later. It looks like:
```javascript
const firebaseConfig = {
  apiKey: "AIza...",
  authDomain: "negotiateiq.firebaseapp.com",
  databaseURL: "https://negotiateiq-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "negotiateiq-123456",
  ...
};
```

---

#### STAGE 4 — Local Machine Setup (Do Once, Takes ~20 min)

Install these tools on your laptop in this order:

**Step 10: Install core tools**

| Tool | How to install | What it's for |
|---|---|---|
| **VS Code** | `https://code.visualstudio.com` | Your code editor |
| **Node.js v20+** | `https://nodejs.org` (LTS version) | Runs the React UI and JS backend |
| **Python 3.11+** | `https://python.org` (if using Python backend) | Optional, for Python orchestrator |
| **Git** | `https://git-scm.com` | Version control |
| **Docker Desktop** | `https://docker.com/products/docker-desktop` | Build containers for Cloud Run |
| **gcloud CLI** | `https://cloud.google.com/sdk/docs/install` | Talk to GCP from your terminal |
| **Firebase CLI** | `npm install -g firebase-tools` (after Node is installed) | Deploy to Firebase |

**Step 11: Authenticate gcloud CLI with your Google account**
```bash
gcloud auth login
# A browser window opens — sign in with the same Google account used for GCP
gcloud config set project negotiateiq-123456
# Replace negotiateiq-123456 with YOUR actual project ID
gcloud auth application-default login
# This sets up credentials for local code to call GCP APIs (Vertex AI etc.)
```

**Step 12: Authenticate Firebase CLI**
```bash
firebase login
# A browser window opens — sign in with the same Google account
firebase projects:list
# You should see negotiateiq in the list
```

**Step 13: Install VS Code extensions**

Open VS Code → Extensions (`Ctrl+Shift+X`) → Search and install:
- `Google Cloud Code` — GCP integration inside VS Code
- `ESLint` — code quality
- `Prettier` — code formatting
- `Docker` — container file support
- `Firebase` — Firebase tools integration
- `GitLens` — better Git visibility

---

#### STAGE 5 — GitHub Repository Setup (Do Once, Takes ~10 min)

**Step 14: Create the GitHub repository**
1. Go to `https://github.com/new`
2. Repository name: `negotiateiq`
3. Set to **Private** (you are in a competition)
4. Add a README
5. Click **Create repository**

**Step 15: Clone and set up the folder structure locally**
```bash
git clone https://github.com/YOUR_USERNAME/negotiateiq.git
cd negotiateiq
```

Create this folder structure in VS Code:
```
negotiateiq/
├── orchestrator/           # Python FastAPI backend — all agent logic lives here
│   ├── src/
│   │   ├── main.py         # FastAPI app (4 endpoints)
│   │   ├── models.py       # Pydantic data shapes (A2AMessage, NegotiationSession …)
│   │   ├── state_machine.py# Turn progression and negotiation lifecycle
│   │   ├── merchant.py     # Merchant Agent: rules engine + Gemini call
│   │   ├── shopping.py     # Shopping Agent: AI persona or human relay
│   │   ├── gemini.py       # Thin async Gemini API wrapper (google-genai SDK)
│   │   └── firebase_db.py  # Firestore integration (session + product persistence)
│   ├── prompts/            # System prompts for Merchant Agent and buyer personas
│   │   ├── merchant_system.txt
│   │   ├── persona_budget_shopper.txt
│   │   ├── persona_premium_buyer.txt
│   │   └── persona_bulk_purchaser.txt
│   ├── tests/              # Unit + smoke tests (80 tests, all passing)
│   ├── requirements.txt    # Python deps (FastAPI, google-genai, firebase-admin …)
│   ├── Dockerfile          # Python slim image for Cloud Run
│   └── .env.example        # Template for env vars — safe to commit
├── ui/                     # React Firebase frontend (Phase 2)
│   ├── src/
│   └── public/
├── functions/              # Cloud Functions placeholder (future: escalation handler FS1)
│   └── index.js
├── firestore/              # Firestore schema reference + seed scripts
│   ├── seed-products.js    # Loads 4 demo products into Firestore
│   └── schema.md
├── infra/                  # Deployment scripts
│   ├── deploy-cloudrun.sh
│   └── deploy-firebase.sh
├── docs/                   # Documentation
│   └── spec.md             # ← This file lives here
├── .gitignore
└── README.md
```

> **Note:** `merchant-agent/`, `shopping-agent/`, and `shared/` folders were removed.
> All agent logic, config, and prompts live inside `orchestrator/` — a single deployable unit.
> The A2A message schema is defined as Pydantic models in `orchestrator/src/models.py`.

**Step 16: Set up .gitignore immediately — before any code**
```
# .gitignore
.env
.env.local
*.env
node_modules/
__pycache__/
*.pyc
.firebase/
service-account-key.json
*-key.json
```
> ⚠️ **Critical:** Never commit `.env` files or any JSON key files. This exposes your credentials publicly.

**Step 17: Push the structure to GitHub**
```bash
git add .
git commit -m "chore: initial project structure"
git push origin main
```

---

#### STAGE 6 — Local Dev Environment Variables

**Step 18: Create .env files for local development**

In `orchestrator/.env` (never committed — use `.env.example` as template):
```bash
# Set DRY_RUN=true for local testing without real GCP credentials.
# Set DRY_RUN=false (or remove) when deploying with a real Gemini key + Firestore.
DRY_RUN=false

# Gemini (AI Studio key for local dev; Vertex AI service account on Cloud Run)
GEMINI_API_KEY=your_ai_studio_key_here

# Firestore (session + product persistence)
FIREBASE_PROJECT_ID=negotiateiq-123456

# GCP
GCP_PROJECT_ID=negotiateiq-123456
GCP_REGION=asia-south1
```

> **Note:** `FIREBASE_DATABASE_URL` / Firebase Realtime Database has been removed.
> Live turn streaming is handled by SSE directly from the FastAPI orchestrator.

In `orchestrator/.env.example` (committed to GitHub as a template):
```bash
DRY_RUN=false
GEMINI_API_KEY=your_key_here
FIREBASE_PROJECT_ID=your_gcp_project_id_here
GCP_PROJECT_ID=your_gcp_project_id_here
GCP_REGION=asia-south1
```

---

#### STAGE 7 — Writing Code That Works Both Locally and on GCP

This is the key principle: **your code should never need to change when moving from local to GCP.** Achieve this by using environment variables and the official Google SDKs, which automatically handle both local credentials and cloud credentials.

**The golden rule:**
```
Local dev  → reads from .env file → calls Gemini via AI Studio key
GCP deploy → reads from Secret Manager + service account → calls Gemini via Vertex AI
```

Your code reads `process.env.GEMINI_API_KEY` either way — the value just comes from a different source.

**Local → GCP transition checklist (per service):**

| Service | Local (Dev) | GCP (Demo) | Code change needed? |
|---|---|---|---|
| Gemini LLM | AI Studio API key in `.env` | Vertex AI via `gcloud auth` | Swap SDK call, same logic |
| Database | Firebase Emulator on `localhost:8080` | Firestore on GCP | Change env var only |
| Auth | Firebase Emulator | Firebase Auth (production) | Change env var only |
| Secrets | `.env` file | Secret Manager | No code change |
| Logging | `console.log` | Cloud Logging (automatic) | No code change |

---

## 14. Local Development with Free LLMs
> **Goal:** Test and build the full negotiation logic locally without spending any credits and without needing internet access to GCP.

You have three options for local LLM use. Start with Option A, move to B or C as needed.

---

### Option A — Gemini via AI Studio API Key (Recommended Starting Point)

The easiest path. Get a free API key from Google AI Studio and call Gemini 2.5 Flash directly. No GCP account needed, no credit card, nothing to install.

**Step 1: Get your free API key**
1. Go to `https://aistudio.google.com`
2. Sign in with your Google account
3. Click **Get API key** (top left) → **Create API key**
4. Select **Create API key in new project** (or link to your GCP project if already set up)
5. Copy the key — it starts with `AIza...`
6. Paste into `orchestrator/.env` as `GEMINI_API_KEY=AIza...`

**Step 2: Install the SDK**
```bash
# Node.js
npm install @google/genai

# Python
pip install google-generativeai
```

**Step 3: Call Gemini in your code**
```javascript
// Node.js — orchestrator/src/gemini.js
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

export async function callMerchantAgent(negotiationContext) {
  const response = await ai.models.generateContent({
    model: "gemini-2.5-flash",   // free tier model
    contents: negotiationContext,
    config: {
      systemInstruction: MERCHANT_SYSTEM_PROMPT,  // your agent prompt
    }
  });
  return response.text;
}
```

```python
# Python equivalent — orchestrator/src/gemini.py
import google.generativeai as genai
import os

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=MERCHANT_SYSTEM_PROMPT
)

def call_merchant_agent(negotiation_context: str) -> str:
    response = model.generate_content(negotiation_context)
    return response.text
```

**Free tier limits to keep in mind during dev:**

| Limit | Value | What it means for you |
|---|---|---|
| Requests per minute | 15 RPM | If you're running rapid tests in a loop, add a 4-second sleep between calls |
| Requests per day | ~1,500 RPD | ~750 full negotiation turns/day (2 agent calls per turn) — plenty for dev |
| Tokens per minute | 1,000,000 | Effectively unlimited for this use case |
| Data privacy | ⚠️ Google may use inputs for training | Fine for dev/testing. Switch to Vertex AI for the actual demo |

**How to switch to Vertex AI later (when deploying to GCP):**
```javascript
// Change only these two lines — rest of your code stays identical
import { VertexAI } from "@google-cloud/vertexai";
const vertexai = new VertexAI({ project: process.env.GCP_PROJECT_ID, location: "asia-south1" });
const model = vertexai.preview.getGenerativeModel({ model: "gemini-2.5-flash" });
```

---

### Option B — Gemma via Ollama (Fully Offline, No API Key Needed)

Use Google's open-source Gemma model running entirely on your laptop. No internet needed, no rate limits, no cost — ever. Good for when you want to test negotiation logic rapidly without any external calls.

**Step 1: Install Ollama**
```bash
# Download from https://ollama.com or:
curl -fsSL https://ollama.com/install.sh | sh   # Mac/Linux
# Windows: download installer from https://ollama.com/download
```

**Step 2: Pull a Gemma model**
```bash
# Gemma 3 — Google's latest open model (recommended)
ollama pull gemma3:4b       # ~3GB download, runs on most laptops (8GB RAM min)
ollama pull gemma3:12b      # ~8GB download, better quality, needs 16GB RAM
```

**Step 3: Run Ollama server**
```bash
ollama serve
# Ollama now runs at http://localhost:11434
# Keep this terminal open
```

**Step 4: Call Gemma from your code**
```javascript
// Node.js — drop-in replacement for the Gemini call during local testing
async function callMerchantAgentLocal(negotiationContext) {
  const response = await fetch("http://localhost:11434/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "gemma3:4b",
      prompt: `${MERCHANT_SYSTEM_PROMPT}\n\n${negotiationContext}`,
      stream: false
    })
  });
  const data = await response.json();
  return data.response;
}
```

**Step 5: Toggle between local (Gemma) and cloud (Gemini) via env var**
```javascript
// orchestrator/src/agent.js
const USE_LOCAL_MODEL = process.env.USE_LOCAL_MODEL === "true";

export async function callMerchantAgent(context) {
  if (USE_LOCAL_MODEL) {
    return callMerchantAgentLocal(context);   // Ollama / Gemma
  } else {
    return callMerchantAgentCloud(context);   // Gemini via AI Studio or Vertex
  }
}
```

In `.env`:
```bash
USE_LOCAL_MODEL=true    # during offline dev
USE_LOCAL_MODEL=false   # when testing with real Gemini / before demo
```

**Honest trade-off:** Gemma 3 4B is good but noticeably less capable than Gemini 2.5 Flash for complex multi-turn reasoning. Use it for structural/flow testing (does the A2A message routing work? does the state machine progress?), not for judging the quality of negotiation responses.

---

### Option C — Firebase Emulator Suite (For Database & Auth, Not LLM)

This is not an LLM option — it's for mocking the Firebase backend locally so your UI and database logic work without touching production Firebase at all.

**Step 1: Install**
```bash
npm install -g firebase-tools
cd negotiateiq
firebase init emulators
# Select: Firestore, Realtime Database, Hosting
```

**Step 2: Start emulators**
```bash
firebase emulators:start
# Emulator UI at http://localhost:4000
# Realtime DB at http://localhost:9000
# Firestore at http://localhost:8080
```

**Step 3: Point your app at emulators in dev**
```javascript
// ui/src/firebase.js
import { initializeApp } from "firebase/app";
import { getDatabase, connectDatabaseEmulator } from "firebase/database";

const app = initializeApp(firebaseConfig);
const db = getDatabase(app);

if (process.env.NODE_ENV === "development") {
  connectDatabaseEmulator(db, "localhost", 9000);  // local emulator
}
// In production (GCP), this block is skipped — connects to real Firebase
export { db };
```

No code change needed when going to production — the `NODE_ENV` check handles it automatically.

---

### Recommended Local Dev Workflow

```
Day 1–3:   USE_LOCAL_MODEL=true  +  Firebase Emulators
           → Build A2A routing, state machine, UI — zero cost, zero internet needed

Day 4–7:   USE_LOCAL_MODEL=false + GEMINI_API_KEY (AI Studio)  +  Firebase Emulators
           → Validate real negotiation quality, test prompts, refine agent reasoning

Day 8–14:  USE_LOCAL_MODEL=false + GEMINI_API_KEY (AI Studio)  +  Real Firebase (GCP)
           → End-to-end integration test before GCP deploy

Day 14+:   Deploy to GCP — switch to Vertex AI, everything else stays the same
```

---

## 15. Success Criteria

A successful demo will:
1. Run a complete AI-vs-AI negotiation in < 3 minutes with no errors
2. Demonstrate a human-driven negotiation turn seamlessly
3. Show the Merchant Agent issue a firm Final Offer and auto-close the deal
4. Show the Cloud Logging audit trail of A2A messages
5. Leave the audience with a clear mental model of how A2A protocol enables agent commerce on Google Cloud

---

## 16. Future Scope
> These features are intentionally out of scope for the hackathon demo but are documented here as planned enhancements for a production version of NegotiateIQ.

| # | Feature | Description |
|---|---|---|
| FS1 | **Human Manager Escalation** | When the Merchant Agent encounters a deal that exceeds all configured thresholds (discount, quantity, SLA), it pauses and escalates to a human manager via Pub/Sub + Cloud Functions. The manager reviews via an auth-gated Firebase page and approves, rejects, or modifies the deal before the agent resumes. Requires: Firebase Auth, Cloud Pub/Sub, Cloud Functions. |
| FS2 | **Firebase Authentication** | Role-based login (shopper, manager, admin) to gate different pages and personalise the negotiation experience. |
| FS3 | **Multi-product Basket Negotiation** | Extend the A2A schema to support negotiating a basket of multiple SKUs in a single session rather than one product at a time. |
| FS4 | **Persistent Deal History** | Full deal history dashboard across sessions — track win rate, average discount given, most contested SKUs over time. |
| FS5 | **Agent Fine-tuning** | Fine-tune the Merchant Agent on historical deal data to sharpen pricing intuition and improve persona-specific response quality. |
| FS6 | **Webhook Integrations** | Post completed deal summaries to external systems (Slack, ERP, CRM) via Cloud Functions on deal acceptance. |
| FS7 | **Voice Mode** | Allow the Human shopping mode to use speech input/output via the Web Speech API, making the demo more interactive in a live setting. |
| FS8 | **Demo Explainer Overlay** | A real-time "director's commentary" panel overlaid on the UI during demos. Shows the A2A message intent, which GCP service is active (Gemini, Cloud Run, Firebase), and what is happening behind each turn — aimed at a technical audience unfamiliar with A2A protocol. |

---

*NegotiateIQ — Built on Google Cloud. Powered by Gemini. Negotiated by agents.*
