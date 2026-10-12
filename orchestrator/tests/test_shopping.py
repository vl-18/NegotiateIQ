"""
Tests for shopping.py — AI mode, human mode, context builder, router.
Gemini is mocked for AI mode tests. Human mode needs no mocking.
Run: python -m pytest orchestrator/tests/test_shopping.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import json
import pytest
from unittest.mock import patch, AsyncMock

os.environ["GEMINI_API_KEY"] = "test-key-placeholder"

from models import (
    A2AMessage, NegotiationSession, ProposedTerms,
    Intent, Sender, Mode, Persona, SessionStatus
)
from merchant import Product
from state_machine import StateMachine
from shopping import (
    build_shopping_context, _parse_intent,
    shopping_turn_ai, shopping_turn_human, shopping_turn
)


# ---------------------------------------------------------------------------
# Shared fixtures
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

def make_product() -> Product:
    return Product(PRODUCT_DATA)

def make_ai_session() -> NegotiationSession:
    return NegotiationSession(mode=Mode.AI, persona=Persona.BUDGET_SHOPPER, product_sku="SKU-001")

def make_human_session() -> NegotiationSession:
    return NegotiationSession(mode=Mode.HUMAN, product_sku="SKU-001")

# A mock Gemini response from the shopping agent
MOCK_AI_RESPONSE = {
    "intent": "counter_offer",
    "proposed_terms": {"unit_price": 85.00, "quantity": 25, "delivery_days": 5, "voucher_requested": None},
    "display_text": "Can you do $85 per unit? That's my maximum budget.",
    "reasoning": "Pushing price down to stay within budget.",
}

MOCK_ACCEPT_RESPONSE = {
    "intent": "accept",
    "proposed_terms": {"unit_price": 92.99, "quantity": 25, "delivery_days": 5, "voucher_requested": None},
    "display_text": "That works for me — let's do the deal.",
    "reasoning": "Merchant's offer is within acceptable range.",
}


# ---------------------------------------------------------------------------
# Intent parser
# ---------------------------------------------------------------------------

def test_parse_valid_intents():
    assert _parse_intent("counter_offer") == Intent.COUNTER_OFFER
    assert _parse_intent("accept")        == Intent.ACCEPT
    assert _parse_intent("reject")        == Intent.REJECT
    assert _parse_intent("query")         == Intent.QUERY


def test_parse_unknown_intent_defaults_to_query():
    """Unknown intent strings default to QUERY so the session can continue."""
    assert _parse_intent("bargain_hard") == Intent.QUERY
    assert _parse_intent("")             == Intent.QUERY


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def test_context_includes_product_and_turn_info():
    session = make_ai_session()
    product = make_product()
    context = build_shopping_context(session, product)
    assert product.name in context
    assert "Turn 1 of 8" in context


def test_context_labels_merchant_correctly():
    """Merchant messages are labelled 'Merchant' in the shopping context."""
    session = make_ai_session()
    product = make_product()

    # Add a mock merchant turn to history
    session.turns.append(A2AMessage(
        session_id=session.session_id, turn=1,
        sender=Sender.MERCHANT_AGENT, receiver=Sender.SHOPPING_AGENT,
        intent=Intent.COUNTER_OFFER,
        display_text="Our list price is $99.99.",
    ))
    context = build_shopping_context(session, product)
    assert "Merchant" in context
    assert "Our list price is $99.99." in context


# ---------------------------------------------------------------------------
# Human mode
# ---------------------------------------------------------------------------

def test_human_turn_wraps_message_in_a2a():
    """Human message is wrapped as a QUERY with sender=HUMAN."""
    session = make_human_session()
    product = make_product()
    sm = StateMachine(session)

    msg = shopping_turn_human(session, product, sm, "Can you do $90 per unit?")

    assert msg.sender == Sender.HUMAN
    assert msg.intent == Intent.QUERY
    assert msg.display_text == "Can you do $90 per unit?"
    assert session.turn_count == 1


def test_human_turn_strips_whitespace():
    """Leading/trailing whitespace is stripped from human messages."""
    session = make_human_session()
    product = make_product()
    sm = StateMachine(session)

    msg = shopping_turn_human(session, product, sm, "  Give me a better price.  ")
    assert msg.display_text == "Give me a better price."


def test_human_turn_appended_to_session():
    """Human turn is added to session.turns."""
    session = make_human_session()
    product = make_product()
    sm = StateMachine(session)

    shopping_turn_human(session, product, sm, "What about $88?")
    assert session.turn_count == 1
    assert session.turns[0].sender == Sender.HUMAN


# ---------------------------------------------------------------------------
# AI mode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_turn_returns_a2a_message():
    """AI mode calls Gemini and returns a properly formed A2AMessage."""
    session = make_ai_session()
    product = make_product()
    sm = StateMachine(session)

    with patch("shopping.call_shopping_agent", new_callable=AsyncMock, return_value=MOCK_AI_RESPONSE):
        msg = await shopping_turn_ai(session, product, sm)

    assert isinstance(msg, A2AMessage)
    assert msg.sender == Sender.SHOPPING_AGENT
    assert msg.intent == Intent.COUNTER_OFFER
    assert msg.proposed_terms.unit_price == 85.00
    assert session.turn_count == 1


@pytest.mark.asyncio
async def test_ai_turn_accept_intent_closes_session():
    """AI returning accept intent transitions session to ACCEPTED."""
    session = make_ai_session()
    product = make_product()
    sm = StateMachine(session)

    # Add a prior merchant offer so ACCEPT has something to agree to
    session.turns.append(A2AMessage(
        session_id=session.session_id, turn=0,
        sender=Sender.MERCHANT_AGENT, receiver=Sender.SHOPPING_AGENT,
        intent=Intent.COUNTER_OFFER,
        proposed_terms=ProposedTerms(unit_price=92.99, quantity=25),
    ))

    with patch("shopping.call_shopping_agent", new_callable=AsyncMock, return_value=MOCK_ACCEPT_RESPONSE):
        msg = await shopping_turn_ai(session, product, sm)

    assert msg.intent == Intent.ACCEPT
    assert session.status == SessionStatus.ACCEPTED


@pytest.mark.asyncio
async def test_ai_turn_fallback_on_gemini_failure():
    """If Gemini fails, AI mode falls back to a neutral QUERY without crashing."""
    session = make_ai_session()
    product = make_product()
    sm = StateMachine(session)

    with patch("shopping.call_shopping_agent", new_callable=AsyncMock, side_effect=ValueError("API error")):
        msg = await shopping_turn_ai(session, product, sm)

    assert msg.sender == Sender.SHOPPING_AGENT
    assert msg.intent == Intent.QUERY    # fallback intent
    assert msg.display_text              # fallback text was set
    assert session.turn_count == 1       # turn was still applied


# ---------------------------------------------------------------------------
# Router — shopping_turn
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_dispatches_to_ai_mode():
    """shopping_turn routes to AI path when session.mode == AI."""
    session = make_ai_session()
    product = make_product()
    sm = StateMachine(session)

    with patch("shopping.call_shopping_agent", new_callable=AsyncMock, return_value=MOCK_AI_RESPONSE):
        msg = await shopping_turn(session, product, sm)

    assert msg.sender == Sender.SHOPPING_AGENT


@pytest.mark.asyncio
async def test_router_dispatches_to_human_mode():
    """shopping_turn routes to human path when session.mode == HUMAN."""
    session = make_human_session()
    product = make_product()
    sm = StateMachine(session)

    msg = await shopping_turn(session, product, sm, message_text="What's your best offer?")
    assert msg.sender == Sender.HUMAN


@pytest.mark.asyncio
async def test_router_raises_if_human_message_empty():
    """Human mode with no message_text raises ValueError."""
    session = make_human_session()
    product = make_product()
    sm = StateMachine(session)

    with pytest.raises(ValueError, match="message_text is required"):
        await shopping_turn(session, product, sm, message_text="")
