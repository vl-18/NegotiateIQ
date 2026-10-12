"""
Smoke tests for gemini.py (google-genai SDK).
Mocks the Gemini client — no real API key required.
Run: python -m pytest orchestrator/tests/test_gemini.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import json
import pytest
from unittest.mock import patch, MagicMock

# Set a dummy key so the module loads without error
os.environ["GEMINI_API_KEY"] = "test-key-placeholder"

from models import Persona
import gemini as gem


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def test_merchant_system_prompt_loads():
    """Merchant system prompt file exists and is non-empty."""
    prompt = gem.merchant_system_prompt()
    assert len(prompt) > 50
    assert "intent" in prompt   # response format is documented in the prompt


def test_all_persona_prompts_load():
    """All three buyer persona prompts exist and contain the JSON format spec."""
    for persona in Persona:
        prompt = gem.shopping_system_prompt(persona)
        assert len(prompt) > 50, f"Prompt for {persona} is too short"
        assert "intent" in prompt, f"Prompt for {persona} missing intent field"


# ---------------------------------------------------------------------------
# JSON response parsing
# ---------------------------------------------------------------------------

def test_parse_clean_json():
    """Plain JSON string is parsed correctly."""
    payload = {"intent": "counter_offer", "display_text": "Here is my offer."}
    result = gem._parse_json_response(json.dumps(payload))
    assert result["intent"] == "counter_offer"


def test_parse_json_with_markdown_fence():
    """Gemini sometimes wraps JSON in ```json ... ``` — we strip it."""
    payload = {"intent": "accept", "display_text": "Deal!"}
    wrapped = f"```json\n{json.dumps(payload)}\n```"
    result = gem._parse_json_response(wrapped)
    assert result["intent"] == "accept"


def test_parse_invalid_json_raises():
    """Non-JSON response raises ValueError with a clear message."""
    with pytest.raises(ValueError, match="non-JSON"):
        gem._parse_json_response("Sorry, I cannot help with that.")


# ---------------------------------------------------------------------------
# Async agent calls (mocked)
# ---------------------------------------------------------------------------

MOCK_MERCHANT_RESPONSE = json.dumps({
    "intent": "counter_offer",
    "proposed_terms": {"unit_price": 92.99, "quantity": 25, "delivery_days": 5, "voucher_offered": None},
    "display_text": "For 25 units I can offer $92.99 each with free standard shipping.",
    "reasoning": "Applying a 7% discount for the 25-unit bulk order."
})

MOCK_SHOPPING_RESPONSE = json.dumps({
    "intent": "counter_offer",
    "proposed_terms": {"unit_price": 85.00, "quantity": 25, "delivery_days": 5, "voucher_requested": None},
    "display_text": "Can you do $85 per unit? That's my budget limit.",
    "reasoning": "Pushing for a lower price to stay within budget."
})


def _make_mock_client(response_text: str):
    """Build a mock genai.Client whose generate_content returns a fixed response."""
    mock_response = MagicMock()
    mock_response.text = response_text

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response

    mock_client = MagicMock()
    mock_client.models = mock_models
    return mock_client


@pytest.mark.asyncio
async def test_call_merchant_agent_returns_parsed_dict():
    """call_merchant_agent calls Gemini and returns parsed JSON."""
    gem._client = _make_mock_client(MOCK_MERCHANT_RESPONSE)
    result = await gem.call_merchant_agent("Turn 1: Buyer asks for 25 units.")
    assert result["intent"] == "counter_offer"
    assert result["proposed_terms"]["unit_price"] == 92.99


@pytest.mark.asyncio
async def test_call_shopping_agent_returns_parsed_dict():
    """call_shopping_agent calls Gemini with the correct persona prompt."""
    gem._client = _make_mock_client(MOCK_SHOPPING_RESPONSE)
    result = await gem.call_shopping_agent(
        "Turn 2: Merchant offers $94.99.",
        Persona.BUDGET_SHOPPER,
    )
    assert result["intent"] == "counter_offer"
    assert result["proposed_terms"]["unit_price"] == 85.00


@pytest.mark.asyncio
async def test_gemini_non_json_propagates_as_value_error():
    """If Gemini returns non-JSON, ValueError bubbles up from the agent call."""
    gem._client = _make_mock_client("I am sorry, I cannot help.")
    with pytest.raises(ValueError, match="non-JSON"):
        await gem.call_merchant_agent("some context")


def test_get_client_raises_if_not_initialised():
    """_get_client raises RuntimeError if init_gemini() was never called."""
    original = gem._client
    gem._client = None
    with pytest.raises(RuntimeError, match="not initialised"):
        gem._get_client()
    gem._client = original   # restore for other tests
