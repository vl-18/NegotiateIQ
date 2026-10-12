"""
shopping.py — Shopping Agent (buyer side) for NegotiateIQ.

Architecture: code owns every hard constraint; LLM supplies negotiation judgement and prose.

  1. required_action() decides accept | reject | counter before the LLM is called.
  2. LLM reply is validated, checked for wrong intent, and retried once with feedback.
  3. clamp_counter() applies hard limits post-LLM (walk-away, delivery, quantity range).
  4. fallback_proposal() produces a deterministic move if the LLM fails entirely.

Modes:
  AI mode    — Gemini drives the buyer through the full safety pipeline.
  Human mode — typed message is regex-parsed into intent + terms, then wrapped in A2A.

Both paths produce identical A2AMessage shapes — the Merchant Agent cannot tell the difference.

Structured JSON logs are emitted per turn for the future metrics dashboard:
  {event, session_id, turn, persona, required, phase, stall, intent,
   source, attempts, latency_ms, llm: {model, latency_ms, prompt_tokens, output_tokens}}
"""

import json
import logging
import random
import re
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from pydantic import BaseModel

from models import (
    A2AMessage, NegotiationSession, ProposedTerms,
    Intent, Sender, Mode, Persona,
)
from gemini import call_gemini_shopping, load_persona_prompt, is_dry_run, SHOPPING_MODEL
import metrics as _metrics
from state_machine import StateMachine
from merchant import Product   # reuse the Product wrapper

log = logging.getLogger("negotiateiq.shopping")

# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------

