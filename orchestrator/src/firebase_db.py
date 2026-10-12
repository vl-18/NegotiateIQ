"""
firebase_db.py — Firestore integration for NegotiateIQ.

Handles session and product persistence only.
Live turn streaming is done via SSE in main.py — no Firebase Realtime DB needed.

Initialised once at startup via init_firebase().
All functions are async-friendly (blocking SDK calls run in thread executor).

DRY_RUN=true skips real Firestore and uses in-memory dicts + a hardcoded product
catalogue — no GCP credentials needed for local demos.
"""

import asyncio
import os
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

from models import A2AMessage, NegotiationSession, ProposedTerms, Mode, Persona, SessionStatus
from merchant import Product


# ---------------------------------------------------------------------------
# Dry-run in-memory store
# ---------------------------------------------------------------------------

_dry_run: bool = False
_sessions: dict = {}    # session_id → NegotiationSession (live Python objects)

# Hardcoded product catalogue — matches the 4 SKUs we'll seed in Firestore
_DRY_RUN_PRODUCTS = {
    "SKU-001": {
        "sku": "SKU-001", "name": "Sony WH-1000XM6",
        "list_price": 99.99, "price_floor": 79.99,
        "bulk_tiers": [{"min_qty": 10, "discount_pct": 8}, {"min_qty": 50, "discount_pct": 15}],
        "delivery_options": ["standard_5d", "express_2d"],
        "vouchers_eligible": True,
        "image_url": "https://picsum.photos/seed/headphones/400/280",
    },
    "SKU-002": {
        "sku": "SKU-002", "name": "Logitech MX Master 3S",
        "list_price": 49.99, "price_floor": 39.99,
        "bulk_tiers": [{"min_qty": 10, "discount_pct": 8}, {"min_qty": 50, "discount_pct": 15}],
        "delivery_options": ["standard_5d", "express_2d"],
        "vouchers_eligible": True,
        "image_url": "https://picsum.photos/seed/mouse/400/280",
    },
    "SKU-003": {
        "sku": "SKU-003", "name": "Samsung T7 SSD 1TB",
        "list_price": 89.99, "price_floor": 69.99,
        "bulk_tiers": [{"min_qty": 10, "discount_pct": 8}, {"min_qty": 50, "discount_pct": 15}],
        "delivery_options": ["standard_5d"],
        "vouchers_eligible": False,
        "image_url": "https://picsum.photos/seed/storage/400/280",
    },
    "SKU-004": {
        "sku": "SKU-004", "name": "LG 27\" 4K Monitor",
        "list_price": 399.99, "price_floor": 319.99,
        "bulk_tiers": [{"min_qty": 5, "discount_pct": 8}, {"min_qty": 20, "discount_pct": 15}],
        "delivery_options": ["standard_5d", "express_2d"],
        "vouchers_eligible": True,
        "image_url": "https://picsum.photos/seed/monitor/400/280",
    },
}


# ---------------------------------------------------------------------------
# Initialisation — called once in main.py lifespan
# ---------------------------------------------------------------------------

