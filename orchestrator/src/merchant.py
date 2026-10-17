"""
merchant.py — Merchant Agent logic for NegotiateIQ.

Two-layer design:
  1. Rules engine  — pure Python, determines what terms are acceptable (fast, deterministic)
  2. Gemini call   — generates natural language display_text and reasoning (generative)

Gemini only controls prose. Numbers always come from the rules engine.

Final offer logic:
  The merchant issues FINAL_OFFER when apply_rules() determines the offered price
  is at or within FINAL_OFFER_EPSILON of the price floor. At that point, Gemini
  is bypassed and a static, firm closing message is used instead.
"""

import json
import logging
from datetime import datetime, timezone

from models import (
    A2AMessage, NegotiationSession, ProposedTerms,
    Intent, Sender
)
from gemini import call_merchant_agent
from state_machine import StateMachine

log = logging.getLogger("negotiateiq.merchant")


# ---------------------------------------------------------------------------
# Product data shape (loaded from Firestore; passed in by main.py)
# ---------------------------------------------------------------------------

class Product:
    """Lightweight product wrapper — mirrors the Firestore product document."""

    def __init__(self, data: dict):
        self.sku:               str        = data["sku"]
        self.name:              str        = data["name"]
        self.list_price:        float      = data["list_price"]
        self.price_floor:       float      = data["price_floor"]
        self.bulk_tiers:        list       = data.get("bulk_tiers", [])
        self.delivery_options:  list       = data.get("delivery_options", ["standard_5d"])
        self.vouchers_eligible: bool       = data.get("vouchers_eligible", False)
        self.image_url:         str | None = data.get("image_url")

    DELIVERY_DAYS = {
        "standard_5d": 5,
        "express_2d":  2,
        "next_day":    1,
    }

    def delivery_days(self, option: str) -> int:
        return self.DELIVERY_DAYS.get(option, 5)


# ---------------------------------------------------------------------------
# Rules engine — pure logic, no LLM
# ---------------------------------------------------------------------------

# If the computed offer is within this amount of the price floor, trigger FINAL_OFFER.
FINAL_OFFER_EPSILON = 0.50


def _bulk_discount_pct(product: Product, quantity: int) -> float:
    """Return the best applicable bulk discount for the given quantity."""
    applicable = [t for t in product.bulk_tiers if quantity >= t["min_qty"]]
    if not applicable:
        return 0.0
    return max(t["discount_pct"] for t in applicable)


def apply_rules(
    product: Product,
    buyer_terms: ProposedTerms | None,
    previous_merchant_price: float | None,
) -> tuple[ProposedTerms, Intent]:
    """
    Pure rules engine: compute the merchant's best constrained offer.

    Strategy (in order):
      1. Start from last merchant offer (or list price on first turn)
      2. Apply best bulk discount the buyer's quantity qualifies for
      3. If buyer pushed lower, split the difference — clamped to price floor
      4. If offer is within FINAL_OFFER_EPSILON of the floor → FINAL_OFFER
      5. Add a loyalty voucher on FINAL_OFFER if the product is eligible
    """
    quantity   = (buyer_terms.quantity or 1) if buyer_terms else 1
    list_price = product.list_price

    # Base: most favourable of (last offer, bulk-discounted list price)
    base_price   = previous_merchant_price if previous_merchant_price is not None else list_price
    bulk_pct     = _bulk_discount_pct(product, quantity)
    bulk_price   = list_price * (1 - bulk_pct / 100)
    offered_price = min(base_price, bulk_price)

    # Move toward buyer if they pushed lower — floor-clamped
    if buyer_terms and buyer_terms.unit_price and buyer_terms.unit_price < offered_price:
        mid_price     = (offered_price + buyer_terms.unit_price) / 2
        offered_price = max(mid_price, product.price_floor)
    else:
        offered_price = max(offered_price, product.price_floor)

    offered_price = round(offered_price, 2)

    # Final offer: we're at (or within epsilon of) the price floor
    is_final = (offered_price - product.price_floor) <= FINAL_OFFER_EPSILON

    # If final, land exactly on the floor — no ambiguity
    if is_final:
        offered_price = product.price_floor

    # Delivery: standard by default; express if buyer requested faster delivery
    delivery_days = 5
    if buyer_terms and buyer_terms.delivery_days and buyer_terms.delivery_days < 5:
        delivery_days = 2

    # Loyalty voucher sweetener on final offer
    voucher = "LOYALTY10" if (is_final and product.vouchers_eligible) else None

    terms = ProposedTerms(
        unit_price=offered_price,
        quantity=quantity,
        delivery_days=delivery_days,
        voucher_requested=voucher,
    )
    intent = Intent.FINAL_OFFER if is_final else Intent.COUNTER_OFFER
    return terms, intent


# ---------------------------------------------------------------------------
# Context builder — formats turn history for Gemini
# ---------------------------------------------------------------------------

