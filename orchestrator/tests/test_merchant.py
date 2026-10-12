"""
Tests for merchant.py — rules engine, context builder, and merchant_turn.
Rules engine tests need no mocking. merchant_turn mocks Gemini.
Run: python -m pytest orchestrator/tests/test_merchant.py -v
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
from state_machine import StateMachine
from merchant import Product, apply_rules, should_reject, build_negotiation_context, merchant_turn


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

PRODUCT_DATA = {
    "sku": "SKU-001",
    "name": "Sony WH-1000XM6",
    "list_price": 99.99,
    "price_floor": 79.99,
    "bulk_tiers": [
        {"min_qty": 10, "discount_pct": 8},
        {"min_qty": 50, "discount_pct": 15},
    ],
    "delivery_options": ["standard_5d", "express_2d", "next_day"],
    "vouchers_eligible": True,
}

def make_product() -> Product:
    return Product(PRODUCT_DATA)

def make_session() -> NegotiationSession:
    return NegotiationSession(mode=Mode.AI, persona=Persona.BUDGET_SHOPPER, product_sku="SKU-001")

def make_buyer_msg(session: NegotiationSession, unit_price=None, quantity=25, delivery_days=5, intent=Intent.QUERY) -> A2AMessage:
    terms = ProposedTerms(unit_price=unit_price, quantity=quantity, delivery_days=delivery_days) if unit_price else None
    return A2AMessage(
        session_id=session.session_id, turn=1,
        sender=Sender.SHOPPING_AGENT, receiver=Sender.MERCHANT_AGENT,
        intent=intent, proposed_terms=terms,
        display_text="What's your best price for 25 units?",
    )


# ---------------------------------------------------------------------------
# Rules engine — apply_rules
# ---------------------------------------------------------------------------

def test_opens_at_list_price_with_no_prior_offer():
    """First merchant offer starts at list price (no bulk, no prior offer)."""
    product = make_product()
    terms, intent = apply_rules(product, None, turn_number=2, is_final_offer=False, previous_merchant_price=None)
    assert terms.unit_price == product.list_price
    assert intent == Intent.COUNTER_OFFER


def test_bulk_tier_10_units_applies_8pct_discount():
    """10+ units triggers 8% bulk discount off list price."""
    product = make_product()
    buyer_terms = ProposedTerms(quantity=10, unit_price=90.00)
    terms, _ = apply_rules(product, buyer_terms, turn_number=2, is_final_offer=False, previous_merchant_price=None)
    expected = round(product.list_price * 0.92, 2)   # 8% off
    assert terms.unit_price <= expected


def test_bulk_tier_50_units_applies_15pct_discount():
    """50+ units triggers 15% bulk discount."""
    product = make_product()
    buyer_terms = ProposedTerms(quantity=50, unit_price=80.00)
    terms, _ = apply_rules(product, buyer_terms, turn_number=2, is_final_offer=False, previous_merchant_price=None)
    expected_bulk = round(product.list_price * 0.85, 2)   # 15% off
    # Offered price may be further reduced by split logic, but never below floor
    assert terms.unit_price >= product.price_floor
    assert terms.unit_price <= expected_bulk


def test_price_never_goes_below_floor():
    """No matter how aggressive the buyer, price never goes below price_floor."""
    product = make_product()
    buyer_terms = ProposedTerms(quantity=100, unit_price=10.00)   # way below floor
    terms, _ = apply_rules(product, buyer_terms, turn_number=4, is_final_offer=False, previous_merchant_price=80.00)
    assert terms.unit_price >= product.price_floor


def test_final_offer_includes_loyalty_voucher():
    """On the final offer turn, a voucher is attached when product is eligible."""
    product = make_product()
    buyer_terms = ProposedTerms(quantity=25, unit_price=85.00)
    terms, intent = apply_rules(product, buyer_terms, turn_number=7, is_final_offer=True, previous_merchant_price=90.00)
    assert intent == Intent.FINAL_OFFER
    assert terms.voucher_requested == "LOYALTY10"


def test_non_final_offer_has_no_voucher():
    """Voucher is not offered on regular counter-offer turns."""
    product = make_product()
    terms, intent = apply_rules(product, None, turn_number=2, is_final_offer=False, previous_merchant_price=None)
    assert intent == Intent.COUNTER_OFFER
    assert terms.voucher_requested is None


def test_buyer_requests_fast_delivery_gets_2_days():
    """When buyer asks for fast delivery, merchant offers 2-day express."""
    product = make_product()
    buyer_terms = ProposedTerms(quantity=10, unit_price=90.00, delivery_days=2)
    terms, _ = apply_rules(product, buyer_terms, turn_number=2, is_final_offer=False, previous_merchant_price=None)
    assert terms.delivery_days == 2


# ---------------------------------------------------------------------------
# Reject logic — should_reject
# ---------------------------------------------------------------------------

def test_should_reject_extreme_low_price():
    """Buyer asking below the max-discount threshold triggers rejection."""
    product = make_product()
    # Max discount = 20%, so floor for reject is 99.99 * 0.80 = 79.99 (exactly)
    # Asking below 79.99 should reject
    buyer_terms = ProposedTerms(unit_price=70.00)
    assert should_reject(product, buyer_terms) is True


def test_should_not_reject_reasonable_ask():
    """Reasonable ask within 20% discount is not rejected."""
    product = make_product()
    buyer_terms = ProposedTerms(unit_price=85.00)   # ~15% off — acceptable
    assert should_reject(product, buyer_terms) is False


def test_should_not_reject_none_terms():
    """No terms (query intent) never triggers rejection."""
    product = make_product()
    assert should_reject(product, None) is False


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def test_build_context_contains_product_name():
    """Context string includes product name and SKU."""
    session = make_session()
    product = make_product()
    context = build_negotiation_context(session, product)
    assert product.name in context
    assert product.sku in context


def test_build_context_includes_turn_history():
    """Context includes previous turns' display text."""
    session = make_session()
    product = make_product()
    msg = make_buyer_msg(session)
    session.turns.append(msg)
    context = build_negotiation_context(session, product)
    assert "What's your best price for 25 units?" in context


