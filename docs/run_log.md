# NegotiateIQ — How to Run This Project

Audience: a developer who has cloned the repo for the first time.

---

## 1. Prerequisites

Before you begin, make sure the following are installed on your machine:

| Tool | Minimum version | Check |
|------|----------------|-------|
| Python | 3.14+ | `python --version` |
| Node.js | 18+ (v24 recommended) | `node --version` |
| npm | 10+ (v11 recommended) | `npm --version` |
| Git | any recent | `git --version` |

You will also need a **Gemini API key** from [aistudio.google.com](https://aistudio.google.com). Keys start with `AIza`. The free tier allows 20 requests per day per model.

---

## 2. One-Time Setup

### 2.1 Clone the repository

```bash
git clone <repo-url>
cd A2A_protocol_prac
```

### 2.2 Create and activate the Python virtual environment

```bash
cd orchestrator
python -m venv venv
```

Activate (Windows PowerShell):

```powershell
venv\Scripts\Activate.ps1
```

Activate (Windows CMD):

```cmd
venv\Scripts\activate.bat
```

Activate (macOS / Linux):

```bash
source venv/bin/activate
```

### 2.3 Install Python dependencies

From inside `orchestrator/` with the venv active:

```bash
pip install -r requirements.txt
```

### 2.4 Install Node dependencies for the UI

Open a second terminal and navigate to the `ui/` directory:

```bash
cd ui
npm install
```

---

## 3. Environment Configuration

The backend reads configuration from `orchestrator/.env`. This file is **gitignored — never commit it**.

Use the provided example as a starting template:

```bash
# from the orchestrator/ directory
copy .env.example .env   # Windows
# or
cp .env.example .env     # macOS / Linux
```

Then open `orchestrator/.env` in your editor and fill in the values:

```dotenv
# ─── Gemini ───────────────────────────────────────────────────
GEMINI_API_KEY=AIza...          # Required for live mode; get from aistudio.google.com
MERCHANT_MODEL=gemini-3.8-flash # Model used by the Merchant Agent
SHOPPING_MODEL=gemini-3.8-flash # Model used by the Shopping Agent

# ─── Dry-run flags ────────────────────────────────────────────
DRY_RUN=false                   # true → skip Gemini (simulated responses)
FIREBASE_DRY_RUN=true           # true → skip Firestore (use in-memory store)

# ─── GCP / Firebase (only needed when FIREBASE_DRY_RUN=false) ─
GCP_PROJECT=negotiateiq-510510
GCP_REGION=asia-southeast1
```

**For a local demo** the recommended settings are:

```dotenv
DRY_RUN=false
FIREBASE_DRY_RUN=true
GEMINI_API_KEY=AIza<your-key>
```

This gives you real Gemini responses without needing a Firestore connection.

> **Security reminder:** Never commit `.env` or any GCP JSON key files to version control.

---

## 4. Running Locally

You need **three separate terminal windows** — one for the backend and one for each UI.

### Terminal 1 — Backend (FastAPI on port 8001)

```powershell
cd orchestrator
venv\Scripts\uvicorn main:app --app-dir src --port 8001
```

Wait until you see a line similar to:

```
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

> **Important:** always start the server from the `orchestrator/` directory using the venv's own `uvicorn` binary. Running `uvicorn` from the system Python path is a common source of import errors (see Troubleshooting).

### Terminal 2 — Buyer UI (Vite on port 5173)

```powershell
cd ui
npm run dev:buyer
```

Access at: [http://localhost:5173](http://localhost:5173)

### Terminal 3 — Merchant UI (Vite on port 5174)

```powershell
cd ui
npm run dev:merchant
```

Access at: [http://localhost:5174](http://localhost:5174)

---

## 5. Running Your First Negotiation

1. Open [http://localhost:5173](http://localhost:5173) in your browser (Buyer UI).
2. Select a **product** from the catalogue.
3. Choose a **negotiation persona** (Budget Shopper, Premium Buyer, or Bulk Purchaser).
4. Click **Start Negotiation**.
5. Watch the A2A message exchange in real time via Server-Sent Events.
6. The negotiation ends when the Shopping Agent accepts, the Merchant Agent issues a final offer, or the maximum turn count for the persona is reached.
7. A summary of the deal (or rejection) is shown on screen.

> Metrics for the session are stored in memory. They reset when the backend restarts.

---

## 6. Accessing the Merchant Portal

1. Open [http://localhost:5174](http://localhost:5174) in your browser (Merchant UI).
2. Enter the password **`merchant123`** when prompted (demo gate — hardcoded).
3. From the dashboard you can:
   - View and edit product listings (name, list price, price floor, bulk tiers).
   - Review active and completed negotiation sessions.
   - Inspect per-session LLM call metrics.

---

## 7. Switching Between Dry-Run and Live Gemini Mode

Edit `orchestrator/.env` and restart the backend after each change.

| Scenario | `DRY_RUN` | `FIREBASE_DRY_RUN` | Notes |
|----------|-----------|-------------------|-------|
| Full dry-run (no API calls) | `true` | `true` | Fastest; simulated responses |
| Live Gemini, in-memory store | `false` | `true` | **Recommended for local demo** |
| Live Gemini + Firestore | `false` | `false` | Requires GCP credentials |

To toggle, update the value in `.env` and then stop and restart Terminal 1.

**Free-tier quota:** 20 requests per day per Gemini model. Each negotiation turn makes 1–2 LLM calls. Monitor usage at [aistudio.google.com](https://aistudio.google.com).

---

## 8. Troubleshooting

### 8.1 Port 8001 not responding / 404 on `/metrics`

**Symptom:** `curl http://localhost:8001/metrics` returns a connection error or 404.

**Cause:** The backend server is not running, or it was never (re)started after a code change.

**Fix:** Start (or restart) Terminal 1 using the exact command in section 4. Confirm the uvicorn startup line appears.

---

### 8.2 HTTP 500 on the merchant dashboard

**Symptom:** The merchant UI loads but all API calls return 500.

**Cause:** The Vite proxy in `vite.merchant.config.js` is pointing to the wrong port.

**Fix:** Open `ui/vite.merchant.config.js` and verify the proxy target is `http://localhost:8001`. It must not be 8000 or any other port.

---

### 8.3 Merchant portal shows the buyer UI

**Symptom:** Navigating to [http://localhost:5174](http://localhost:5174) shows the buyer product catalogue instead of the merchant dashboard.

**Cause:** `vite.merchant.config.js` is not being used; npm is serving the default Vite config instead.

**Fix:** Make sure you launched the merchant UI with `npm run dev:merchant` (not `npm run dev` or `npm run dev:buyer`). Check that `package.json` has a `"dev:merchant"` script that passes `--config vite.merchant.config.js`.

---

### 8.4 `ImportError: cannot import name 'genai'`

**Symptom:** The backend crashes at startup with an ImportError referencing `genai`.

**Cause:** `uvicorn` is being invoked from the system Python environment, not the project venv. The `google-genai` package is only installed inside the venv.

**Fix:** Ensure the venv is active before running uvicorn, **and** use the venv-local binary path:

```powershell
# Correct — uses the venv's own uvicorn
orchestrator\venv\Scripts\uvicorn main:app --app-dir src --port 8001
```

Do not use a globally installed `uvicorn` command.

---

### 8.5 `429 RESOURCE_EXHAUSTED` from Gemini

**Symptom:** LLM calls fail with HTTP 429 and the message `RESOURCE_EXHAUSTED`.

**Cause:** The free-tier quota (20 requests per day per model) has been exhausted.

**Fix (short-term):** Set `DRY_RUN=true` in `.env` and restart the backend to continue testing without API calls.

**Fix (long-term):** Upgrade your Google AI Studio project to a paid tier, or wait until the next UTC day for the quota to reset.

---

### 8.6 No metrics showing on the merchant dashboard

**Symptom:** The metrics panel on the merchant portal is empty even after a negotiation.

**Cause (1):** The backend was restarted since the last negotiation. Metrics are held in memory (`metrics.py`) and reset on every restart.

**Cause (2):** No negotiation has been completed since the server last started.

**Fix:** Ensure the backend has not been restarted since your last session. Then run at least one full negotiation via the buyer UI. The metrics endpoint at `GET /api/metrics` will populate after the first completed negotiation turn.
