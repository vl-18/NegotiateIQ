# Build Log

## Done
- [2026-10-02] Created `CLAUDE.md` with project coding instructions.
- [2026-10-02] Created `build_log.md` to track progress.
- [2026-10-02] Created full project directory structure:
  - `merchant-agent/` — config + prompts placeholder
  - `shopping-agent/` — config + personas placeholder
  - `orchestrator/` — Dockerfile, `.env.example`, src placeholder
  - `ui/` — src + public placeholders
  - `shared/` — A2A message JSON schema
  - `firestore/` — schema.md + seed-products.js
  - `functions/` — escalation handler placeholder (future scope)
  - `infra/` — deploy scripts for Cloud Run and Firebase
  - `docs/` — spec.md moved here
  - `.gitignore`, `README.md`

## Pending

### Phase 1 — Core Agents & A2A (orchestrator)
- [x] `models.py` — all Pydantic data models (A2AMessage, NegotiationSession, enums, API request types) — 7/7 tests pass
- [x] `requirements.txt` — pydantic>=2.10, fastapi, uvicorn, google-generativeai, firebase-admin, python-dotenv
- [x] venv set up at `orchestrator/venv/` (Python 3.14.3)
- [x] `state_machine.py` — turn progression, alternation enforcement, final-offer flag, expiry — 12/12 tests pass
- [x] `gemini.py` — async Gemini wrapper (google-genai SDK), prompt loading, JSON parsing — 9/9 tests pass
- [x] Prompts written: `merchant_system.txt`, `persona_budget_shopper.txt`, `persona_premium_buyer.txt`, `persona_bulk_purchaser.txt`
- [x] Switched from deprecated `google-generativeai` → `google-genai` SDK
- [x] `merchant.py` — rules engine (bulk tiers, price floor, delivery, voucher), context builder, Gemini integration, fallback — 15/15 tests pass
- [x] `shopping.py` — AI mode (Gemini + persona), human mode (A2A relay), router, fallback — 13/13 tests pass (1 bug found and fixed: whitespace stripping moved to source)
- [x] `firebase_db.py` — Firestore (session + product CRUD), Realtime DB (live turn push, status update), full round-trip serialisation — 12/12 tests pass
- [x] `main.py` — FastAPI app: /session/start, /session/{id}/turn, /session/{id}/status, /health — 12/12 tests pass

### Phase 1 complete — 80/80 tests passing across all orchestrator modules

- [x] Cleaned up redundant folders: removed `merchant-agent/`, `shopping-agent/`, `shared/` (all superseded by orchestrator modules)

### Phase 2 — React UI
> Stack: React + Vite (Node v24 / npm v11), Tailwind CSS, native browser EventSource (no Firebase JS SDK)
> Live streaming: SSE via FastAPI — Firebase Realtime DB dropped (simpler, no extra SDK)
> OQ3 (explainer overlay) → deferred as FS8 in spec.md Section 16

**Part 8 — Orchestrator SSE additions (before UI)**
- [x] Add `GET /session/{id}/stream` SSE endpoint to `main.py`
- [x] Add in-memory asyncio.Queue per session for turn events
- [x] Strip `push_turn()` + `push_session_status()` Realtime DB calls from `firebase_db.py`
- [x] SSE test assertion fixed (close event `data: {}` correctly distinguished from turn events)
- [x] 25/25 tests passing (test_main.py + test_firebase_db.py)

**Part 9 — React UI (initial scaffold)**
- [x] Scaffold React + Vite app in `ui/` (files written directly — no CLI scaffold needed)
- [x] `api.js` — startSession(), runTurn(), openStream() (EventSource wrapper)
- [x] `TurnMessage.jsx` — message bubble with intent badge and proposed terms
- [x] `DealSummary.jsx` — outcome panel (accepted / rejected / expired) + final deal terms
- [x] Tailwind CSS via CDN play (no build step needed for demo)
- [x] `npm run build` clean — 35 modules, 0 errors

**Part 9b — DRY_RUN mode (local demo without GCP credentials)**
- [x] `DRY_RUN=true` env var support added to `gemini.py` — skips Gemini client init, returns canned JSON responses
  - Merchant agent: fixed display_text placeholder (numbers still from rules engine)
  - Shopping agent: persona-tuned opening counter-offer; accepts on merchant's final_offer
- [x] `DRY_RUN=true` env var support added to `firebase_db.py` — skips Firebase init, uses in-memory dicts
  - In-memory session store (`_sessions` dict)
  - Hardcoded 4-product catalogue (`_DRY_RUN_PRODUCTS`) matching real Firestore schema