def build_negotiation_context(
    session: NegotiationSession,
    product: Product,
    config: dict | None = None,
) -> str:
    """
    Build a plain-text negotiation summary for the Gemini merchant prompt.
    Config (agent name, role) is injected so it can be updated without changing prompts.
    """
    agent_name = (config or {}).get("agent_name", "Alex")
    role       = (config or {}).get("role", "Senior Sales Representative")
    company    = (config or {}).get("company", "MadeinMind Commerce")

    lines = [
        f"You are {agent_name}, {role} at {company}.",
        f"Product: {product.name} (SKU: {product.sku})",
        f"List price: ${product.list_price:.2f} | Price floor: ${product.price_floor:.2f}",
        f"Turn {session.turn_count + 1}",
        "",
        "--- Negotiation history so far ---",
    ]

    for msg in session.turns:
        sender_label = "Buyer" if msg.sender != Sender.MERCHANT_AGENT else "Merchant (you)"
        terms_str = ""
        if msg.proposed_terms:
            t = msg.proposed_terms
            parts = []
            if t.unit_price:        parts.append(f"${t.unit_price:.2f}/unit")
            if t.quantity:          parts.append(f"qty {t.quantity}")
            if t.delivery_days:     parts.append(f"{t.delivery_days}-day delivery")
            if t.voucher_requested: parts.append(f"voucher: {t.voucher_requested}")
            terms_str = " | ".join(parts)

        text = msg.display_text or msg.reasoning or msg.intent.value
        lines.append(f"Turn {msg.turn} [{sender_label}]: {text}")
        if terms_str:
            lines.append(f"  → Terms: {terms_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point — called by main.py for each merchant turn
# ---------------------------------------------------------------------------

async def merchant_turn(
    session: NegotiationSession,
    product: Product,
    state_machine: StateMachine,
    buyer_msg: A2AMessage,
) -> A2AMessage:
    """
    Process one merchant turn:
      1. Apply rules engine to get constrained terms and intent
      2. If FINAL_OFFER → use a static firm message (skip Gemini)
         If COUNTER_OFFER → call Gemini for natural language prose
      4. Return a fully-formed A2AMessage
    """
    # Import here to avoid circular import at module level
    from firebase_db import get_merchant_config

    buyer_terms = buyer_msg.proposed_terms

    # Rules engine: compute constrained terms
    previous_price = (
        session.last_merchant_terms.unit_price if session.last_merchant_terms else None
    )
    terms, intent = apply_rules(
        product=                 product,
        buyer_terms=             buyer_terms,
        previous_merchant_price= previous_price,
    )

    is_final = (intent == Intent.FINAL_OFFER)

    if is_final:
        # Static firm message — no Gemini, no ambiguity
        delivery_str = f"{terms.delivery_days}-day delivery"
        voucher_str  = f" + voucher code {terms.voucher_requested}" if terms.voucher_requested else ""
        display_text = (
            f"Our final price is ${terms.unit_price:.2f}/unit for {terms.quantity} unit(s) "
            f"with {delivery_str}{voucher_str}. "
            f"We cannot go any lower — this is our best and final offer."
        )
        reasoning = "Price floor reached — final offer issued without Gemini."
    else:
        # Gemini generates natural prose; numbers are locked by rules engine
        config  = await get_merchant_config()
        context = build_negotiation_context(session, product, config)
        context += (
            f"\n\nYour next offer (already decided by rules engine): "
            f"${terms.unit_price:.2f}/unit, qty {terms.quantity}, "
            f"{terms.delivery_days}-day delivery."
        )

        display_text = ""
        reasoning    = ""
        for attempt in range(2):   # one retry on transient failure
            try:
                gemini_response = await call_merchant_agent(context, session_id=session.session_id)
                display_text    = gemini_response.get("display_text", "")
                reasoning       = gemini_response.get("reasoning", "")
                break
            except Exception as exc:
                log.warning("merchant Gemini attempt %d failed: %s: %s",
                            attempt + 1, type(exc).__name__, exc)
                is_quota = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
                if attempt == 1 or is_quota:   # no more retries on quota error or final attempt
                    display_text = (
                        f"For {terms.quantity} unit(s) of {product.name}, "
                        f"I can offer ${terms.unit_price:.2f}/unit with {terms.delivery_days}-day delivery."
                    )
                    reasoning = "Gemini unavailable after 2 attempts — fallback display_text used."
                    break

    msg = A2AMessage(
        session_id=    session.session_id,
        turn=          session.turn_count + 1,
        sender=        Sender.MERCHANT_AGENT,
        receiver=      Sender.SHOPPING_AGENT,
        intent=        intent,
        product_id=    product.sku,
        proposed_terms=terms,
        display_text=  display_text,
        reasoning=     reasoning,
    )
    state_machine.apply(msg)
    return msg
