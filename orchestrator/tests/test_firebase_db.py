"""
Tests for firebase_db.py — Firestore only (Realtime DB removed).
Firebase Admin SDK is fully mocked. No real Firebase project needed.
Run: python -m pytest orchestrator/tests/test_firebase_db.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

os.environ["GEMINI_API_KEY"]     = "test-key-placeholder"
os.environ["FIREBASE_PROJECT_ID"] = "test-project"

from models import (
    A2AMessage, NegotiationSession, ProposedTerms,
    Intent, Sender, Mode, Persona, SessionStatus
)
from merchant import Product
import firebase_db as fdb


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PRODUCT_DATA = {
    "sku": "SKU-001",
    "name": "Sony WH-1000XM6",
    "list_price": 99.99,
    "price_floor": 79.99,
    "bulk_tiers": [{"min_qty": 10, "discount_pct": 8}],
    "delivery_options": ["standard_5d", "express_2d"],
    "vouchers_eligible": True,
}

def make_session() -> NegotiationSession:
    return NegotiationSession(mode=Mode.AI, persona=Persona.BUDGET_SHOPPER, product_sku="SKU-001")

def make_msg(session: NegotiationSession, turn=1) -> A2AMessage:
    return A2AMessage(
        session_id=session.session_id, turn=turn,
        sender=Sender.SHOPPING_AGENT, receiver=Sender.MERCHANT_AGENT,
        intent=Intent.QUERY, product_id="SKU-001",
        display_text="What is your best price?",
        proposed_terms=ProposedTerms(unit_price=85.00, quantity=25),
    )

def _make_firestore_mock(return_data: dict | None = None):
    mock_doc = MagicMock()
    mock_doc.exists = return_data is not None
    mock_doc.to_dict.return_value = return_data
    mock_col = MagicMock()
    mock_col.document.return_value.get.return_value = mock_doc
    mock_col.document.return_value.set.return_value = None
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_col
    return mock_client


# ---------------------------------------------------------------------------
# Serialisation round-trips — no Firebase needed
# ---------------------------------------------------------------------------

def test_msg_to_dict_round_trip():
    session = make_session()
    msg = make_msg(session)
    d = fdb._msg_to_dict(msg)
    assert d["turn"]         == 1
    assert d["sender"]       == "shopping-agent"
    assert d["intent"]       == "query"
    assert d["display_text"] == "What is your best price?"
    assert d["proposed_terms"]["unit_price"] == 85.00


def test_session_to_dict_contains_all_fields():
    session = make_session()
    session.turns.append(make_msg(session))
    d = fdb._session_to_dict(session)
    assert d["session_id"]  == session.session_id
    assert d["mode"]        == "ai"
    assert d["persona"]     == "budget_shopper"
    assert d["status"]      == "active"
    assert d["turn_count"]  == 1
    assert len(d["turns"])  == 1


def test_session_round_trip_via_dicts():
    session = make_session()
    session.turns.append(make_msg(session))
    d = fdb._session_to_dict(session)
    restored = fdb._dict_to_session(d)
    assert restored.session_id        == session.session_id
    assert restored.mode              == Mode.AI
    assert restored.persona           == Persona.BUDGET_SHOPPER
    assert restored.status            == SessionStatus.ACTIVE
    assert restored.turn_count        == 1
    assert restored.turns[0].intent   == Intent.QUERY


def test_session_round_trip_with_final_deal():
    session = make_session()
    session.status     = SessionStatus.ACCEPTED
    session.final_deal = ProposedTerms(unit_price=89.99, quantity=25, delivery_days=5)
    d = fdb._session_to_dict(session)
    restored = fdb._dict_to_session(d)
    assert restored.status                   == SessionStatus.ACCEPTED
    assert restored.final_deal.unit_price    == 89.99
    assert restored.final_deal.delivery_days == 5


def test_human_session_round_trip_no_persona():
    session = NegotiationSession(mode=Mode.HUMAN, product_sku="SKU-002")
    d = fdb._session_to_dict(session)
    restored = fdb._dict_to_session(d)
    assert restored.mode    == Mode.HUMAN
    assert restored.persona is None


# ---------------------------------------------------------------------------
# Firestore calls — mocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_product_returns_product():
    mock_client = _make_firestore_mock(PRODUCT_DATA)
    with patch("firebase_db.firestore") as mock_fs:
        mock_fs.client.return_value = mock_client
        product = await fdb.get_product("SKU-001")
    assert isinstance(product, Product)
    assert product.sku  == "SKU-001"
    assert product.name == "Sony WH-1000XM6"


@pytest.mark.asyncio
async def test_get_product_raises_if_not_found():
    mock_client = _make_firestore_mock(None)
    with patch("firebase_db.firestore") as mock_fs:
        mock_fs.client.return_value = mock_client
        with pytest.raises(ValueError, match="Product not found"):
            await fdb.get_product("MISSING-SKU")


@pytest.mark.asyncio
async def test_create_session_calls_firestore_set():
    session = make_session()
    mock_client = _make_firestore_mock()
    with patch("firebase_db.firestore") as mock_fs:
        mock_fs.client.return_value = mock_client
        await fdb.create_session(session)
    mock_client.collection.assert_called_with("sessions")
    mock_client.collection().document.assert_called_with(session.session_id)
    mock_client.collection().document().set.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_returns_session():
    session = make_session()
    session_dict = fdb._session_to_dict(session)
    mock_client = _make_firestore_mock(session_dict)
    with patch("firebase_db.firestore") as mock_fs:
        mock_fs.client.return_value = mock_client
        restored = await fdb.get_session(session.session_id)
    assert restored.session_id == session.session_id
    assert restored.mode       == Mode.AI


@pytest.mark.asyncio
async def test_get_session_raises_if_not_found():
    mock_client = _make_firestore_mock(None)
    with patch("firebase_db.firestore") as mock_fs:
        mock_fs.client.return_value = mock_client
        with pytest.raises(ValueError, match="Session not found"):
            await fdb.get_session("unknown-id")


@pytest.mark.asyncio
async def test_update_session_calls_firestore_set():
    session = make_session()
    mock_client = _make_firestore_mock()
    with patch("firebase_db.firestore") as mock_fs:
        mock_fs.client.return_value = mock_client
        await fdb.update_session(session)
    mock_client.collection().document().set.assert_called_once()