- [x] `orchestrator/.env` created with `DRY_RUN=true` + placeholder keys (gitignored)
- [x] Backend confirmed: `uvicorn main:app --app-dir src` starts cleanly; `/health` returns 200

**Part 9c — UI redesign (sidebar navigation + MadeinMind branding)**
- [x] Full UI redesign: sidebar-based layout replacing single-page setup screen
- [x] `Sidebar.jsx` — fixed left nav with MadeinMind logo (Google 4-colour dot mark), 3 tabs, Google colour accents, "Powered by Google Cloud" footer
- [x] `ProductsScreen.jsx` — 2×2 product card grid; click to select + jump to Negotiate tab; shows list price, floor, bulk tiers, voucher eligibility
- [x] `MerchantConfigScreen.jsx` — merchant rules dashboard: agent identity (Alex / MadeinMind Commerce), pricing rules, bulk tier table, delivery options, negotiation parameters — read-only for demo
- [x] `NegotiationScreen.jsx` — two-column setup panel (Merchant side read-only | Counterparty shopping agent configurable); switches to full-width chat once session starts
- [x] Shopping Agent clearly labelled "Counterparty" — mode + persona configured here for demo; framing makes clear this is the other party
- [x] `TurnMessage.jsx` updated — Google colour palette (yellow for shopping, green for merchant, blue/red/purple intent badges)
- [x] `DealSummary.jsx` updated — Google colour outcomes; inline with ChatPanel
- [x] `App.jsx` rewritten — state: activeTab, selectedProduct, session; product selection navigates to Negotiate tab automatically
- [x] Back navigation: "← Change product" link + sidebar tab clicks work anywhere
- [x] `npm run build` clean — 37 modules, 0 errors
- [x] Both servers confirmed live: FastAPI on :8000, Vite dev server on :5173

**Documentation**
- [x] `docs/merchant_agent.md` — merchant agent reference: two-layer design, rules engine walkthrough, key constants, how-to-update guide
- [x] `docs/shopping_agent.md` — shopping agent reference: AI vs human mode, persona system, intent parsing, how-to-update guide
- [x] `docs/pipeline.md` — end-to-end pipeline: session start → SSE stream → turn execution → session end; file map; bug tracing guide

**Part 9e — Split into two separate UI apps (Option A: single repo, two Vite entry points)**
- [x] `ui/src/App.jsx` — stripped to buyer-only (Products + Negotiate, no role state, no merchant imports)
- [x] `ui/src/MerchantApp.jsx` — new standalone merchant app: login gate + MerchantSidebar + screens
  - Fetches sessions from `GET /api/sessions` (backend) — no shared React state with buyer
  - Normalises API snake_case to camelCase for existing dashboard components
  - Inline `NegotiationHistory` table + `MerchantSidebar` (no extra files needed)
- [x] `ui/src/main.merchant.jsx` — new entry point that mounts `MerchantApp`
- [x] `ui/src/components/Sidebar.jsx` — stripped to buyer-only nav (no role props, no merchant login link)
- [x] `ui/src/components/NegotiationScreen.jsx` — removed price floor from buyer-facing setup panel
- [x] `ui/src/api.js` — added `fetchSessions()` → `GET /sessions`
- [x] `orchestrator/src/firebase_db.py` — added `list_sessions()` (DRY_RUN: returns all in-memory sessions; production: Firestore `.stream()`)
- [x] `orchestrator/src/main.py` — added `GET /sessions` endpoint returning session summaries with product info
- [x] `ui/index.merchant.html` — merchant HTML entry (title: NegotiateIQ — Merchant Portal)
- [x] `ui/vite.config.js` — added `build.outDir: "dist/buyer"`, explicit port 5173
- [x] `ui/vite.merchant.config.js` — new config: port 5174, entry `index.merchant.html`, outDir `dist/merchant`
- [x] `ui/package.json` — scripts: `dev:buyer` (:5173), `dev:merchant` (:5174), `build:buyer`, `build:merchant`, `build` (both)
- [x] `firebase.json` — two Firebase Hosting targets: `buyer` → dist/buyer, `merchant` → dist/merchant
- [x] `.firebaserc` — placeholder project + site targets (`negotiateiq-buyer`, `negotiateiq-merchant`)
- [x] Both builds clean: buyer 36 modules, merchant 41 modules, 0 errors
- [x] Local dev: buyer on :5173, merchant on :5174

