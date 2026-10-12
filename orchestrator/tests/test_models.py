"""
Smoke test for models.py.
Run: python -m pytest orchestrator/tests/test_models.py -v
No external services required.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models import (
    A2AMessage, NegotiationSession, ProposedTerms,
    StartSessionRequest, TurnRequest,
    Intent, Mode, Persona, Sender, SessionStatus
)


def test_proposed_terms_all_optional():
    """ProposedTerms can be empty — valid for accept/reject intents."""
    terms = ProposedTerms()
    assert terms.unit_price is None
    assert terms.quantity is None


def test_a2a_message_defaults():
    """A2AMessage auto-fills session_id, timestamp, and a2a_version."""
    msg = A2AMessage(
        turn=1,
        sender=Sender.SHOPPING_AGENT,
        receiver=Sender.MERCHANT_AGENT,
        intent=Intent.QUERY,
    )
    assert msg.a2a_version == "1.0"
    assert msg.session_id is not None
    assert msg.timestamp is not None
    assert msg.constraints == []


def test_a2a_message_with_terms():
    """A2AMessage carries ProposedTerms correctly."""
    msg = A2AMessage(
        turn=2,
        sender=Sender.MERCHANT_AGENT,
        receiver=Sender.SHOPPING_AGENT,
        intent=Intent.COUNTER_OFFER,
        product_id="SKU-001",
        proposed_terms=ProposedTerms(unit_price=94.99, quantity=25, delivery_days=5),
        reasoning="Applying 5% bulk discount for 25 units.",
    )
    assert msg.proposed_terms.unit_price == 94.99
    assert msg.reasoning.startswith("Applying")


def test_session_defaults_and_properties():
    """NegotiationSession starts active with 0 turns."""
    session = NegotiationSession(
        mode=Mode.AI,
        persona=Persona.BUDGET_SHOPPER,
        product_sku="SKU-001",
    )
    assert session.status == SessionStatus.ACTIVE
    assert session.turn_count == 0
    assert session.last_merchant_terms is None


def test_session_last_merchant_terms():
    """last_merchant_terms returns the most recent merchant offer."""
    session = NegotiationSession(mode=Mode.AI, product_sku="SKU-001")
    session.turns.append(A2AMessage(
        turn=1, sender=Sender.SHOPPING_AGENT, receiver=Sender.MERCHANT_AGENT,
        intent=Intent.QUERY, session_id=session.session_id,
    ))
    session.turns.append(A2AMessage(
        turn=2, sender=Sender.MERCHANT_AGENT, receiver=Sender.SHOPPING_AGENT,
        intent=Intent.COUNTER_OFFER, session_id=session.session_id,
        proposed_terms=ProposedTerms(unit_price=94.99),
    ))
    assert session.turn_count == 2
    assert session.last_merchant_terms.unit_price == 94.99


def test_start_session_request():
    """StartSessionRequest validates mode and optional persona."""
    req = StartSessionRequest(product_sku="SKU-002", mode=Mode.AI, persona=Persona.BULK_PURCHASER)
    assert req.mode == Mode.AI

    # Human mode — no persona needed
    req2 = StartSessionRequest(product_sku="SKU-002", mode=Mode.HUMAN)
    assert req2.persona is None


def test_turn_request_human_message():
    """TurnRequest carries optional human message text."""
    req = TurnRequest(message_text="Can you do $85 per unit?")
    assert req.message_text == "Can you do $85 per unit?"

    # AI mode turn — no message text
    req2 = TurnRequest()
    assert req2.message_text is None