# ---------------------------------------------------------------------------
# merchant_turn — full flow (Gemini mocked)
# ---------------------------------------------------------------------------

MOCK_GEMINI_REPLY = json.dumps({
    "intent": "counter_offer",
    "proposed_terms": {"unit_price": 92.99, "quantity": 25, "delivery_days": 5, "voucher_offered": None},
    "display_text": "For 25 units I can offer $92.99 each with free standard shipping.",
    "reasoning": "Applying 7% bulk discount.",
})


@pytest.mark.asyncio
async def test_merchant_turn_returns_a2a_message():
    """merchant_turn produces a valid A2AMessage and appends it to the session."""
    session = make_session()
    product = make_product()
    sm = StateMachine(session)

    buyer_msg = make_buyer_msg(session, unit_price=85.00, quantity=25)
    # Apply buyer turn first so alternation is valid
    sm.apply(buyer_msg)

    with patch("merchant.call_merchant_agent", new_callable=AsyncMock, return_value=json.loads(MOCK_GEMINI_REPLY)):
        result = await merchant_turn(session, product, sm, buyer_msg)

    assert isinstance(result, A2AMessage)
    assert result.sender == Sender.MERCHANT_AGENT
    assert result.intent in (Intent.COUNTER_OFFER, Intent.FINAL_OFFER)
    assert result.proposed_terms is not None
    assert result.proposed_terms.unit_price >= product.price_floor
    assert session.turn_count == 2   # buyer turn + merchant turn


@pytest.mark.asyncio
async def test_merchant_rejects_extreme_buyer_demand():
    """If buyer asks far below floor, merchant_turn returns a REJECT without calling Gemini."""
    session = make_session()
    product = make_product()
    sm = StateMachine(session)

    buyer_msg = make_buyer_msg(session, unit_price=40.00, quantity=25, intent=Intent.COUNTER_OFFER)
    sm.apply(buyer_msg)

    # Gemini should NOT be called on a hard reject
    with patch("merchant.call_merchant_agent", new_callable=AsyncMock) as mock_gemini:
        result = await merchant_turn(session, product, sm, buyer_msg)
        mock_gemini.assert_not_called()

    assert result.intent == Intent.REJECT
    assert session.status == SessionStatus.REJECTED


@pytest.mark.asyncio
async def test_merchant_turn_uses_fallback_if_gemini_fails():
    """If Gemini raises an exception, merchant_turn still returns a valid message."""
    session = make_session()
    product = make_product()
    sm = StateMachine(session)

    buyer_msg = make_buyer_msg(session, unit_price=88.00, quantity=25)
    sm.apply(buyer_msg)

    with patch("merchant.call_merchant_agent", new_callable=AsyncMock, side_effect=ValueError("API error")):
        result = await merchant_turn(session, product, sm, buyer_msg)

    assert result.intent in (Intent.COUNTER_OFFER, Intent.FINAL_OFFER)
    assert result.display_text  # fallback text was generated
    assert result.proposed_terms.unit_price >= product.price_floor