**Part 9d — Role separation (Buyer Portal vs Merchant Dashboard)**
- [x] `MerchantLogin.jsx` — password gate (demo: `merchant123`); hardcoded, no backend call
- [x] `MerchantDashboard.jsx` — aggregate metrics (total sessions, win rate, avg discount, outcome bar chart, recent sessions table); all from React state
- [x] `MerchantProductsScreen.jsx` — full internal product view: list price + price floor + exact bulk tier %s + delivery options
- [x] `ProductsScreen.jsx` — sanitised for buyer view: price floor removed; bulk tiers replaced with "Volume discounts available" badge
- [x] `NegotiationScreen.jsx` — added `onSessionComplete(summary)` callback fired when any session ends (accepted/rejected/expired); summary includes sessionId, status, finalDeal, product, mode, persona; de-duped with ref
- [x] `Sidebar.jsx` — two nav configs: buyer (Products + Negotiate + merchant login link) vs merchant (Dashboard + Products + Negotiations + Config + logout); role badge in header for merchant view
- [x] `App.jsx` — role state (`"buyer"` | `"login"` | `"merchant"`); `completedSessions` array; full screen routing; MerchantNegotiationHistory inline component; login screen is full-width (no sidebar)
- [x] `npm run build` clean — 40 modules, 0 errors
- [x] Merchant data (price floor, exact discount %) is now completely hidden from the buyer portal

**Part 9f — Option B: Full configurable merchant agent**

- [x] `models.py` — added `ProductUpdate` (PATCH body for PUT /products/{sku}) and `MerchantConfig` (body for PUT /config)
- [x] `state_machine.py` — rewritten:
  - Removed `DEFAULT_MAX_TURNS = 8` and `MAX_DISCOUNT_PCT`; no configurable turn limit
  - Added `SAFETY_MAX_TURNS = 50` as absolute backstop (bug guard only, not user-visible)
  - Added `merchant_issued_final_offer()` method
  - Removed `should_use_final_offer()` (final offer now triggered purely by price floor in merchant.py)
- [x] `merchant.py` — rewritten:
  - Removed `MAX_DISCOUNT_PCT = 20`; agent now negotiates until `price_floor` is hit
  - Added `FINAL_OFFER_EPSILON = 0.50`: within $0.50 of floor → FINAL_OFFER
  - FINAL_OFFER uses a static firm message (no Gemini call)
  - COUNTER_OFFER calls Gemini for prose; numbers always locked by rules engine
  - Circular import fix: `get_merchant_config` imported inside `merchant_turn()` body
- [x] `firebase_db.py` — added:
  - `list_products()` — DRY_RUN: returns `_DRY_RUN_PRODUCTS`; production: Firestore `.stream()`
  - `update_product(sku, updates)` — merge semantics; DRY_RUN: patches in-memory dict
  - `_merchant_config` in-memory dict (agent_name, role, company)
  - `get_merchant_config()` — DRY_RUN: returns dict copy; production: Firestore config doc
  - `save_merchant_config(updates)` — merge semantics; DRY_RUN: updates in-memory dict
- [x] `main.py` — updated:
  - Imports: added `Intent`, `Sender`, `ProductUpdate`, `MerchantConfig` from models; added `list_products`, `update_product`, `get_merchant_config`, `save_merchant_config` from firebase_db
  - `GET /products` — returns all products for merchant config screen
  - `PUT /products/{sku}` — patch product pricing/delivery (ProductUpdate body)
  - `GET /config` — returns merchant agent identity config
  - `PUT /config` — updates agent identity (MerchantConfig body)
  - Force-reject logic in `run_turn()`: if merchant previously sent FINAL_OFFER and shopping agent counters, override the turn to REJECT intent and close session
- [x] `ui/src/api.js` — added `fetchProducts()`, `updateProduct(sku, data)`, `fetchMerchantConfig()`, `updateMerchantConfig(config)`
- [x] `ui/src/components/MerchantConfigScreen.jsx` — complete rewrite:
  - Self-fetches products + config from API (no more hardcoded constants or product prop)
  - Agent Identity section: editable name/role/company text fields with save button
  - Negotiation Behaviour section: informational summary of rules
  - Product Catalogue: per-product accordion editors; each product has editable list_price, price_floor, bulk tiers (add/remove rows), delivery checkboxes, voucher eligibility toggle; individual save buttons with save/error feedback
- [x] `ui/src/MerchantApp.jsx` — removed `product={null}` prop from MerchantConfigScreen (self-fetches now)
- [x] All new endpoints confirmed live: GET /products 200, GET /config 200, PUT /products/{sku} 200, PUT /config 200
- [x] Both buyer (:5173) and merchant (:5174) dev servers running with HMR applied

