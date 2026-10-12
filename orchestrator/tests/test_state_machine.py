"""
Smoke + unit tests for state_machine.py.
Run: python -m pytest orchestrator/tests/test_state_machine.py -v
No external services required.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from models import (
    A2AMessage, NegotiationSession, ProposedTerms,
    Intent, Sender, Mode, Persona, SessionStatus
)
from state_machine import StateMachine, NegotiationError, DEFAULT_MAX_TURNS


# ---------------------------------------------------------------------------
# Helpers — build minimal valid messages quickly
# ---------------------------------------------------------------------------

def shopping_msg(turn: int, session_id: str, intent=Intent.QUERY, terms=None) -> A2AMessage:
    return A2AMessage(
        session_id=session_id, turn=turn,
        sender=Sender.SHOPPING_AGENT, receiver=Sender.MERCHANT_AGENT,
        intent=intent, proposed_terms=terms,
    )

def human_msg(turn: int, session_id: str, intent=Intent.QUERY) -> A2AMessage:
    return A2AMessage(
        session_id=session_id, turn=turn,
        sender=Sender.HUMAN, receiver=Sender.MERCHANT_AGENT,
        intent=intent,
    )

def merchant_msg(turn: int, session_id: str, intent=Intent.COUNTER_OFFER, terms=None) -> A2AMessage:
    return A2AMessage(
        session_id=session_id, turn=turn,
        sender=Sender.MERCHANT_AGENT, receiver=Sender.SHOPPING_AGENT,
        intent=intent, proposed_terms=terms,
    )

def new_session() -> NegotiationSession:
    return NegotiationSession(mode=Mode.AI, persona=Persona.BUDGET_SHOPPER, product_sku="SKU-001")


# ---------------------------------------------------------------------------
# Happy-path: normal alternating flow
# ---------------------------------------------------------------------------

def test_normal_two_turn_flow():
    """Shopping → Merchant alternation works and turn count grows."""
    session = new_session()
    sm = StateMachine(session)

    sm.apply(shopping_msg(1, session.session_id))
    assert session.turn_count == 1
    assert session.status == SessionStatus.ACTIVE

    sm.apply(merchant_msg(2, session.session_id, terms=ProposedTerms(unit_price=94.99)))
    assert session.turn_count == 2
    assert session.status == SessionStatus.ACTIVE


def test_human_counts_as_shopping_side():
    """Human sender is treated as shopping side for alternation."""
    session = new_session()
    sm = StateMachine(session)

    sm.apply(human_msg(1, session.session_id))
    sm.apply(merchant_msg(2, session.session_id))
    assert session.turn_count == 2


# ---------------------------------------------------------------------------
# Terminal intents: ACCEPT
# ---------------------------------------------------------------------------

def test_accept_closes_session_with_last_merchant_terms():
    """ACCEPT with no terms falls back to last merchant offer."""
    session = new_session()
    sm = StateMachine(session)

    sm.apply(shopping_msg(1, session.session_id))
    sm.apply(merchant_msg(2, session.session_id, terms=ProposedTerms(unit_price=89.99, quantity=25)))
    sm.apply(shopping_msg(3, session.session_id, intent=Intent.ACCEPT))

    assert session.status == SessionStatus.ACCEPTED
    assert session.final_deal.unit_price == 89.99   # fell back to last merchant terms


def test_accept_with_explicit_terms():
    """ACCEPT with its own terms captures those terms as the final deal."""
    session = new_session()
    sm = StateMachine(session)
    agreed_terms = ProposedTerms(unit_price=88.00, quantity=30)

    sm.apply(shopping_msg(1, session.session_id))
    sm.apply(merchant_msg(2, session.session_id, terms=ProposedTerms(unit_price=90.00)))
    sm.apply(shopping_msg(3, session.session_id, intent=Intent.ACCEPT, terms=agreed_terms))

    assert session.final_deal.unit_price == 88.00


def test_no_turns_after_accept():
    """Any turn after ACCEPT raises NegotiationError."""
    session = new_session()
    sm = StateMachine(session)

    sm.apply(shopping_msg(1, session.session_id))
    sm.apply(merchant_msg(2, session.session_id))
    sm.apply(shopping_msg(3, session.session_id, intent=Intent.ACCEPT))

    with pytest.raises(NegotiationError, match="already accepted"):
        sm.apply(merchant_msg(4, session.session_id))


# ---------------------------------------------------------------------------
# Terminal intents: REJECT
# ---------------------------------------------------------------------------

def test_reject_closes_session():
    session = new_session()
    sm = StateMachine(session)

    sm.apply(shopping_msg(1, session.session_id))
    sm.apply(merchant_msg(2, session.session_id, intent=Intent.REJECT))

    assert session.status == SessionStatus.REJECTED


# ---------------------------------------------------------------------------
# Alternation enforcement
# ---------------------------------------------------------------------------

def test_first_turn_must_be_shopping_side():
    """Merchant cannot go first."""
    session = new_session()
    sm = StateMachine(session)

    with pytest.raises(NegotiationError, match="shopping side"):
        sm.apply(merchant_msg(1, session.session_id))


def test_two_shopping_turns_in_a_row_blocked():
    session = new_session()
    sm = StateMachine(session)

    sm.apply(shopping_msg(1, session.session_id))
    with pytest.raises(NegotiationError, match="consecutive shopping"):
        sm.apply(shopping_msg(2, session.session_id))


def test_two_merchant_turns_in_a_row_blocked():
    session = new_session()
    sm = StateMachine(session)

    sm.apply(shopping_msg(1, session.session_id))
    sm.apply(merchant_msg(2, session.session_id))
    with pytest.raises(NegotiationError, match="consecutive merchant"):
        sm.apply(merchant_msg(3, session.session_id))


# ---------------------------------------------------------------------------
# Final offer flag and expiry
# ---------------------------------------------------------------------------

def test_should_use_final_offer_at_penultimate_turn():
    """should_use_final_offer is True when one merchant turn remains."""
    session = new_session()
    sm = StateMachine(session, max_turns=4)

    # Fill to turn 3 (3 turns done; next merchant turn = turn 4 = max)
    sm.apply(shopping_msg(1, session.session_id))
    sm.apply(merchant_msg(2, session.session_id))
    sm.apply(shopping_msg(3, session.session_id))

    assert sm.should_use_final_offer() is True


def test_should_not_use_final_offer_early():
    """should_use_final_offer is False with plenty of turns remaining."""
    session = new_session()
    sm = StateMachine(session, max_turns=8)

    sm.apply(shopping_msg(1, session.session_id))
    assert sm.should_use_final_offer() is False


def test_session_expires_at_max_turns():
    """Session expires when max turns hit with no resolution."""
    session = new_session()
    sm = StateMachine(session, max_turns=4)

    sm.apply(shopping_msg(1, session.session_id))
    sm.apply(merchant_msg(2, session.session_id, terms=ProposedTerms(unit_price=90.0)))
    sm.apply(shopping_msg(3, session.session_id))
    sm.apply(merchant_msg(4, session.session_id, terms=ProposedTerms(unit_price=88.0)))

    # Next turn should trigger expiry
    with pytest.raises(NegotiationError):
        sm.apply(shopping_msg(5, session.session_id))

    assert session.status == SessionStatus.EXPIRED
    # Last merchant offer surfaced as the final deal
    assert session.final_deal.unit_price == 88.0
