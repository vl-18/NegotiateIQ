"""
state_machine.py — Negotiation turn progression for NegotiateIQ.

Manages the lifecycle:
  INITIATED → SHOPPING_OFFER → MERCHANT_COUNTER → [loop] → FINAL_OFFER → ACCEPTED | REJECTED

Turn limit: removed as the primary termination condition.
  - The merchant now issues FINAL_OFFER when its rules engine hits the price floor.
  - After FINAL_OFFER the shopping side must ACCEPT or REJECT (enforced in main.py).
  - SAFETY_MAX_TURNS (50) exists only as a backstop against bugs / infinite loops.
"""

from models import (
    A2AMessage, NegotiationSession, ProposedTerms,
    Intent, Sender, SessionStatus
)


# Absolute backstop — prevents runaway loops if something goes wrong.
# Not exposed to the merchant; not part of normal negotiation flow.
SAFETY_MAX_TURNS = 50


class NegotiationError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class StateMachine:
    """
    Drives turn-by-turn progression of a NegotiationSession.

    Usage:
        sm = StateMachine(session)
        sm.apply(msg)   # validates and appends a new A2AMessage turn
    """

    def __init__(self, session: NegotiationSession):
        self.session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self, msg: A2AMessage) -> None:
        """
        Validate and apply a new turn to the session.
        Updates session.status and session.final_deal on terminal intents.
        Raises NegotiationError if the move is illegal.
        """
        self._guard_session_active()
        self._guard_safety_limit()
        self._validate_sender_order(msg)

        self.session.turns.append(msg)

        if msg.intent == Intent.ACCEPT:
            self._close_accepted(msg)
        elif msg.intent == Intent.REJECT:
            self.session.status = SessionStatus.REJECTED

    def merchant_issued_final_offer(self) -> bool:
        """
        True if the merchant has already sent a FINAL_OFFER in this session.
        Used by main.py to enforce that the next shopping-side move must be ACCEPT or REJECT.
        """
        return any(
            m.sender == Sender.MERCHANT_AGENT and m.intent == Intent.FINAL_OFFER
            for m in self.session.turns
        )

    def expire(self) -> None:
        """
        Safety-limit backstop: marks session EXPIRED and surfaces last merchant offer.
        Called only when SAFETY_MAX_TURNS is reached (should not happen in normal flow).
        """
        self.session.status = SessionStatus.EXPIRED
        self.session.final_deal = self.session.last_merchant_terms

    # ------------------------------------------------------------------
    # Internal guards and helpers
    # ------------------------------------------------------------------

    def _guard_session_active(self) -> None:
        if self.session.status != SessionStatus.ACTIVE:
            raise NegotiationError(
                f"Session is already {self.session.status.value} — no more turns allowed."
            )

    def _guard_safety_limit(self) -> None:
        if self.session.turn_count >= SAFETY_MAX_TURNS:
            self.expire()
            raise NegotiationError(
                f"Safety limit ({SAFETY_MAX_TURNS} turns) reached. Session expired."
            )

    def _validate_sender_order(self, msg: A2AMessage) -> None:
        """Enforce strict alternation: shopping side goes first, then merchant, then alternate."""
        shopping_senders = {Sender.SHOPPING_AGENT, Sender.HUMAN}

        if not self.session.turns:
            if msg.sender not in shopping_senders:
                raise NegotiationError("First turn must come from the shopping side.")
            return

        last_sender = self.session.turns[-1].sender
        last_was_shopping = last_sender in shopping_senders
        this_is_shopping  = msg.sender in shopping_senders

        if last_was_shopping and this_is_shopping:
            raise NegotiationError("Two consecutive shopping-side turns are not allowed.")
        if not last_was_shopping and not this_is_shopping:
            raise NegotiationError("Two consecutive merchant turns are not allowed.")

    def _close_accepted(self, msg: A2AMessage) -> None:
        self.session.status = SessionStatus.ACCEPTED
        self.session.final_deal = msg.proposed_terms or self.session.last_merchant_terms