**Part 9g — UI redesign ("Structured Precision Dark")**
- [x] Design direction: editorial B2B dark, typography-first hierarchy, single accent (#7C6DFA indigo-violet), 8px spacing, no emoji in UI, no rounded-2xl cards
- [x] Color system: base #09090B, surface #111115, border #222228, accent #7C6DFA, text #F0F0F4/#7B7B96/#3D3D52, semantic green/red/amber only
- [x] `Sidebar.jsx` — structural border-only left rail, active state = left stripe accent, no background fill
- [x] `ProductsScreen.jsx` — editorial vertical list replacing 2-col card grid; price right-aligned, chevron indicator
- [x] `NegotiationScreen.jsx` — single-column setup (removed two-column merchant/counterparty split), cleaner chat area, underline input style
- [x] `TurnMessage.jsx` — rounded-lg (not 2xl), no emoji in terms, single accent system, tabular numbers
- [x] `DealSummary.jsx` — typographic outcome, no emoji icons, clean 2-col terms table
- [x] `MerchantLogin.jsx` — no emoji icon, no card container, accent-colored sign in button
- [x] `MerchantApp.jsx` — rewritten sidebar + negotiation history with new color system
- [x] `MerchantDashboard.jsx` — data-dense metric row (not card grid), thin progress bars, status text (no colored pill backgrounds)
- [x] `MerchantProductsScreen.jsx` — horizontal row layout replacing stacked cards, tabular numbers
- [x] `MerchantConfigScreen.jsx` — new color system throughout; Save button uses accent; rounded → rounded-md; no emoji
- [x] `App.jsx` + HTML files — body background updated to #09090B

**Part 9h — Dark/Light theme toggle**
- [x] CSS custom properties (`--bg`, `--surface`, `--surface-hover`, `--accent-tint`, `--border`, `--accent`, `--accent-hover`, `--text-1`, `--text-2`, `--text-3`, `--green`, `--green-tint`, `--green-border`, `--red`, `--red-tint`, `--red-border`, `--amber`, `--intent-counter-bg`, `--intent-counter`) defined in `<style>` block in both HTML files
- [x] `[data-theme="light"]` overrides for full light palette defined in both HTML files
- [x] Anti-flash inline script in `<head>` reads localStorage before paint, applies `data-theme` on `<html>`
- [x] `ThemeToggle.jsx` — fixed top-right button (sun/moon icon), toggles `data-theme` on `document.documentElement`, persists to localStorage
- [x] `App.jsx` — ThemeToggle imported + rendered; root div uses `var(--bg)` / `var(--text-1)`
- [x] All hardcoded hex colors replaced with `var(--...)` references across all component files:
  - `Sidebar.jsx`, `TurnMessage.jsx`, `DealSummary.jsx` (done in earlier session)
  - `MerchantLogin.jsx`, `ProductsScreen.jsx`, `NegotiationScreen.jsx`, `MerchantDashboard.jsx`, `MerchantProductsScreen.jsx`, `MerchantConfigScreen.jsx`
  - `MerchantApp.jsx` — ThemeToggle added, root divs updated, all inline components (MerchantSidebar, NegotiationHistory, ChatTranscript) converted to CSS vars

**Part 9i — Shopping Agent upgrade (merged best of both implementations)**
- [x] `orchestrator/src/gemini.py` — updated:
  - `_call_gemini_raw()` now captures per-call latency_ms, prompt_tokens, output_tokens, thoughts_tokens from usage_metadata
  - `call_merchant_agent()` logs structured `{"event":"gemini_call","agent":"merchant",...}` JSON entry
  - Added `call_gemini_shopping(system, user, schema, timeout_s)` → `(raw_text, metadata)` for structured output + timeout support
  - Added `load_persona_prompt(persona_key)` for string-key prompt loading
  - Added `is_dry_run()` public accessor
  - `response_schema` param passed to GenerateContentConfig (Gemini JSON-mode structured output)
- [x] `orchestrator/src/shopping.py` — full rewrite incorporating teammate's safety architecture:
  - `Bracket` + `PersonaSpec` dataclasses encode price limits in code (open/target/ceiling/walk-away per bracket)
  - `PERSONAS` dict: budget_shopper (8 turns/stall 3), premium_buyer (5 turns/stall 2, extended walk-away), bulk_purchaser (6 turns/stall 2, two qty brackets + lever_qty)
  - `NegotiationState` — derived view wrapping our `NegotiationSession.turns` (A2AMessage→raw dict conversion)
  - `required_action()` — code forces accept/reject before LLM is called (turn-limit, stall-limit, merchant-reject)
  - `is_acceptable()` — validates merchant terms against all persona constraints including extended walk-away
  - `clamp_counter()` — post-LLM hard clamp: walk-away, delivery cap, qty range, never-bid-above-merchant, never-lower-own-offer
  - `fallback_proposal()` — deterministic paced move when LLM fails or DRY_RUN=true
  - `_intent_problem()` — retry feedback when LLM chose wrong intent
  - Retry loop (1 retry with corrective feedback injected into context)
  - `BuyerReply` Pydantic schema for Gemini JSON-mode structured output
  - `_build_context()` — structured JSON context (replaces old plain-text "Turn N of 8" format)
  - Human mode: regex extracts price/qty/delivery/voucher + detects accept/reject/counter/query intent (replaces always-QUERY)
  - Per-turn structured JSON log: `{event, session_id, turn, persona, required, phase, stall, intent, source, attempts, latency_ms, llm}`
  - source values: llm | llm_repaired | override | fallback | dry_run
  - `verify_prompt_matches_limits()` — startup integrity check (logs warnings, never crashes)
  - Backward-compatible public API: `shopping_turn(session, product, state_machine, message_text)` unchanged
- [x] `orchestrator/prompts/persona_budget_shopper.txt` — replaced with 126-line structured version
- [x] `orchestrator/prompts/persona_premium_buyer.txt` — replaced with 127-line structured version (extended walk-away rule)
- [x] `orchestrator/prompts/persona_bulk_purchaser.txt` — replaced with 138-line structured version (two brackets, quantity lever)
  - All three prompts: structured JSON input (section 4), strict JSON output schema (section 5), 6-step decision procedure (section 6), persona-specific pacing (section 7), hard rules (section 8), worked examples (section 9)

**Part 9j — Merchant portal 500 fix + missing /config routes**
- [x] **Root cause**: stale Python server running on port 8000 (old code, returns 500 for `/sessions` and `/products`) while working server is on port 8001
- [x] `ui/vite.config.js` — proxy target updated `localhost:8000` → `localhost:8001`
- [x] `ui/vite.merchant.config.js` — created (was missing; `npm run dev:merchant` was failing); port 5174, proxy to `localhost:8001`, entry `index.merchant.html`
- [x] `orchestrator/src/main.py` — added missing `GET /config` and `PUT /config` route handlers (were in docstring but never implemented)
- [x] `orchestrator/src/models.py` — added `MerchantConfigUpdate` Pydantic model (all fields optional: agent_name, role, company)
- [x] `orchestrator/src/firebase_db.py` — added `update_merchant_config(updates)` function (was referenced in build log entry 9f but missing from file)

**Part 9k — Google Shopping-style buyer UI**
- [x] `orchestrator/src/merchant.py` — added `image_url` field to `Product` class
- [x] `orchestrator/src/firebase_db.py` — added `image_url` to all 4 dry-run products (picsum.photos seed URLs)
- [x] `orchestrator/src/models.py` — added `image_url: Optional[str]` to `ProductCreate` and `ProductUpdate`
- [x] `ui/src/api.js` — added `imageUrl: p.image_url ?? null` to `normalizeProduct()`
- [x] `ui/src/components/ProductsScreen.jsx` — complete rewrite:
  - Google Shopping 4-column responsive grid (4→3→2→1 columns)
  - Search bar filtering by name/SKU (client-side, instant)
  - Filter chips: Voucher eligible · Express delivery · Bulk discount (stackable)
  - Product cards: image with hover zoom, SKU badge, name, price, feature pills, Negotiate button
  - Image error fallback (placeholder SVG if URL fails)
  - Loading skeleton (4 animated placeholder cards)
- [x] `ui/src/components/NegotiationScreen.jsx` — SetupPanel redesigned:
  - Step 1: Two large mode cards — "Negotiate yourself" (Human) | "Use AI agent"
  - Step 2 (AI only): Three persona cards with icon, label, tagline, description — Budget Shopper · Premium Buyer · Bulk Purchaser
  - Start button disabled until both mode and (if AI) persona are selected
  - Product image thumbnail shown in negotiation header

**Part 9m — Persist LLM metrics per session to Firestore**
- [x] `orchestrator/src/metrics.py` — added `session_id` param to `record_call()`; added `total_call_count()` and `calls_since(offset, session_id)` helpers for tracking new calls per turn
- [x] `orchestrator/src/gemini.py` — added `session_id: Optional[str] = None` to both `call_merchant_agent()` and `call_gemini_shopping()`; forwarded to `record_call()`
- [x] `orchestrator/src/merchant.py` — passes `session_id=session.session_id` when calling `call_merchant_agent()`
- [x] `orchestrator/src/shopping.py` — passes `session_id=session.session_id` when calling `call_gemini_shopping()`
- [x] `orchestrator/src/firebase_db.py` — added `append_session_metrics(session_id, calls)`: writes LLM call records to `sessions/{session_id}/llm_calls` Firestore subcollection; no-op in dry-run mode
- [x] `orchestrator/src/main.py` — in `run_turn()`: snapshots `metrics_offset` before shopping+merchant turns; calls `append_session_metrics()` after each turn path (both normal and early-exit)

**Part 9l — Merchant Config UI: image URL + Metrics tab**
- [x] `orchestrator/src/metrics.py` — new in-memory LLM call metrics store:
  - `record_call(agent, model, latency_ms, prompt_tokens, output_tokens, thoughts_tokens)` — append one record
  - `get_metrics()` — returns `{calls, summary, by_agent}`: total/p50/p95/max latency, token totals, per-agent breakdown
- [x] `orchestrator/src/gemini.py` — import `metrics`; call `_metrics.record_call(...)` after every real Gemini call (merchant + shopping)
- [x] `orchestrator/src/main.py` — added `GET /metrics` endpoint (returns live in-memory stats, resets on server restart)
- [x] `ui/src/api.js` — added `fetchMetrics()` → `GET /metrics`
- [x] `ui/src/components/MerchantMetricsScreen.jsx` — new dashboard:
  - KPI tiles: Total LLM calls, Avg latency, P95 latency, Total tokens
  - Agent breakdown: Merchant vs Shopping agent side-by-side cards (calls, avg latency, prompt/output tokens)
  - Latency sparkline: SVG bar chart of last 24 calls, merchant=green / shopping=accent colored bars
  - Recent calls table: last 30 calls with time, agent badge, model, latency, prompt/output/total tokens; slow calls (>5s) highlighted red
  - Auto-refreshes every 10 seconds; manual refresh button
- [x] `ui/src/MerchantApp.jsx` — added "m-metrics" tab to MERCHANT_NAV (chart icon) + wired MerchantMetricsScreen

**Part 9n — Reliability improvements: retry, 429 detection, logging, simulated metrics**
- [x] `orchestrator/src/merchant.py` — added `import logging` + `log = logging.getLogger("negotiateiq.merchant")`; Gemini call now wrapped in retry loop (`for attempt in range(2)`); `log.warning()` on each exception so Gemini errors are visible in server terminal; 429/RESOURCE_EXHAUSTED detected via string match → breaks immediately (quota errors don't resolve on retry); static fallback display_text used when both attempts fail — [2026-10-11]
- [x] `orchestrator/src/shopping.py` — existing retry loop updated to break on 429 RESOURCE_EXHAUSTED (was retrying quota errors which wastes time and adds latency without benefit); dry-run path now records simulated metric via `_metrics.record_call()` so Metrics dashboard is populated in demo mode without real Gemini calls — [2026-10-11]
- [x] `orchestrator/src/gemini.py` — both `call_merchant_agent()` and `call_gemini_shopping()` now record a latency-only metric even on failure (tokens=None) so the dashboard shows the call was made; dry-run path in `call_merchant_agent()` records simulated metric with random latency+tokens — [2026-10-11]

**Documentation (continued)**
- [x] `docs/end_to_end_flow.md` — detailed end-to-end flow document with 7 Mermaid flowcharts + sequence diagram covering all code paths: session start, full turn execution (run_turn), shopping AI mode (all branches: required_action / dry-run / LLM retry / clamp / fallback), shopping human mode (regex parse → A2A), merchant agent (rules engine / FINAL_OFFER / Gemini retry), SSE event sequence, metrics collection flow, dry-run vs live mode comparison table, session end scenarios table — [2026-10-11]
- [x] `docs/merchant_agent.md` — complete rewrite: updated model name (gemini-3.8-flash), added retry loop + 429 detection, added logging, added session_id param, added image_url to Product, removed MAX_DISCOUNT_PCT references — [2026-10-11]
- [x] `docs/shopping_agent.md` — complete rewrite: new safety pipeline architecture (PersonaSpec, required_action, clamp_counter, fallback_proposal, BuyerReply schema), correct model name (gemini-3.8-flash), per-persona turn/stall budget table, human mode regex parsing, structured turn log, metrics recording, 429 break — [2026-10-11]
- [x] `docs/pipeline.md` — updated: added /metrics endpoint, added metrics.py to file map, added MerchantMetricsScreen.jsx and MerchantConfigScreen.jsx to file map, updated session end table (5 conditions now), updated shopping/merchant turn detail to match actual code, added metrics pipeline section, updated data persistence table — [2026-10-11]
- [x] `docs/run_log.md` — new doc: step-by-step run instructions, prerequisites, venv setup, .env config table, running all 3 processes, first negotiation walkthrough, dry-run vs live Gemini toggle, 6-item troubleshooting section — [2026-10-11]
- [x] `docs/solution_arch.md` — new doc: system overview, Mermaid high-level architecture diagram, component breakdown, A2AMessage model, Firestore schema (products/ sessions/ llm_calls subcollection), dry-run mode table, SSE sequence diagram, merchant agent two-layer flowchart, shopping agent safety pipeline flowchart, metrics/observability section, deployment topology, env var table — [2026-10-11]

**Part 9o — Product catalogues + deployment readiness**
- [x] Fixed `orchestrator/Dockerfile` — was Node.js/npm (wrong runtime); rewritten as Python 3.11-slim FastAPI image; CMD uses `$PORT` env var injected by Cloud Run — [2026-10-11]
- [x] Fixed `infra/deploy-cloudrun.sh` — corrected region (`asia-south1` → `asia-southeast1`); added Artifact Registry repo creation step; added `FIREBASE_PROJECT_ID` to Cloud Run env vars; switched `GEMINI_API_KEY` to Secret Manager (`--set-secrets`) instead of plain env var — [2026-10-11]
- [x] Fixed `infra/deploy-firebase.sh` — added `VITE_API_URL` injection into both Vite builds so production UI calls the Cloud Run URL, not localhost — [2026-10-11]
- [x] Fixed `orchestrator/src/main.py` `_row_to_product()` — was silently dropping `image_url` from CSV rows; added extraction so imported products include the product image — [2026-10-11]
- [x] `data/catalogue_electronics.csv` — 10-product electronics catalogue (Google Pixel 9 Pro/9a, Pixel Watch 3, Pixel Buds Pro 2, HP EliteBook 840 G11, HP OfficeJet Pro 9135e, Samsung Galaxy Tab S10+, Sony WH-1000XM6, Logitech MX Keys S, LG 32" 4K Monitor) with realistic prices, floors, bulk tiers, delivery options, and picsum image URLs — [2026-10-11]
- [x] `data/catalogue_furniture.csv` — 10-product home & furniture catalogue (Ergohuman Elite Chair, Flexispot Standing Desk, IKEA KALLAX, Casper Mattress, Philips Hue Kit, Dyson V15, Nespresso Vertuo, Kindle Scribe, Ring Doorbell Pro 2, LIFX 10-pack) — [2026-10-11]
- [x] `firestore/seed-products.js` — updated to seed all 20 products across both catalogues (was only 1 placeholder); includes image_url fields — [2026-10-11]

**Part 9q — Merchant UI enhancements**
- [x] `MerchantProductsScreen.jsx` — added live search bar (filter by name/SKU); product images now displayed as thumbnails beside each product card (matching buyer UI style) — [2026-10-11]
- [x] `MerchantConfigScreen.jsx` — added search bar inside the collapsible Product Catalogue section; filters by name or SKU in real time — [2026-10-11]
- [x] `MerchantApp.jsx` `NegotiationHistory` — added "Date / Time" column (formatted "Oct 11 · 14:32") to the negotiations table; `createdAt` added to normalizedSessions mapping — [2026-10-11]
- [x] `MerchantDashboard.jsx` — "Recent sessions" table now shows only sessions from the last 24 hours with a "last 24 h" label; added "Date / Time" column; shows empty state message when no recent sessions — [2026-10-11]

**Part 9p — Bug fixes (full code review)**
- [x] `ui/src/components/MerchantConfigScreen.jsx` — CRITICAL: added `image_url` to `COLUMN_SPEC` and `TEMPLATE_CSV`; merchants can now see/download the correct template column — [2026-10-11]
- [x] `orchestrator/src/main.py` `_row_to_product()` — removed dead first `missing` check (was computed then immediately overwritten before use) — [2026-10-11]
- [x] `orchestrator/src/shopping.py` `BuyerReply` — made `product_id` optional with default `""` to avoid unnecessary ValidationError retries when Gemini omits the field — [2026-10-11]
- [x] `orchestrator/src/metrics.py` — fixed p95 off-by-one: `int(n * 0.95)` → `max(0, int(n * 0.95) - 1)` for correct percentile index — [2026-10-11]

### Phase 3 — Deploy
- [ ] End-to-end demo run with real Gemini API key (3 personas × 2 modes)
- [ ] Add Cloud Logging audit trail (structured log entries already emitted)

---

## Deployment Steps

### Prerequisites
- GCP project: `negotiateiq-510510` with billing enabled
- APIs enabled: Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Firestore (Native mode)
- Firebase project linked to the same GCP project
- Tools installed: `gcloud` CLI, `firebase-tools` (npm), `node` (for seed script)

### 1 — Set up GCP credentials (one-time)
```bash
gcloud auth login
gcloud config set project negotiateiq-510510
gcloud auth application-default login   # for local Firestore access
```

### 2 — Store GEMINI_API_KEY as a Secret (one-time)
```bash
echo -n "YOUR_GEMINI_API_KEY" | \
  gcloud secrets create negotiateiq-gemini-key --data-file=- \
  --project=negotiateiq-510510
# Grant Cloud Run's service account access:
gcloud secrets add-iam-policy-binding negotiateiq-gemini-key \
  --member="serviceAccount:$(gcloud projects describe negotiateiq-510510 \
    --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=negotiateiq-510510
```

### 3 — Seed Firestore product catalogue (one-time, or to reset products)
```bash
# Requires GOOGLE_APPLICATION_CREDENTIALS or gcloud ADC
FIREBASE_PROJECT_ID=negotiateiq-510510 node firestore/seed-products.js
# Alternatively: upload via Merchant Portal → Config → "Import CSV" button
#   using data/catalogue_electronics.csv or data/catalogue_furniture.csv
```

### 4 — Deploy orchestrator to Cloud Run
```bash
export GCP_PROJECT_ID=negotiateiq-510510
export GEMINI_API_KEY=<not needed — stored in Secret Manager>
bash infra/deploy-cloudrun.sh
# Captures the service URL at the end — copy it for step 6
```

### 5 — Set up Firebase Hosting targets (one-time)
```bash
firebase login
firebase use negotiateiq-510510
# Verify firebase.json has two hosting targets: "buyer" → dist/buyer, "merchant" → dist/merchant
# Verify .firebaserc has sites: negotiateiq-buyer, negotiateiq-merchant
firebase target:apply hosting buyer   negotiateiq-buyer
firebase target:apply hosting merchant negotiateiq-merchant
```

### 6 — Build and deploy UI to Firebase Hosting
```bash
export VITE_API_URL=https://negotiateiq-orchestrator-xxxx-as.a.run.app/api
bash infra/deploy-firebase.sh
# Buyer UI:    https://negotiateiq-buyer.web.app
# Merchant UI: https://negotiateiq-merchant.web.app
```

### 7 — Smoke test
```bash
# Health check
curl https://negotiateiq-orchestrator-xxxx-as.a.run.app/health
# → {"status": "ok"}

# Products loaded
curl https://negotiateiq-orchestrator-xxxx-as.a.run.app/products | python -m json.tool | head -20

# Open buyer UI, select a product, run a negotiation in AI mode
# Open merchant UI, confirm session appears in Dashboard and Metrics tabs
```

### Environment variables reference (Cloud Run)
| Variable | Source | Value |
|---|---|---|
| `GCP_PROJECT_ID` | Cloud Run env var | `negotiateiq-510510` |
| `GCP_REGION` | Cloud Run env var | `asia-southeast1` |
| `FIREBASE_PROJECT_ID` | Cloud Run env var | `negotiateiq-510510` |
| `GEMINI_API_KEY` | Secret Manager | `negotiateiq-gemini-key` |
| `DRY_RUN` | NOT set (or `false`) | real Gemini calls |
| `FIREBASE_DRY_RUN` | NOT set (or `false`) | real Firestore |

### Local dev vs production comparison
| Concern | Local dev | Cloud Run production |
|---|---|---|
| Gemini | `DRY_RUN=true` (simulated) or `GEMINI_API_KEY` in `.env` | Secret Manager |
| Firestore | `FIREBASE_DRY_RUN=true` (in-memory) or ADC | Cloud Run service account (ADC automatic) |
| Backend URL | `localhost:8001` | Cloud Run HTTPS URL |
| Frontend | `localhost:5173` (buyer), `localhost:5174` (merchant) | Firebase Hosting URLs |
| CORS | `*` (current) | Tighten to Firebase Hosting origins in `main.py` before production |