def init_firebase() -> None:
    """
    Initialise the Firebase Admin SDK.

    Local dev:  uses GOOGLE_APPLICATION_CREDENTIALS env var or ADC.
    Cloud Run:  uses the attached service account automatically (no key file needed).
    DRY_RUN or FIREBASE_DRY_RUN: skips Firebase — in-memory store used instead.
    Use FIREBASE_DRY_RUN=true to keep in-memory storage while Gemini uses real LLM calls.
    """
    global _dry_run
    firebase_dry = (
        os.getenv("DRY_RUN", "").lower() == "true"
        or os.getenv("FIREBASE_DRY_RUN", "").lower() == "true"
    )
    if firebase_dry:
        _dry_run = True
        return   # no Firebase needed

    if firebase_admin._apps:
        return   # already initialised (e.g. during tests)

    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if not project_id:
        raise EnvironmentError(
            "FIREBASE_PROJECT_ID is not set. Add it to orchestrator/.env"
        )

    # Uses Application Default Credentials — works locally (gcloud auth) and on Cloud Run
    firebase_admin.initialize_app(
        credential=credentials.ApplicationDefault(),
        options={"projectId": project_id},
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_firestore() -> firestore.client:
    return firestore.client()


async def _run_in_thread(fn):
    """Run a blocking Firestore call in a thread pool so FastAPI's event loop isn't blocked."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _msg_to_dict(msg: A2AMessage) -> dict:
    """Serialise an A2AMessage to a plain dict for Firestore storage."""
    return {
        "a2a_version":  msg.a2a_version,
        "session_id":   msg.session_id,
        "turn":         msg.turn,
        "sender":       msg.sender.value,
        "receiver":     msg.receiver.value,
        "timestamp":    msg.timestamp.isoformat(),
        "intent":       msg.intent.value,
        "product_id":   msg.product_id,
        "display_text": msg.display_text,
        "reasoning":    msg.reasoning,
        "constraints":  msg.constraints,
        "proposed_terms": msg.proposed_terms.model_dump() if msg.proposed_terms else None,
    }


def _session_to_dict(session: NegotiationSession) -> dict:
    """Serialise a NegotiationSession to a Firestore-safe dict."""
    return {
        "session_id":  session.session_id,
        "mode":        session.mode.value,
        "persona":     session.persona.value if session.persona else None,
        "product_sku": session.product_sku,
        "status":      session.status.value,
        "turn_count":  session.turn_count,
        "final_deal":  session.final_deal.model_dump() if session.final_deal else None,
        "created_at":  session.created_at.isoformat(),
        "turns":       [_msg_to_dict(m) for m in session.turns],
    }


def _dict_to_session(data: dict) -> NegotiationSession:
    """Deserialise a Firestore dict back into a NegotiationSession."""
    from models import Intent, Sender
    turns = []
    for t in data.get("turns", []):
        terms_data = t.get("proposed_terms")
        turns.append(A2AMessage(
            a2a_version=   t["a2a_version"],
            session_id=    t["session_id"],
            turn=          t["turn"],
            sender=        Sender(t["sender"]),
            receiver=      Sender(t["receiver"]),
            timestamp=     datetime.fromisoformat(t["timestamp"]),
            intent=        Intent(t["intent"]),
            product_id=    t.get("product_id"),
            display_text=  t.get("display_text"),
            reasoning=     t.get("reasoning"),
            constraints=   t.get("constraints", []),
            proposed_terms=ProposedTerms(**terms_data) if terms_data else None,
        ))

    final_deal_data = data.get("final_deal")
    return NegotiationSession(
        session_id=  data["session_id"],
        mode=        Mode(data["mode"]),
        persona=     Persona(data["persona"]) if data.get("persona") else None,
        product_sku= data["product_sku"],
        status=      SessionStatus(data["status"]),
        turns=       turns,
        final_deal=  ProposedTerms(**final_deal_data) if final_deal_data else None,
        created_at=  datetime.fromisoformat(data["created_at"]),
    )


# ---------------------------------------------------------------------------
# Product catalogue — read from Firestore
# ---------------------------------------------------------------------------

async def get_product(sku: str) -> Product:
    """Fetch a product document from Firestore by SKU. Raises ValueError if not found."""
    if _dry_run:
        data = _DRY_RUN_PRODUCTS.get(sku)
        if not data:
            raise ValueError(f"Product not found: {sku}")
        return Product(data)

    def _fetch():
        doc = _get_firestore().collection("products").document(sku).get()
        if not doc.exists:
            raise ValueError(f"Product not found: {sku}")
        return doc.to_dict()

    data = await _run_in_thread(_fetch)
    return Product(data)


# ---------------------------------------------------------------------------
# Session CRUD — Firestore (or in-memory in dry-run mode)
# ---------------------------------------------------------------------------

async def create_session(session: NegotiationSession) -> None:
    """Write a new session document to Firestore."""
    if _dry_run:
        _sessions[session.session_id] = session
        return

    def _write():
        _get_firestore().collection("sessions").document(session.session_id).set(
            _session_to_dict(session)
        )
    await _run_in_thread(_write)


async def get_session(session_id: str) -> NegotiationSession:
    """Read a session document from Firestore. Raises ValueError if not found."""
    if _dry_run:
        session = _sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        return session

    def _fetch():
        doc = _get_firestore().collection("sessions").document(session_id).get()
        if not doc.exists:
            raise ValueError(f"Session not found: {session_id}")
        return doc.to_dict()

    data = await _run_in_thread(_fetch)
    return _dict_to_session(data)


async def update_session(session: NegotiationSession) -> None:
    """Persist the full session state to Firestore after each turn."""
    if _dry_run:
        _sessions[session.session_id] = session   # already a live object; just re-save
        return

    def _update():
        _get_firestore().collection("sessions").document(session.session_id).set(
            _session_to_dict(session), merge=True
        )
    await _run_in_thread(_update)


async def list_sessions() -> list:
    """Return all sessions (used by the merchant dashboard)."""
    if _dry_run:
        return list(_sessions.values())

    def _fetch_all():
        return [_dict_to_session(d.to_dict()) for d in _get_firestore().collection("sessions").stream()]

    return await _run_in_thread(_fetch_all)


# ---------------------------------------------------------------------------
# Product catalogue updates — editable via merchant UI
# ---------------------------------------------------------------------------

async def list_products() -> list:
    """Return all products as raw dicts (merchant admin view)."""
    if _dry_run:
        return [dict(p) for p in _DRY_RUN_PRODUCTS.values()]

    def _fetch():
        return [d.to_dict() for d in _get_firestore().collection("products").stream()]

    return await _run_in_thread(_fetch)


async def create_product(data: dict) -> dict:
    """
    Create a new product. Raises ValueError if the SKU already exists.
    Returns the created product dict.
    """
    sku = data["sku"]
    if _dry_run:
        if sku in _DRY_RUN_PRODUCTS:
            raise ValueError(f"Product already exists: {sku}")
        _DRY_RUN_PRODUCTS[sku] = dict(data)
        return dict(_DRY_RUN_PRODUCTS[sku])

    def _create():
        ref = _get_firestore().collection("products").document(sku)
        if ref.get().exists:
            raise ValueError(f"Product already exists: {sku}")
        ref.set(data)
        return ref.get().to_dict()

    return await _run_in_thread(_create)


async def delete_product(sku: str) -> None:
    """Delete a product by SKU. Raises ValueError if not found."""
    if _dry_run:
        if sku not in _DRY_RUN_PRODUCTS:
            raise ValueError(f"Product not found: {sku}")
        del _DRY_RUN_PRODUCTS[sku]
        return

    def _delete():
        ref = _get_firestore().collection("products").document(sku)
        if not ref.get().exists:
            raise ValueError(f"Product not found: {sku}")
        ref.delete()

    await _run_in_thread(_delete)


async def update_product(sku: str, updates: dict) -> dict:
    """
    Patch a product's fields. Returns the updated product dict.
    Only provided keys are changed (merge semantics).
    """
    if _dry_run:
        if sku not in _DRY_RUN_PRODUCTS:
            raise ValueError(f"Product not found: {sku}")
        _DRY_RUN_PRODUCTS[sku].update({k: v for k, v in updates.items() if v is not None})
        return dict(_DRY_RUN_PRODUCTS[sku])

    def _update():
        ref = _get_firestore().collection("products").document(sku)
        if not ref.get().exists:
            raise ValueError(f"Product not found: {sku}")
        ref.set({k: v for k, v in updates.items() if v is not None}, merge=True)
        return ref.get().to_dict()

    return await _run_in_thread(_update)


# ---------------------------------------------------------------------------
# Merchant agent config — editable via merchant UI
# ---------------------------------------------------------------------------

_merchant_config: dict = {
    "agent_name": "Alex",
    "role":       "Senior Sales Representative",
    "company":    "MadeinMind Commerce",
}


async def get_merchant_config() -> dict:
    """Return current merchant agent configuration."""
    if _dry_run:
        return dict(_merchant_config)

    def _fetch():
        doc = _get_firestore().collection("config").document("merchant").get()
        return doc.to_dict() if doc.exists else dict(_merchant_config)

    return await _run_in_thread(_fetch)


async def update_merchant_config(updates: dict) -> dict:
    """Merge-patch the merchant agent config. Returns the updated config."""
    if _dry_run:
        _merchant_config.update(updates)
        return dict(_merchant_config)

    def _update():
        ref = _get_firestore().collection("config").document("merchant")
        ref.set(updates, merge=True)
        doc = ref.get()
        return doc.to_dict() if doc.exists else dict(_merchant_config)

    return await _run_in_thread(_update)


async def append_session_metrics(session_id: str, calls: list[dict]) -> None:
    """
    Write LLM call records for a turn to sessions/{session_id}/llm_calls subcollection.
    Skipped in dry-run mode (metrics live only in the in-memory store).
    """
    if not calls or _dry_run:
        return

    def _write():
        fs   = _get_firestore()
        coll = fs.collection("sessions").document(session_id).collection("llm_calls")
        for call in calls:
            coll.add(call)   # Firestore auto-generates a document ID per call

    await _run_in_thread(_write)


