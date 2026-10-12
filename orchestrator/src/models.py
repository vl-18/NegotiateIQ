"""
models.py — Pydantic data models for NegotiateIQ.
All A2A message shapes, session state, and API request/response types live here.
"""

from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid


# ---------------------------------------------------------------------------
# Enums — constrained string fields
# ---------------------------------------------------------------------------

class Intent(str, Enum):
    COUNTER_OFFER = "counter_offer"
    ACCEPT        = "accept"
    REJECT        = "reject"
    QUERY         = "query"
    FINAL_OFFER   = "final_offer"


class SessionStatus(str, Enum):
    ACTIVE   = "active"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED  = "expired"   # hit max turns with no deal


class Mode(str, Enum):
    AI    = "ai"
    HUMAN = "human"


class Persona(str, Enum):
    BUDGET_SHOPPER   = "budget_shopper"
    PREMIUM_BUYER    = "premium_buyer"
    BULK_PURCHASER   = "bulk_purchaser"


class Sender(str, Enum):
    SHOPPING_AGENT  = "shopping-agent"
    MERCHANT_AGENT  = "merchant-agent"
    HUMAN           = "human"


# ---------------------------------------------------------------------------
# Core A2A message structure
# ---------------------------------------------------------------------------

class ProposedTerms(BaseModel):
    """The commercial terms being offered in a single negotiation turn."""
    unit_price:        Optional[float] = None
    quantity:          Optional[int]   = None
    delivery_days:     Optional[int]   = None
    voucher_requested: Optional[str]   = None  # e.g. "LOYALTY10"


class A2AMessage(BaseModel):
    """
    Full A2A protocol envelope for one negotiation turn.
    Both agents produce and consume this shape.
    """
    a2a_version: str     = "1.0"
    session_id:  str     = Field(default_factory=lambda: str(uuid.uuid4()))
    turn:        int
    sender:      Sender
    receiver:    Sender
    timestamp:   datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Negotiation payload
    intent:         Intent
    product_id:     Optional[str]          = None
    proposed_terms: Optional[ProposedTerms] = None
    reasoning:      Optional[str]          = None   # AI agents include this
    constraints:    list[str]              = []      # e.g. ["max_budget: 2500"]
    display_text:   Optional[str]          = None   # Human-readable message for UI


# ---------------------------------------------------------------------------
# Session state — persisted in Firestore and mirrored to Firebase Realtime DB
# ---------------------------------------------------------------------------

class NegotiationSession(BaseModel):
    """Full state of one negotiation session."""
    session_id:  str            = Field(default_factory=lambda: str(uuid.uuid4()))
    mode:        Mode
    persona:     Optional[Persona] = None   # null in human mode
    product_sku: str
    turns:       list[A2AMessage]  = []
    status:      SessionStatus     = SessionStatus.ACTIVE
    final_deal:  Optional[ProposedTerms] = None
    created_at:  datetime          = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def last_merchant_terms(self) -> Optional[ProposedTerms]:
        """Most recent terms offered by the merchant — for UI summary."""
        for msg in reversed(self.turns):
            if msg.sender == Sender.MERCHANT_AGENT and msg.proposed_terms:
                return msg.proposed_terms
        return None


# ---------------------------------------------------------------------------
# API request shapes
# ---------------------------------------------------------------------------

class StartSessionRequest(BaseModel):
    """Body for POST /session/start"""
    product_sku: str
    mode:        Mode
    persona:     Optional[Persona] = None  # required when mode=ai


class TurnRequest(BaseModel):
    """
    Body for POST /session/{id}/turn.
    - In AI mode: message_text is ignored; the Shopping Agent generates its own.
    - In Human mode: message_text is the typed buyer message.
    """
    message_text: Optional[str] = None   # human mode only


class ProductCreate(BaseModel):
    """Body for POST /products — sku and name are required."""
    sku:               str
    name:              str
    list_price:        float
    price_floor:       float
    bulk_tiers:        list         = []
    delivery_options:  list         = ["standard_5d"]
    vouchers_eligible: bool         = False
    image_url:         Optional[str] = None


class ProductUpdate(BaseModel):
    """Body for PUT /products/{sku} — all fields optional (patch semantics)."""
    list_price:        Optional[float] = None
    price_floor:       Optional[float] = None
    bulk_tiers:        Optional[list]  = None
    delivery_options:  Optional[list]  = None
    vouchers_eligible: Optional[bool]  = None
    image_url:         Optional[str]   = None


class MerchantConfigUpdate(BaseModel):
    """Body for PUT /config — all fields optional (patch semantics)."""
    agent_name: Optional[str] = None
    role:       Optional[str] = None
    company:    Optional[str] = None


