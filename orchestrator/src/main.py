"""
main.py — FastAPI orchestration layer for NegotiateIQ.

Endpoints:
  POST /session/start          — create a new negotiation session
  POST /session/{id}/turn      — run one full turn (shopping + merchant)
  GET  /session/{id}/stream    — SSE stream: pushes each turn to the UI in real time
  GET  /session/{id}/status    — return current session state + full turn history
  GET  /sessions               — merchant dashboard: list all session summaries
  GET  /products               — merchant admin: list all products
  PUT  /products/{sku}         — merchant admin: update a product
  GET  /config                 — merchant admin: get agent config
  PUT  /config                 — merchant admin: update agent config
  GET  /health                 — liveness check for Cloud Run
"""

import asyncio
import csv
import io
import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from models import (
    NegotiationSession, StartSessionRequest, TurnRequest,
    Mode, SessionStatus, Intent, Sender, ProductCreate, ProductUpdate,
    MerchantConfigUpdate,
)
from gemini import init_gemini
import metrics as _metrics
from firebase_db import (
    init_firebase, get_product, create_session,
    get_session, update_session, list_sessions,
    list_products, create_product, update_product, delete_product,
    get_merchant_config, update_merchant_config,
    append_session_metrics,
)
from shopping import shopping_turn
from merchant import merchant_turn
from state_machine import StateMachine, NegotiationError


# ---------------------------------------------------------------------------
# In-memory SSE queues — one asyncio.Queue per active session.
# When run_turn completes a turn it puts the event here;
# the /stream endpoint reads from here and pushes to the browser.
# Safe for single-instance Cloud Run (demo scale — single tenant).
# ---------------------------------------------------------------------------

_sse_queues: dict[str, asyncio.Queue] = {}

def _get_queue(session_id: str) -> asyncio.Queue:
    """Return (or create) the SSE queue for a session."""
    if session_id not in _sse_queues:
        _sse_queues[session_id] = asyncio.Queue()
    return _sse_queues[session_id]

async def _push_event(session_id: str, event: dict) -> None:
    """Put a serialised event onto the session's SSE queue."""
    await _get_queue(session_id).put(json.dumps(event))

