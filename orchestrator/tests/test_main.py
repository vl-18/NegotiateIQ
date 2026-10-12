"""
Tests for main.py — FastAPI routes including SSE stream endpoint.
All external dependencies (Gemini, Firestore, shopping/merchant) are mocked.
Run: python -m pytest orchestrator/tests/test_main.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

os.environ["GEMINI_API_KEY"]      = "test-key-placeholder"
os.environ["FIREBASE_PROJECT_ID"] = "test-project"

from models import (
    NegotiationSession, A2AMessage, ProposedTerms,
    Intent, Sender, Mode, Persona, SessionStatus
)
from merchant import Product


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """TestClient with init functions mocked so app starts without real services."""
    with patch("main.init_gemini"), patch("main.init_firebase"):
        from main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

PRODUCT_DATA = {
    "sku": "SKU-001", "name": "Sony WH-1000XM6",
    "list_price": 99.99, "price_floor": 79.99,
    "bulk_tiers": [{"min_qty": 10, "discount_pct": 8}],
    "delivery_options": ["standard_5d", "express_2d"],
    "vouchers_eligible": True,
}

def make_session(mode=Mode.AI, persona=Persona.BUDGET_SHOPPER) -> NegotiationSession:
    return NegotiationSession(mode=mode, persona=persona, product_sku="SKU-001")

def make_shopping_msg(session) -> A2AMessage:
    return A2AMessage(
        session_id=session.session_id, turn=1,
        sender=Sender.SHOPPING_AGENT, receiver=Sender.MERCHANT_AGENT,
        intent=Intent.QUERY, display_text="What's your best price?",
    )

def make_merchant_msg(session) -> A2AMessage:
    return A2AMessage(
        session_id=session.session_id, turn=2,
        sender=Sender.MERCHANT_AGENT, receiver=Sender.SHOPPING_AGENT,
        intent=Intent.COUNTER_OFFER, display_text="I can offer $92.99 each.",
        proposed_terms=ProposedTerms(unit_price=92.99, quantity=25, delivery_days=5),
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /session/start
# ---------------------------------------------------------------------------

def test_start_session_ai_mode(client):
    with patch("main.get_product", new_callable=AsyncMock, return_value=Product(PRODUCT_DATA)), \
         patch("main.create_session", new_callable=AsyncMock):
        resp = client.post("/session/start", json={
            "product_sku": "SKU-001", "mode": "ai", "persona": "budget_shopper",
        })
    assert resp.status_code == 201
    body = resp.json()
    assert "session_id" in body
    assert body["mode"]   == "ai"
    assert body["status"] == "active"


def test_start_session_human_mode(client):
    with patch("main.get_product", new_callable=AsyncMock, return_value=Product(PRODUCT_DATA)), \
         patch("main.create_session", new_callable=AsyncMock):
        resp = client.post("/session/start", json={"product_sku": "SKU-001", "mode": "human"})
    assert resp.status_code == 201
    assert resp.json()["persona"] is None


def test_start_session_ai_without_persona_returns_400(client):
    with patch("main.get_product", new_callable=AsyncMock, return_value=Product(PRODUCT_DATA)):
        resp = client.post("/session/start", json={"product_sku": "SKU-001", "mode": "ai"})
    assert resp.status_code == 400


def test_start_session_unknown_sku_returns_404(client):
    with patch("main.get_product", new_callable=AsyncMock, side_effect=ValueError("not found")):
        resp = client.post("/session/start", json={
            "product_sku": "MISSING", "mode": "ai", "persona": "budget_shopper",
        })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /session/{id}/turn
# ---------------------------------------------------------------------------

def test_run_turn_returns_both_messages(client):
    session = make_session()
    shopping_msg = make_shopping_msg(session)
    merchant_msg = make_merchant_msg(session)

    with patch("main.get_session",    new_callable=AsyncMock, return_value=session), \
         patch("main.get_product",    new_callable=AsyncMock, return_value=Product(PRODUCT_DATA)), \
         patch("main.shopping_turn",  new_callable=AsyncMock, return_value=shopping_msg), \
         patch("main.merchant_turn",  new_callable=AsyncMock, return_value=merchant_msg), \
         patch("main.update_session", new_callable=AsyncMock):
        resp = client.post(f"/session/{session.session_id}/turn", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["shopping_turn"]["sender"] == "shopping-agent"
    assert body["merchant_turn"]["sender"] == "merchant-agent"
    assert body["session_status"]          == "active"


def test_run_turn_human_mode_passes_message_text(client):
    session = make_session(mode=Mode.HUMAN, persona=None)
    shopping_msg = A2AMessage(
        session_id=session.session_id, turn=1,
        sender=Sender.HUMAN, receiver=Sender.MERCHANT_AGENT,
        intent=Intent.QUERY, display_text="Can you do $88?",
    )
    with patch("main.get_session",    new_callable=AsyncMock, return_value=session), \
         patch("main.get_product",    new_callable=AsyncMock, return_value=Product(PRODUCT_DATA)), \
         patch("main.shopping_turn",  new_callable=AsyncMock, return_value=shopping_msg) as mock_shop, \
         patch("main.merchant_turn",  new_callable=AsyncMock, return_value=make_merchant_msg(session)), \
         patch("main.update_session", new_callable=AsyncMock):
        resp = client.post(f"/session/{session.session_id}/turn", json={"message_text": "Can you do $88?"})

    assert resp.status_code == 200
    assert mock_shop.call_args.kwargs["message_text"] == "Can you do $88?"


def test_run_turn_session_not_found_returns_404(client):
    with patch("main.get_session", new_callable=AsyncMock, side_effect=ValueError("not found")):
        resp = client.post("/session/bad-id/turn", json={})
    assert resp.status_code == 404


def test_run_turn_on_finished_session_returns_409(client):
    session = make_session()
    session.status = SessionStatus.ACCEPTED
    with patch("main.get_session",  new_callable=AsyncMock, return_value=session), \
         patch("main.get_product",  new_callable=AsyncMock, return_value=Product(PRODUCT_DATA)):
        resp = client.post(f"/session/{session.session_id}/turn", json={})
    assert resp.status_code == 409


def test_run_turn_buyer_accepts_skips_merchant(client):
    """If buyer accepts, merchant turn is not called."""
    session = make_session()
    accepted_msg = A2AMessage(
        session_id=session.session_id, turn=1,
        sender=Sender.SHOPPING_AGENT, receiver=Sender.MERCHANT_AGENT,
        intent=Intent.ACCEPT, display_text="Deal!",
    )

    async def shopping_side_effect(*args, **kwargs):
        session.status     = SessionStatus.ACCEPTED
        session.final_deal = ProposedTerms(unit_price=92.99)
        session.turns.append(accepted_msg)
        return accepted_msg

    with patch("main.get_session",    new_callable=AsyncMock, return_value=session), \
         patch("main.get_product",    new_callable=AsyncMock, return_value=Product(PRODUCT_DATA)), \
         patch("main.shopping_turn",  new_callable=AsyncMock, side_effect=shopping_side_effect), \
         patch("main.merchant_turn",  new_callable=AsyncMock) as mock_merchant, \
         patch("main.update_session", new_callable=AsyncMock):
        resp = client.post(f"/session/{session.session_id}/turn", json={})

    assert resp.status_code == 200
    assert resp.json()["session_status"] == "accepted"
    assert resp.json()["merchant_turn"]  is None
    mock_merchant.assert_not_called()


# ---------------------------------------------------------------------------
# GET /session/{id}/stream — SSE endpoint
# ---------------------------------------------------------------------------

def test_stream_session_not_found_returns_404(client):
    """Opening a stream for an unknown session returns 404."""
    with patch("main.get_session", new_callable=AsyncMock, side_effect=ValueError("not found")):
        resp = client.get("/session/bad-id/stream")
    assert resp.status_code == 404


def test_stream_delivers_events_from_queue(client):
    """Events put into the SSE queue are delivered to the client."""
    import main as main_module

    session = make_session()

    # Pre-load two events and a close sentinel into the queue
    queue = asyncio.Queue()
    queue.put_nowait(json.dumps({"type": "turn", "turn": 1, "sender": "shopping-agent"}))
    queue.put_nowait(json.dumps({"type": "turn", "turn": 2, "sender": "merchant-agent"}))
    queue.put_nowait(None)   # sentinel → close stream

    main_module._sse_queues[session.session_id] = queue

    with patch("main.get_session", new_callable=AsyncMock, return_value=session):
        with client.stream("GET", f"/session/{session.session_id}/stream") as resp:
            assert resp.status_code == 200
            lines = []
            for line in resp.iter_lines():
                if line:
                    lines.append(line)

    # SSE yields: "event: close" line + "data: {}" line for close, and "data: <json>" for turns
    event_lines = [l for l in lines if l.startswith("event:")]
    data_lines  = [l for l in lines if l.startswith("data:")]

    # Two turn data payloads + one close data payload = 3 data lines total
    assert len(data_lines)  == 3
    assert len(event_lines) == 1   # only the close event has an explicit event: label
    assert "close" in event_lines[0]

    # First two data lines are the turn events
    first_event = json.loads(data_lines[0].replace("data: ", ""))
    assert first_event["sender"] == "shopping-agent"
    second_event = json.loads(data_lines[1].replace("data: ", ""))
    assert second_event["sender"] == "merchant-agent"


# ---------------------------------------------------------------------------
# GET /session/{id}/status
# ---------------------------------------------------------------------------

def test_session_status_returns_state(client):
    session = make_session()
    session.turns.append(make_shopping_msg(session))
    with patch("main.get_session", new_callable=AsyncMock, return_value=session):
        resp = client.get(f"/session/{session.session_id}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"]     == "active"
    assert body["turn_count"] == 1
    assert body["turns"][0]["sender"] == "shopping-agent"


def test_session_status_not_found_returns_404(client):
    with patch("main.get_session", new_callable=AsyncMock, side_effect=ValueError("not found")):
        resp = client.get("/session/bad-id/status")
    assert resp.status_code == 404