def _d(s) -> Decimal:
    """Convert anything to a 2-decimal Decimal."""
    return Decimal(str(s)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q2(v: Optional[Decimal]) -> Optional[Decimal]:
    if v is None:
        return None
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Persona system — brackets, specs, and the PERSONAS registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Bracket:
    """Price limits for one quantity range, expressed as fractions of list price."""
    min_qty: int
    max_qty: int
    open_pct:    Decimal   # opening bid
    target_pct:  Decimal   # accept at or below this (win zone)
    ceiling_pct: Decimal   # publicly stated maximum (not the real limit)
    walk_pct:    Decimal   # absolute maximum — code never exceeds this


@dataclass(frozen=True)
class PersonaSpec:
    key:              str
    brackets:         tuple         # tuple of Bracket (at least one)
    start_qty:        int           # opening quantity
    open_delivery:    int           # opening delivery_days to ask for
    max_delivery_days: int          # hard ceiling on delivery
    turn_limit:       int = 8
    stall_limit:      int = 3
    ext_walk_pct:     Optional[Decimal] = None  # extended walk-away fraction (premium only)
    ext_max_delivery: Optional[int] = None      # max delivery for extended walk-away
    lever_qty:        Optional[int] = None      # quantity lever (bulk purchaser: 50)


def _b(mn, mx, op, tgt, ceil_, walk) -> Bracket:
    return Bracket(mn, mx, _d(op), _d(tgt), _d(ceil_), _d(walk))


PERSONAS: dict[str, PersonaSpec] = {
    "budget_shopper": PersonaSpec(
        key="budget_shopper",
        brackets=(_b(1, 4, "0.80", "0.86", "0.88", "0.90"),),
        start_qty=2, open_delivery=5, max_delivery_days=7,
        turn_limit=8, stall_limit=3,
    ),
    "premium_buyer": PersonaSpec(
        key="premium_buyer",
        brackets=(_b(1, 3, "0.92", "0.94", "0.96", "0.97"),),
        start_qty=2, open_delivery=1, max_delivery_days=2,
        ext_walk_pct=_d("1.00"), ext_max_delivery=2,
        turn_limit=5, stall_limit=2,
    ),
    "bulk_purchaser": PersonaSpec(
        key="bulk_purchaser",
        brackets=(
            _b(25, 49, "0.74", "0.82", "0.85", "0.88"),
            _b(50, 60, "0.72", "0.80", "0.83", "0.85"),
        ),
        start_qty=25, open_delivery=5, max_delivery_days=5,
        lever_qty=50, turn_limit=6, stall_limit=2,
    ),
}


def bracket_for(spec: PersonaSpec, qty: Optional[int]) -> Optional[Bracket]:
    """Return the bracket that covers qty, or None if out of all ranges."""
    if qty is None:
        return spec.brackets[0]
    for b in spec.brackets:
        if b.min_qty <= qty <= b.max_qty:
            return b
    return None


# ---------------------------------------------------------------------------
# Lightweight product view (buyer side only needs sku, name, list_price)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _BuyerProduct:
    sku:        str
    name:       str
    list_price: Decimal


# ---------------------------------------------------------------------------
# Internal terms dataclass (within shopping.py only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _BuyerTerms:
    unit_price:        Optional[Decimal]
    quantity:          Optional[int]
    delivery_days:     Optional[int]
    voucher_requested: Optional[str]

    def to_dict(self) -> dict:
        return {
            "unit_price":        float(self.unit_price) if self.unit_price is not None else None,
            "quantity":          self.quantity,
            "delivery_days":     self.delivery_days,
            "voucher_requested": self.voucher_requested,
        }


def _terms_from_msg(raw: dict) -> Optional[_BuyerTerms]:
    """Extract _BuyerTerms from a raw message dict. Returns None if missing."""
    msg = raw.get("message") or {}
    pt = msg.get("proposed_terms") or {}
    if not pt:
        return None
    try:
        return _BuyerTerms(
            unit_price=_d(str(pt["unit_price"])) if pt.get("unit_price") is not None else None,
            quantity=int(pt["quantity"]) if pt.get("quantity") is not None else None,
            delivery_days=int(pt["delivery_days"]) if pt.get("delivery_days") is not None else None,
            voucher_requested=(pt.get("voucher_requested") or "").strip() or None,
        )
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Stall detection
# ---------------------------------------------------------------------------

_STALL_MIN_PCT = Decimal("0.005")   # 0.5% price improvement = "merchant moved"

# Sender value strings (what our Sender enum serialises to)
_MERCHANT_ID = Sender.MERCHANT_AGENT.value   # "merchant-agent"
_BUYER_IDS   = {Sender.SHOPPING_AGENT.value, Sender.HUMAN.value}


def _merchant_moved(older: Optional[_BuyerTerms], newer: Optional[_BuyerTerms]) -> bool:
    """True if merchant lowered their price by at least 0.5% from older→newer turn."""
    if older is None or newer is None or older.unit_price is None or newer.unit_price is None:
        return True   # can't determine — assume they moved
    drop = older.unit_price - newer.unit_price
    return drop >= older.unit_price * _STALL_MIN_PCT


# ---------------------------------------------------------------------------
# Negotiation state — wraps a NegotiationSession for the safety layer
# ---------------------------------------------------------------------------

class NegotiationState:
    """
    Derived view of a NegotiationSession from the buyer's perspective.
    Converts A2AMessage objects to raw dicts compatible with the safety functions.
    Immutable once constructed — build a fresh one per turn.
    """

    def __init__(
        self,
        spec:          PersonaSpec,
        product:       _BuyerProduct,
        exchange_turn: int,           # exchange number buyer is ABOUT TO send (1-indexed)
        history:       list[dict],    # all raw messages (latest merchant msg may be included)
        merchant_msg:  Optional[dict],
    ):
        self.persona  = spec
        self.product  = product
        self.turn     = exchange_turn

        # Dedup: if history ends with merchant_msg, pop it (callers may include it)
        hist = list(history or [])
        if merchant_msg is not None and hist and hist[-1] == merchant_msg:
            hist.pop()
        self._history    = hist
        self._merchant_msg = merchant_msg

    # -- Public read-only properties --

    @property
    def history(self) -> list[dict]:
        return self._history

    @property
    def merchant_msg(self) -> Optional[dict]:
        return self._merchant_msg

    @property
    def turn_limit(self) -> int:
        return self.persona.turn_limit

    @property
    def turns_remaining(self) -> int:
        return self.turn_limit - self.turn

    @property
    def phase(self) -> str:
        pos = self.turn / self.turn_limit
        if pos <= 0.4:
            return "early"
        if pos <= 0.7:
            return "mid"
        return "late"

    @property
    def merchant_terms(self) -> Optional[_BuyerTerms]:
        return _terms_from_msg(self._merchant_msg) if self._merchant_msg else None

    @property
    def merchant_intent(self) -> Optional[str]:
        if self._merchant_msg is None:
            return None
        return (self._merchant_msg.get("message") or {}).get("intent")

    @property
    def stall_count(self) -> int:
        """Consecutive turns where the merchant did not improve their offer."""
        all_merch = []
        if self._merchant_msg:
            all_merch.append(self._merchant_msg)
        all_merch += [m for m in reversed(self._history) if m.get("sender") == _MERCHANT_ID]

        count = 0
        for i in range(len(all_merch) - 1):
            cur = _terms_from_msg(all_merch[i])
            prv = _terms_from_msg(all_merch[i + 1])
            if _merchant_moved(prv, cur):
                break
            count += 1
        return count

    def buyer_offers(self) -> list[_BuyerTerms]:
        """All buyer counter-offers in order (oldest first). Excludes queries."""
        result = []
        for m in self._history:
            if m.get("sender") in _BUYER_IDS:
                terms = _terms_from_msg(m)
                if terms and terms.unit_price is not None:
                    result.append(terms)
        return result

    def queries_used(self) -> int:
        return sum(
            1 for m in self._history
            if m.get("sender") in _BUYER_IDS
            and (m.get("message") or {}).get("intent") == "query"
        )


# ---------------------------------------------------------------------------
# Adapter: build NegotiationState from our A2AMessage-based NegotiationSession
# ---------------------------------------------------------------------------

def _a2a_to_raw(msg: A2AMessage) -> dict:
    """Convert an A2AMessage Pydantic object to the raw dict NegotiationState expects."""
    terms_dict = None
    if msg.proposed_terms:
        pt = msg.proposed_terms
        terms_dict = {
            "unit_price":        pt.unit_price,
            "quantity":          pt.quantity,
            "delivery_days":     pt.delivery_days,
            "voucher_requested": pt.voucher_requested,
        }
    return {
        "sender": msg.sender.value,
        "turn":   msg.turn,
        "message": {
            "intent":         msg.intent.value,
            "proposed_terms": terms_dict,
            "reasoning":      msg.reasoning or msg.display_text or "",
        },
    }


def _build_state(session: NegotiationSession, prod: _BuyerProduct, spec: PersonaSpec) -> NegotiationState:
    all_raw = [_a2a_to_raw(t) for t in session.turns]
    merchant_raw_msgs = [r for r in all_raw if r["sender"] == _MERCHANT_ID]
    latest_merchant   = merchant_raw_msgs[-1] if merchant_raw_msgs else None

    buyer_turns_sent = sum(1 for t in session.turns if t.sender.value in _BUYER_IDS)
    exchange_turn    = buyer_turns_sent + 1   # exchange the buyer is ABOUT TO send

    return NegotiationState(
        spec=spec, product=prod,
        exchange_turn=exchange_turn,
        history=all_raw,
        merchant_msg=latest_merchant,
    )


# ---------------------------------------------------------------------------
# Price policy helpers
# ---------------------------------------------------------------------------

def walk_limit(spec: PersonaSpec, prod: _BuyerProduct, terms: _BuyerTerms) -> Decimal:
    """Maximum price the buyer will pay. Respects extended walk-away rules."""
    brk = bracket_for(spec, terms.quantity)
    if brk is None:
        return _d("0")
    base = prod.list_price * brk.walk_pct
    # Extended walk-away: premium buyer pays up to list_price if delivery fast + voucher included
    if (spec.ext_walk_pct is not None and spec.ext_max_delivery is not None
            and (terms.delivery_days or 99) <= spec.ext_max_delivery
            and terms.voucher_requested):
        return prod.list_price * spec.ext_walk_pct
    return base


def is_acceptable(state: NegotiationState, terms: Optional[_BuyerTerms]) -> bool:
    """True if merchant's terms satisfy all persona constraints."""
    if terms is None:
        return False
    spec, prod = state.persona, state.product
    brk = bracket_for(spec, terms.quantity)
    if brk is None:
        return False
    if (terms.delivery_days or 99) > spec.max_delivery_days:
        return False
    walk = walk_limit(spec, prod, terms)
    return (terms.unit_price or _d("999999")) <= walk


def open_price(spec: PersonaSpec, prod: _BuyerProduct, qty: Optional[int] = None) -> Decimal:
    brk = bracket_for(spec, qty or spec.start_qty)
    if brk is None:
        brk = spec.brackets[0]
    return _q2(prod.list_price * brk.open_pct)


# ---------------------------------------------------------------------------
# Code-enforced safety: required_action, clamp_counter, fallback_proposal
# ---------------------------------------------------------------------------

def required_action(state: NegotiationState) -> str:
    """
    Code decides the required terminal action BEFORE the LLM is called.
    Returns 'accept' | 'reject' | 'counter'.
    'counter' allows the LLM latitude to also accept if it judges terms acceptable.
    """
    intent = state.merchant_intent
    terms  = state.merchant_terms

    if intent == "reject":
        return "reject"              # merchant walked away — buyer confirms

    if intent == "accept":
        return "accept"              # merchant confirmed — buyer echoes

    if state.turns_remaining <= 0:
        return "accept" if is_acceptable(state, terms) else "reject"

    if state.stall_count >= state.persona.stall_limit:
        return "accept" if is_acceptable(state, terms) else "reject"

    return "counter"                 # normal mid-game: LLM handles it


def _pacing_fraction(state: NegotiationState) -> Decimal:
    """Default move size as a fraction of the current gap (persona pacing in prompts overrides)."""
    phase = state.phase
    if phase == "early":
        return Decimal("0.25")
    if phase == "mid":
        return Decimal("0.40")
    return Decimal("0.70")


def clamp_counter(
    state: NegotiationState, proposed: _BuyerTerms
) -> tuple[_BuyerTerms, list[str]]:
    """
    Apply hard limits to a proposed counter-offer. Returns (clamped, repair_notes).
    The LLM's prose may need _swap_price() afterwards if the price was changed.
    """
    spec, prod = state.persona, state.product
    repairs: list[str] = []

    qty = proposed.quantity
    brk = bracket_for(spec, qty)

    # Clamp quantity into a valid bracket
    if brk is None:
        all_min = min(b.min_qty for b in spec.brackets)
        all_max = max(b.max_qty for b in spec.brackets)
        new_qty = max(all_min, min(all_max, qty or spec.start_qty))
        repairs.append(f"qty {qty}→{new_qty} (out of allowed range)")
        qty = new_qty
        brk = bracket_for(spec, qty) or spec.brackets[0]

    # Clamp delivery_days
    days = proposed.delivery_days or spec.max_delivery_days
    if days > spec.max_delivery_days:
        repairs.append(f"delivery {days}→{spec.max_delivery_days} (max {spec.max_delivery_days}d)")
        days = spec.max_delivery_days

    candidate = _BuyerTerms(proposed.unit_price, qty, days, proposed.voucher_requested)
    walk = walk_limit(spec, prod, candidate)
    price = proposed.unit_price or open_price(spec, prod, qty)

    # Never exceed walk-away
    if price > walk:
        repairs.append(f"price {price}→{walk} (walk-away cap)")
        price = walk

    # Never bid above the merchant's current ask (buyer never bids higher than merchant)
    mt = state.merchant_terms
    if mt and mt.unit_price is not None and price > mt.unit_price:
        repairs.append(f"price {price}→{mt.unit_price} (never exceed merchant's ask)")
        price = mt.unit_price

    # Never lower own previous offer at this quantity (don't go backwards)
    for prev in state.buyer_offers():
        if prev.quantity == qty and prev.unit_price is not None and price < prev.unit_price:
            repairs.append(f"price {price}→{prev.unit_price} (held: never move backward)")
            price = prev.unit_price
            break

    return _BuyerTerms(_q2(price), qty, days, proposed.voucher_requested), repairs


def fallback_proposal(state: NegotiationState) -> _BuyerTerms:
    """
    Deterministic fallback used when the LLM fails or in dry-run mode.
    Moves toward the merchant's price by the phase-appropriate pacing fraction.
    """
    spec, prod = state.persona, state.product
    mt = state.merchant_terms

    # Opening: no merchant message yet
    if mt is None:
        price = open_price(spec, prod, spec.start_qty)
        return _BuyerTerms(price, spec.start_qty, spec.open_delivery, None)

    qty = mt.quantity if mt.quantity is not None else spec.start_qty
    brk = bracket_for(spec, qty) or spec.brackets[0]
    merchant_price = mt.unit_price if mt.unit_price is not None else prod.list_price
    walk = prod.list_price * brk.walk_pct

    prev_offers = [o for o in state.buyer_offers() if o.quantity == qty]
    last_price = (prev_offers[-1].unit_price if prev_offers
                  else _q2(prod.list_price * brk.open_pct))

    gap  = merchant_price - last_price
    move = gap * _pacing_fraction(state)
    new_price = _q2(min(last_price + move, walk))
    new_price = max(new_price, last_price)   # never go backward

    return _BuyerTerms(new_price, qty, mt.delivery_days or spec.open_delivery, None)


# ---------------------------------------------------------------------------
# LLM output checking
# ---------------------------------------------------------------------------

def _intent_problem(state: NegotiationState, need: str, reply: "BuyerReply") -> Optional[str]:
    """Return a feedback string if the LLM chose a wrong intent, else None."""
    if need in ("accept", "reject") and reply.intent != need:
        return (f"Required move is '{need}' but you replied '{reply.intent}'. "
                f"Reply again with intent '{need}'.")
    if need == "counter":
        if reply.intent == "reject":
            return "You cannot reject yet. Use counter_offer or accept instead."
        if reply.intent == "accept" and not is_acceptable(state, state.merchant_terms):
            return "Terms are outside your limits; counter instead of accepting."
    return None


# ---------------------------------------------------------------------------
# Text helpers for buyer prose
# ---------------------------------------------------------------------------

_RX_PRICE_STR = re.compile(r"\$\d[\d,]*(?:\.\d{1,2})?")

_TEMPLATES = {
    "counter": "At {price} per unit for {qty} units I believe this represents a fair offer.",
    "accept":  "These terms work for me — let's proceed at {price}.",
    "reject":  "Unfortunately those terms are outside what I can approve for this order.",
    "query":   "Could you share more details about available options for this product?",
}


def _template_reasoning(state: NegotiationState, kind: str, terms: _BuyerTerms) -> str:
    price = f"${float(terms.unit_price or 0):.2f}" if terms.unit_price is not None else "the offered price"
    qty   = terms.quantity or "?"
    return _TEMPLATES.get(kind, _TEMPLATES["counter"]).format(price=price, qty=qty)


def _clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return text.strip()


def _swap_price(text: str, old_price: Decimal, new_price: Decimal) -> str:
    """Replace a specific dollar amount in prose when clamping changed the price."""
    old_str = f"${float(old_price):.2f}"
    new_str = f"${float(new_price):.2f}"
    return text.replace(old_str, new_str)


# ---------------------------------------------------------------------------
# Structured output schema for Gemini JSON mode
# ---------------------------------------------------------------------------

class _BuyerTermsSchema(BaseModel):
    unit_price:        float
    quantity:          int
    delivery_days:     int
    voucher_requested: Optional[str] = None


class BuyerReply(BaseModel):
    intent:         str             # "counter_offer" | "accept" | "reject" | "query"
    product_id:     str = ""        # Gemini sometimes omits this; default prevents parse failure
    proposed_terms: _BuyerTermsSchema
    reasoning:      str
    constraints:    list[str] = []


# ---------------------------------------------------------------------------
# Envelope finalisation: LLM reply (or None) → A2A envelope dict
# ---------------------------------------------------------------------------

_INTENT_MAP = {
    "counter_offer": Intent.COUNTER_OFFER,
    "accept":        Intent.ACCEPT,
    "reject":        Intent.REJECT,
    "query":         Intent.QUERY,
    "final_offer":   Intent.FINAL_OFFER,
}


def _finalize(
    state: NegotiationState,
    session: NegotiationSession,
    need: str,
    reply: Optional[BuyerReply],
    initial_source: str,
) -> tuple[dict, str, list[str]]:
    """
    Produce a send-ready A2A envelope dict from a validated LLM reply (or None).
    Returns (envelope, source, notes).
    source values: llm | llm_repaired | override | fallback | dry_run
    """
    prod   = state.product
    mt     = state.merchant_terms
    notes: list[str] = []
    source = initial_source

    # ── Forced terminal moves (accept / reject required by code) ──────────
    if need in ("accept", "reject"):
        terms  = mt or fallback_proposal(state)
        intent = need
        if reply is not None and reply.intent == need:
            reasoning = _clean_text(reply.reasoning)
        else:
            reasoning = _template_reasoning(state, need, terms)
            notes.append(f"forced {need} (code-required)")
            source = "override"

    # ── LLM voluntarily accepts and terms are within limits ───────────────
    elif reply is not None and reply.intent == "accept" and is_acceptable(state, mt):
        intent    = "accept"
        terms     = mt or fallback_proposal(state)
        reasoning = _clean_text(reply.reasoning)
        notes.append("early_accept")

    # ── Counter / query ───────────────────────────────────────────────────
    else:
        if reply is not None:
            intent = reply.intent
            # Convert excess queries to counter_offer
            if intent == "query" and state.queries_used() >= 1:
                intent = "counter_offer"
                notes.append("query→counter_offer (query already used this session)")
            pt = reply.proposed_terms
            proposed  = _BuyerTerms(
                unit_price=_d(str(pt.unit_price)),
                quantity=pt.quantity,
                delivery_days=pt.delivery_days,
                voucher_requested=(pt.voucher_requested or "").strip() or None,
            )
            reasoning = _clean_text(reply.reasoning)
        else:
            intent    = "counter_offer"
            proposed  = fallback_proposal(state)
            reasoning = None

        terms, repairs = clamp_counter(state, proposed)
        if repairs:
            notes += [f"repaired: {r}" for r in repairs]
            if source == "llm":
                source = "llm_repaired"

        # Adjust prose if the price was changed by clamping
        if reasoning and reply is not None:
            old_p = _d(str(reply.proposed_terms.unit_price))
            if terms.unit_price is not None and old_p != terms.unit_price:
                reasoning = _swap_price(reasoning, old_p, terms.unit_price)
            # Clear prose if quantity or delivery changed significantly (would be misleading)
            if (terms.quantity != proposed.quantity or
                    terms.delivery_days != proposed.delivery_days):
                reasoning = None

    if not reasoning:
        kind = "counter" if intent in ("counter_offer", "query") else intent
        reasoning = _template_reasoning(state, kind, terms)

    envelope = {
        "a2a_version": "1.0",
        "session_id":  session.session_id,
        "turn":        state.turn,
        "sender":      Sender.SHOPPING_AGENT.value,
        "receiver":    Sender.MERCHANT_AGENT.value,
        "message": {
            "intent":         intent,
            "product_id":     prod.sku,
            "proposed_terms": terms.to_dict(),
            "reasoning":      reasoning,
        },
    }
    return envelope, source, notes


def _envelope_to_a2a(envelope: dict, session: NegotiationSession, product: Product) -> A2AMessage:
    """Convert the finalized envelope dict to our A2AMessage Pydantic model."""
    msg   = envelope["message"]
    intent = _INTENT_MAP.get(msg["intent"], Intent.QUERY)
    sender_str = envelope["sender"]
    sender = Sender.SHOPPING_AGENT if sender_str == Sender.SHOPPING_AGENT.value else Sender.HUMAN

    raw_terms = msg.get("proposed_terms") or {}
    proposed_terms = ProposedTerms(
        unit_price=        raw_terms.get("unit_price"),
        quantity=          raw_terms.get("quantity"),
        delivery_days=     raw_terms.get("delivery_days"),
        voucher_requested= raw_terms.get("voucher_requested"),
    ) if raw_terms else None

    reasoning = msg.get("reasoning", "")
    return A2AMessage(
        session_id=     session.session_id,
        turn=           session.turn_count + 1,
        sender=         sender,
        receiver=       Sender.MERCHANT_AGENT,
        intent=         intent,
        product_id=     product.sku,
        proposed_terms= proposed_terms,
        display_text=   reasoning,
        reasoning=      reasoning,
    )


# ---------------------------------------------------------------------------
# Startup integrity check — warn if code limits differ from prompt text
# ---------------------------------------------------------------------------

def verify_prompt_matches_limits() -> None:
    """
    Compare code PERSONAS against their prompt files.
    Logs a warning for any mismatch — does not raise (app still runs).
    """
    checks = {
        "budget_shopper": {"open": 80, "walk": 90, "turns": 8,  "stalls": 3},
        "premium_buyer":  {"open": 92, "walk": 97, "turns": 5,  "stalls": 2},
        "bulk_purchaser": {"walk": 88, "turns": 6, "stalls": 2},
    }
    rx_map = [
        ("open",   re.compile(r"Opening price[^:]*:\s*(\d+)%")),
        ("walk",   re.compile(r"WALK-AWAY price[^:]*:\s*(\d+)%")),
        ("turns",  re.compile(r"TURN LIMIT:\s*(\d+)")),
        ("stalls", re.compile(r"STALL LIMIT:\s*(\d+)")),
    ]
    for key, expected in checks.items():
        try:
            text = load_persona_prompt(key)
        except FileNotFoundError:
            log.warning(json.dumps({"event": "prompt_verify", "persona": key, "error": "file_not_found"}))
            continue
        mismatches = []
        for field, rx in rx_map:
            if field not in expected:
                continue
            m = rx.search(text)
            if m and int(m.group(1)) != expected[field]:
                mismatches.append(f"{field}: prompt={m.group(1)} code={expected[field]}")
        if mismatches:
            log.warning(json.dumps({"event": "prompt_verify", "persona": key, "mismatches": mismatches}))
        else:
            log.debug(json.dumps({"event": "prompt_verify", "persona": key, "status": "ok"}))


# ---------------------------------------------------------------------------
# Context builder — structured JSON for the LLM (matches prompt section 4)
# ---------------------------------------------------------------------------

def _compact_msg(raw: dict) -> dict:
    """Produce a compact representation of a raw message for the LLM context."""
    msg = raw.get("message") or {}
    return {
        "sender":         raw.get("sender"),
        "turn":           raw.get("turn"),
        "intent":         msg.get("intent"),
        "proposed_terms": msg.get("proposed_terms"),
        "reasoning":      (msg.get("reasoning") or "")[:400],
    }


def _build_context(state: NegotiationState) -> dict:
    """Build the structured JSON context sent to the LLM each turn."""
    return {
        "product": {
            "sku":        state.product.sku,
            "name":       state.product.name,
            "list_price": float(state.product.list_price),
        },
        "current_turn":           state.turn,
        "turn_limit":             state.turn_limit,
        "turns_remaining":        state.turns_remaining,
        "phase":                  state.phase,
        "merchant_stall_count":   state.stall_count,
        "history":                [_compact_msg(m) for m in state.history],
        "latest_merchant_message": _compact_msg(state.merchant_msg) if state.merchant_msg else None,
    }


# ---------------------------------------------------------------------------
# AI mode — Gemini drives the buyer through the full safety pipeline
# ---------------------------------------------------------------------------

async def shopping_turn_ai(
    session:       NegotiationSession,
    product:       Product,
    state_machine: StateMachine,
) -> A2AMessage:
    """
    AI mode: call Gemini with persona prompt + full code-enforced safety layer.
    Falls back to a deterministic offer if the LLM fails (or in dry-run mode).
    """
    persona_key = session.persona.value
    spec = PERSONAS.get(persona_key, PERSONAS["budget_shopper"])

    buyer_prod = _BuyerProduct(
        sku=product.sku, name=product.name,
        list_price=_d(str(product.list_price)),
    )
    state = _build_state(session, buyer_prod, spec)
    need  = required_action(state)
    t0    = time.perf_counter()

    notes: list[str] = []
    reply: Optional[BuyerReply] = None
    llm_meta: Optional[dict] = None
    attempts = 0
    feedback: Optional[str] = None

    if is_dry_run():
        initial_source = "dry_run"
        # Record a simulated metric so the Metrics dashboard is populated in demo mode
        _metrics.record_call(
            agent="shopping",
            model=f"{SHOPPING_MODEL} [simulated]",
            latency_ms=random.randint(500, 2200),
            prompt_tokens=random.randint(300, 800),
            output_tokens=random.randint(50, 180),
            session_id=session.session_id,
        )
    else:
        initial_source = "llm"
        system       = load_persona_prompt(persona_key)
        context_base = _build_context(state)

        for _attempt in range(2):   # first try + one retry with corrective feedback
            elapsed = time.perf_counter() - t0
            if elapsed > 9.0:
                notes.append("time budget exhausted before retry")
                break

            attempts += 1
            ctx = dict(context_base)
            if feedback:
                ctx["_correction"] = feedback   # injected guidance for the retry
            user_content = json.dumps(ctx)

            try:
                raw, llm_meta = await call_gemini_shopping(
                    system, user_content, BuyerReply,
                    timeout_s=max(3.0, 10.0 - elapsed),
                    session_id=session.session_id,
                )
                cand = BuyerReply.model_validate_json(raw)
            except Exception as exc:
                is_quota = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
                feedback = f"parse error: {type(exc).__name__}: {str(exc)[:80]}"
                notes.append(f"attempt {attempts}: {feedback}")
                if is_quota:
                    break   # quota errors won't resolve on retry
                continue

            problem = _intent_problem(state, need, cand)
            if problem:
                feedback = problem
                notes.append(f"attempt {attempts}: wrong intent – {problem[:80]}")
                continue

            reply = cand
            break   # good response

        if reply is None and initial_source == "llm":
            initial_source = "fallback"
            notes.append("all LLM attempts failed — using deterministic fallback")

    envelope, source, extra = _finalize(state, session, need, reply, initial_source)
    notes += extra
    latency_ms = int((time.perf_counter() - t0) * 1000)

    log.info(json.dumps({
        "event":      "shopping_ai_turn",
        "session_id": session.session_id,
        "turn":       state.turn,
        "persona":    persona_key,
        "required":   need,
        "phase":      state.phase,
        "stall":      state.stall_count,
        "intent":     envelope["message"]["intent"],
        "source":     source,
        "attempts":   attempts,
        "latency_ms": latency_ms,
        "llm":        llm_meta,
        "notes":      notes,
    }))

    msg = _envelope_to_a2a(envelope, session, product)
    state_machine.apply(msg)
    return msg


# ---------------------------------------------------------------------------
# Human mode — typed message parsed into A2A envelope
# ---------------------------------------------------------------------------

_RX_ACCEPT  = re.compile(r"\b(i accept|we accept|accepted|i'?ll take it|deal|agreed?|we have a deal|sounds good|let'?s do it)\b", re.I)
_RX_REJECT  = re.compile(r"\b(i reject|no deal|walk(?:ing)? away|not interested|forget it|no thanks|can'?t do it|too expensive)\b", re.I)
_RX_PRICE   = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)")
_RX_QTY     = re.compile(r"\b(\d{1,4})\s*(?:units?|pcs|pieces|items?|qty)\b", re.I)
_RX_DAYS    = re.compile(r"\b(\d{1,2})\s*-?\s*days?\b", re.I)
_RX_VOUCHER = re.compile(r"\b(voucher|loyalty|reward points?|perk|early access|discount code)\b", re.I)