async def _close_stream(session_id: str) -> None:
    """Send a sentinel None so the /stream generator exits cleanly."""
    await _get_queue(session_id).put(None)


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise external service clients on startup."""
    load_dotenv()       # loads orchestrator/.env in local dev
    init_gemini()       # configure Gemini API key
    init_firebase()     # configure Firestore
    yield
    # No cleanup needed — Cloud Run handles container shutdown


# ---------------------------------------------------------------------------
# App definition
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NegotiateIQ Orchestrator",
    description="A2A negotiation orchestration layer",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the Firebase-hosted UI to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # tighten to Firebase Hosting domain before production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check — required by Cloud Run
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /sessions — merchant dashboard: list all session summaries
# ---------------------------------------------------------------------------

@app.get("/sessions")
async def list_sessions_endpoint():
    """Return a summary of every session (no full turn history) for the merchant dashboard."""
    sessions = await list_sessions()
    summaries = []
    for s in sessions:
        try:
            product = await get_product(s.product_sku)
            product_info = {
                "sku":        product.sku,
                "name":       product.name,
                "list_price": product.list_price,
            }
        except Exception:
            product_info = {"sku": s.product_sku, "name": s.product_sku, "list_price": None}

        summaries.append({
            "session_id":  s.session_id,
            "status":      s.status.value,
            "product":     product_info,
            "mode":        s.mode.value,
            "persona":     s.persona.value if s.persona else None,
            "turn_count":  s.turn_count,
            "final_deal":  s.final_deal.model_dump() if s.final_deal else None,
            "created_at":  s.created_at.isoformat(),
        })
    return {"sessions": summaries}


# ---------------------------------------------------------------------------
# GET /products — merchant admin: list all products
# ---------------------------------------------------------------------------

@app.get("/products")
async def list_products_endpoint():
    """Return all products. Used by the merchant config screen."""
    products = await list_products()
    return {"products": products}


# ---------------------------------------------------------------------------
# POST /products — merchant admin: create a new product
# ---------------------------------------------------------------------------

@app.post("/products", status_code=201)
async def create_product_endpoint(body: ProductCreate):
    """Create a new product. Returns 409 if the SKU already exists."""
    try:
        created = await create_product(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"product": created}


# ---------------------------------------------------------------------------
# POST /products/upload — bulk create/update from CSV or Excel
# ---------------------------------------------------------------------------

# Column contract (enforced here so the spec lives close to the parsing code):
#   MANDATORY : sku, name, list_price, price_floor
#   OPTIONAL  : delivery_options (comma-separated keys, e.g. "standard_5d,express_2d")
#               vouchers_eligible (true/false/yes/no/1/0 — default false)
#               tier1_min_qty, tier1_discount_pct
#               tier2_min_qty, tier2_discount_pct
#               tier3_min_qty, tier3_discount_pct

MANDATORY_COLS = {"sku", "name", "list_price", "price_floor"}


def _parse_bool(val: str) -> bool:
    return str(val).strip().lower() in {"true", "yes", "1"}


def _build_tiers(row: dict) -> list:
    tiers = []
    for n in range(1, 4):
        qty_key  = f"tier{n}_min_qty"
        pct_key  = f"tier{n}_discount_pct"
        qty_val  = row.get(qty_key, "").strip()
        pct_val  = row.get(pct_key, "").strip()
        if qty_val and pct_val:
            try:
                tiers.append({"min_qty": int(float(qty_val)), "discount_pct": float(pct_val)})
            except ValueError:
                pass   # skip malformed tier — not fatal
    return tiers


def _rows_from_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig")   # strip BOM if present
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader]


def _rows_from_excel(raw: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    result  = []
    for row in rows[1:]:
        if all(cell is None for cell in row):
            continue   # skip blank rows
        result.append({headers[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row)})
    return result


def _row_to_product(row: dict) -> dict:
    """Convert a raw header→value dict into a product dict. Raises ValueError on bad data."""
    # normalise keys to lowercase (values are already stripped by the caller)
    row = {k.strip().lower(): v.strip() for k, v in row.items()}
    missing = MANDATORY_COLS - {k for k in row if row.get(k)}
    if missing:
        raise ValueError(f"Missing mandatory columns: {', '.join(sorted(missing))}")

    list_price  = float(row["list_price"])
    price_floor = float(row["price_floor"])
    if price_floor > list_price:
        raise ValueError(f"price_floor ({price_floor}) cannot exceed list_price ({list_price})")

    raw_delivery = row.get("delivery_options", "").strip()
    delivery = [d.strip() for d in raw_delivery.split(",") if d.strip()] or ["standard_5d"]

    image_url = row.get("image_url", "").strip() or None

    return {
        "sku":               row["sku"].upper(),
        "name":              row["name"],
        "list_price":        list_price,
        "price_floor":       price_floor,
        "bulk_tiers":        _build_tiers(row),
        "delivery_options":  delivery,
        "vouchers_eligible": _parse_bool(row.get("vouchers_eligible", "false")),
        "image_url":         image_url,
    }


@app.post("/products/upload")
async def upload_product_catalogue(file: UploadFile = File(...)):
    """
    Bulk create/update products from a CSV (.csv) or Excel (.xlsx/.xls) file.

    Mandatory columns : sku, name, list_price, price_floor
    Optional columns  : delivery_options, vouchers_eligible,
                        tier1_min_qty, tier1_discount_pct,
                        tier2_min_qty, tier2_discount_pct,
                        tier3_min_qty, tier3_discount_pct

    Behaviour per row:
      - Existing SKU → UPDATE (merge patch)
      - New SKU      → CREATE
    Returns { created, updated, errors } counts and lists.
    """
    raw = await file.read()
    filename = (file.filename or "").lower()

    try:
        if filename.endswith(".csv"):
            rows = _rows_from_csv(raw)
        elif filename.endswith((".xlsx", ".xls")):
            rows = _rows_from_excel(raw)
        else:
            raise HTTPException(
                status_code=415,
                detail="Unsupported file type. Upload a .csv or .xlsx file."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    created, updated, errors = [], [], []

    for i, row in enumerate(rows, start=2):   # row 1 is the header
        try:
            product = _row_to_product(row)
        except (ValueError, KeyError) as e:
            errors.append({"row": i, "sku": row.get("sku", "?"), "reason": str(e)})
            continue

        sku = product["sku"]
        try:
            await get_product(sku)
            # Product exists — update it
            await update_product(sku, {k: v for k, v in product.items() if k != "sku"})
            updated.append(sku)
        except ValueError:
            # New product — create it
            try:
                await create_product(product)
                created.append(sku)
            except ValueError as e:
                errors.append({"row": i, "sku": sku, "reason": str(e)})

    return {
        "summary": {
            "total_rows": len(rows),
            "created":    len(created),
            "updated":    len(updated),
            "errors":     len(errors),
        },
        "created": created,
        "updated": updated,
        "errors":  errors,
    }


# ---------------------------------------------------------------------------
# PUT /products/{sku} — merchant admin: update a product's fields
# ---------------------------------------------------------------------------

@app.put("/products/{sku}")
async def update_product_endpoint(sku: str, body: ProductUpdate):
    """Patch a product's pricing and delivery settings. All fields optional."""
    try:
        updated = await update_product(sku, body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"product": updated}


# ---------------------------------------------------------------------------
# DELETE /products/{sku} — merchant admin: remove a product
# ---------------------------------------------------------------------------

@app.delete("/products/{sku}", status_code=204)
async def delete_product_endpoint(sku: str):
    """Permanently delete a product by SKU."""
    try:
        await delete_product(sku)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# GET /config — merchant admin: get agent identity config
# ---------------------------------------------------------------------------

@app.get("/config")
async def get_config():
    """Return the merchant agent's current identity config (name, role, company)."""
    config = await get_merchant_config()
    return {"config": config}


# ---------------------------------------------------------------------------
# PUT /config — merchant admin: update agent identity config
# ---------------------------------------------------------------------------

@app.put("/config")
async def update_config(body: MerchantConfigUpdate):
    """Patch the merchant agent's identity config. All fields optional."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update.")
    updated = await update_merchant_config(updates)
    return {"config": updated}


# ---------------------------------------------------------------------------
# GET /metrics — LLM latency and token usage metrics for the merchant portal
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def get_metrics():
    """Return in-memory LLM call metrics: summary stats + last 100 raw calls."""
    return _metrics.get_metrics()


# ---------------------------------------------------------------------------
# POST /session/start — create a new negotiation session
# ---------------------------------------------------------------------------

@app.post("/session/start", status_code=201)
async def start_session(request: StartSessionRequest):
    """
    Create a new session. Returns the session_id for all subsequent calls.
    Validates that persona is provided in AI mode.
    """
    if request.mode == Mode.AI and not request.persona:
        raise HTTPException(status_code=400, detail="persona is required when mode is 'ai'.")

    try:
        await get_product(request.product_sku)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Product not found: {request.product_sku}")

    session = NegotiationSession(
        mode=        request.mode,
        persona=     request.persona,
        product_sku= request.product_sku,
    )
    await create_session(session)

    return {
        "session_id":  session.session_id,
        "product_sku": session.product_sku,
        "mode":        session.mode.value,
        "persona":     session.persona.value if session.persona else None,
        "status":      session.status.value,
    }


# ---------------------------------------------------------------------------
# POST /session/{session_id}/turn — run one full negotiation turn
# ---------------------------------------------------------------------------

@app.post("/session/{session_id}/turn")
async def run_turn(session_id: str, request: TurnRequest):
    """
    Execute one full turn:
      1. Shopping side goes (AI persona or human message)
      2. Each completed message is pushed to the SSE queue → UI sees it instantly
      3. Merchant agent responds
      4. Full session persisted to Firestore

    Returns both messages in the HTTP response as well (UI can use whichever arrives first).
    """
    try:
        session = await get_session(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=409,
            detail=f"Session is already {session.status.value}. No more turns allowed."
        )

    product = await get_product(session.product_sku)
    sm = StateMachine(session)

    # Snapshot call count before the turn so we can persist only the new calls
    metrics_offset = _metrics.total_call_count()

    # --- Shopping turn ---
    try:
        shopping_msg = await shopping_turn(
            session=      session,
            product=      product,
            state_machine=sm,
            message_text= request.message_text,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NegotiationError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Force-reject if shopping agent counters after merchant's FINAL_OFFER.
    # session.turns[-1] is the just-applied shopping_msg; check everything before it.
    prior_turns = session.turns[:-1]
    merchant_sent_final = any(
        m.sender == Sender.MERCHANT_AGENT and m.intent == Intent.FINAL_OFFER
        for m in prior_turns
    )
    if merchant_sent_final and shopping_msg.intent not in {Intent.ACCEPT, Intent.REJECT}:
        forced = shopping_msg.model_copy(update={
            "intent":       Intent.REJECT,
            "display_text": "The merchant's final price could not be matched. Negotiation closed.",
        })
        session.turns[-1]  = forced
        session.status     = SessionStatus.REJECTED
        shopping_msg       = forced

    # Push shopping turn to SSE stream immediately
    await _push_event(session_id, _msg_summary(shopping_msg))

    # If buyer accepted/rejected, no merchant turn needed
    if session.status != SessionStatus.ACTIVE:
        await update_session(session)
        await _push_event(session_id, {"type": "status", "status": session.status.value,
                                       "final_deal": session.final_deal.model_dump() if session.final_deal else None})
        await _close_stream(session_id)
        new_calls = _metrics.calls_since(metrics_offset, session_id)
        await append_session_metrics(session_id, new_calls)
        return _turn_response(shopping_msg=shopping_msg, merchant_msg=None, session=session)

    # --- Merchant turn ---
    try:
        merch_msg = await merchant_turn(
            session=      session,
            product=      product,
            state_machine=sm,
            buyer_msg=    shopping_msg,
        )
    except NegotiationError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Push merchant turn to SSE stream, persist session
    await _push_event(session_id, _msg_summary(merch_msg))
    await update_session(session)

    # If session ended (final offer accepted/rejected/expired), close the stream
    if session.status != SessionStatus.ACTIVE:
        await _push_event(session_id, {"type": "status", "status": session.status.value,
                                       "final_deal": session.final_deal.model_dump() if session.final_deal else None})
        await _close_stream(session_id)

    # Persist LLM calls made during this turn to Firestore (no-op in dry-run mode)
    new_calls = _metrics.calls_since(metrics_offset, session_id)
    await append_session_metrics(session_id, new_calls)

    return _turn_response(shopping_msg=shopping_msg, merchant_msg=merch_msg, session=session)


# ---------------------------------------------------------------------------
# GET /session/{session_id}/stream — SSE endpoint
# ---------------------------------------------------------------------------

@app.get("/session/{session_id}/stream")
async def stream_session(session_id: str):
    """
    Server-Sent Events endpoint. The browser UI connects here with EventSource.
    Each negotiation turn is pushed as a JSON data event as soon as it's ready.
    The stream closes automatically when the session ends.
    """
    # Ensure the session exists before opening the stream
    try:
        await get_session(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    queue = _get_queue(session_id)

    async def event_generator():
        """Yield SSE-formatted events from the queue until the session closes."""
        while True:
            payload = await queue.get()
            if payload is None:
                # Sentinel received — session is over, close the stream
                yield "event: close\ndata: {}\n\n"
                break
            # Standard SSE format: "data: <json>\n\n"
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering on Cloud Run
        },
    )


# ---------------------------------------------------------------------------
# GET /session/{session_id}/status — return current session state
# ---------------------------------------------------------------------------

@app.get("/session/{session_id}/status")
async def session_status(session_id: str):
    """Return the current session state and full turn history."""
    try:
        session = await get_session(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return {
        "session_id":  session.session_id,
        "status":      session.status.value,
        "mode":        session.mode.value,
        "persona":     session.persona.value if session.persona else None,
        "product_sku": session.product_sku,
        "turn_count":  session.turn_count,
        "final_deal":  session.final_deal.model_dump() if session.final_deal else None,
        "turns": [
            {
                "turn":           m.turn,
                "sender":         m.sender.value,
                "intent":         m.intent.value,
                "display_text":   m.display_text,
                "proposed_terms": m.proposed_terms.model_dump() if m.proposed_terms else None,
            }
            for m in session.turns
        ],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _msg_summary(msg) -> dict:
    """Compact dict of a turn message — used for SSE events and HTTP responses."""
    return {
        "type":           "turn",
        "turn":           msg.turn,
        "sender":         msg.sender.value,
        "intent":         msg.intent.value,
        "display_text":   msg.display_text,
        "proposed_terms": msg.proposed_terms.model_dump() if msg.proposed_terms else None,
    }


def _turn_response(shopping_msg, merchant_msg, session: NegotiationSession) -> dict:
    """HTTP response body for POST /session/{id}/turn."""
    return {
        "shopping_turn":  _msg_summary(shopping_msg) if shopping_msg else None,
        "merchant_turn":  _msg_summary(merchant_msg) if merchant_msg else None,
        "session_status": session.status.value,
        "turn_count":     session.turn_count,
        "final_deal":     session.final_deal.model_dump() if session.final_deal else None,
    }