def shopping_turn_human(
    session:       NegotiationSession,
    product:       Product,
    state_machine: StateMachine,
    message_text:  str,
) -> A2AMessage:
    """
    Human mode: extract intent + terms from typed text via regex, then wrap in A2A.
    Intent detection is far more accurate than the old "always QUERY" approach.
    """
    text  = message_text.strip()
    found: dict = {}

    # Extract structured fields from free text
    if (m := _RX_PRICE.search(text)):
        found["unit_price"] = float(m.group(1))
    if (m := _RX_QTY.search(text)):
        found["quantity"] = int(m.group(1))
    if re.search(r"next[- ]day|overnight", text, re.I):
        found["delivery_days"] = 1
    elif re.search(r"\bexpress\b", text, re.I):
        found["delivery_days"] = 2
    elif (m := _RX_DAYS.search(text)):
        found["delivery_days"] = int(m.group(1))
    if _RX_VOUCHER.search(text):
        found["voucher_requested"] = "LOYALTY10"

    # Determine intent
    merchant_turns = [t for t in session.turns if t.sender == Sender.MERCHANT_AGENT]
    has_merchant   = bool(merchant_turns)

    if _RX_ACCEPT.search(text) and has_merchant:
        intent = Intent.ACCEPT
    elif _RX_REJECT.search(text) and has_merchant:
        intent = Intent.REJECT
    elif found:
        intent = Intent.COUNTER_OFFER
    else:
        intent = Intent.QUERY

    # Accept/reject: echo merchant's last terms exactly
    if intent in (Intent.ACCEPT, Intent.REJECT) and has_merchant:
        last_m = merchant_turns[-1]
        proposed_terms = ProposedTerms(
            unit_price=        last_m.proposed_terms.unit_price        if last_m.proposed_terms else None,
            quantity=          last_m.proposed_terms.quantity          if last_m.proposed_terms else None,
            delivery_days=     last_m.proposed_terms.delivery_days     if last_m.proposed_terms else None,
            voucher_requested= last_m.proposed_terms.voucher_requested if last_m.proposed_terms else None,
        ) if last_m.proposed_terms else None
    else:
        proposed_terms = ProposedTerms(
            unit_price=        found.get("unit_price"),
            quantity=          found.get("quantity"),
            delivery_days=     found.get("delivery_days"),
            voucher_requested= found.get("voucher_requested"),
        ) if found else None

    log.info(json.dumps({
        "event":           "shopping_human_turn",
        "session_id":      session.session_id,
        "turn":            session.turn_count + 1,
        "intent":          intent.value,
        "parse_source":    "regex",
        "extracted_fields": list(found.keys()),
    }))

    msg = A2AMessage(
        session_id=     session.session_id,
        turn=           session.turn_count + 1,
        sender=         Sender.HUMAN,
        receiver=       Sender.MERCHANT_AGENT,
        intent=         intent,
        product_id=     product.sku,
        proposed_terms= proposed_terms,
        display_text=   text,
        reasoning=      text,
    )
    state_machine.apply(msg)
    return msg


# ---------------------------------------------------------------------------
# Router — main.py entry point for every buyer-side turn
# ---------------------------------------------------------------------------

async def shopping_turn(
    session:       NegotiationSession,
    product:       Product,
    state_machine: StateMachine,
    message_text:  str | None = None,
) -> A2AMessage:
    """
    Dispatch to AI or human path based on session.mode.

    AI mode:    message_text is ignored; Gemini (with safety layer) generates the reply.
    Human mode: message_text is required (the typed buyer message).
    """
    if session.mode == Mode.AI:
        return await shopping_turn_ai(session, product, state_machine)

    if not message_text or not message_text.strip():
        raise ValueError("message_text is required in human mode.")
    return shopping_turn_human(session, product, state_machine, message_text.strip())
