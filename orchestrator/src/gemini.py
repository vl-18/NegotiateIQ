"""
gemini.py — Thin async wrapper around the Gemini API (google-genai SDK).

All agent calls go through here. To swap AI Studio → Vertex AI for GCP deploy,
only this file needs to change — merchant.py and shopping.py stay the same.

DRY_RUN=true skips real Gemini calls and returns canned responses for local demos.

Every real Gemini call emits a structured JSON log entry for observability:
  {"event":"gemini_call","agent":"...","model":"...","latency_ms":...,"prompt_tokens":...,"output_tokens":...}
This feeds the future LLM-latency/token-usage metrics dashboard.
"""

import os
import json
import time
import random
import logging
import asyncio
from pathlib import Path
from functools import lru_cache
from typing import Any, Optional

from google import genai
from google.genai import types

from models import Persona
import metrics as _metrics

log = logging.getLogger("negotiateiq.gemini")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MERCHANT_MODEL = os.getenv("MERCHANT_MODEL", "gemini-3.5-flash")
SHOPPING_MODEL = os.getenv("SHOPPING_MODEL", "gemini-3.5-flash")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

PERSONA_PROMPT_FILES = {
    Persona.BUDGET_SHOPPER: "persona_budget_shopper.txt",
    Persona.PREMIUM_BUYER:  "persona_premium_buyer.txt",
    Persona.BULK_PURCHASER: "persona_bulk_purchaser.txt",
}

_client: genai.Client | None = None
_dry_run: bool = False


# ---------------------------------------------------------------------------
# Initialisation — called once at startup
# ---------------------------------------------------------------------------

def init_gemini() -> None:
    """
    Configure the Gemini SDK. Two paths:
      - GEMINI_API_KEY present → AI Studio (personal key, local dev)
      - GEMINI_API_KEY absent  → Vertex AI (uses ADC or GOOGLE_APPLICATION_CREDENTIALS)
    DRY_RUN=true skips both and never touches the network.
    """
    global _client, _dry_run
    if os.getenv("DRY_RUN", "").lower() == "true":
        _dry_run = True
        return

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        # AI Studio path — simple API key, no GCP project needed
        _client = genai.Client(api_key=api_key)
    else:
        # Vertex AI path — uses Application Default Credentials
        # Run: gcloud auth application-default login
        # Or set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
        project  = os.getenv("GCP_PROJECT_ID", "negotiateiq-510510")
        location = os.getenv("GCP_REGION", "us-central1")
        _client  = genai.Client(vertexai=True, project=project, location=location)
        log.info(json.dumps({"event": "gemini_init", "backend": "vertex_ai",
                             "project": project, "location": location}))


def is_dry_run() -> bool:
    return _dry_run


def _get_client() -> genai.Client:
    if _client is None:
        raise RuntimeError("Gemini client not initialised. Call init_gemini() first.")
    return _client


# ---------------------------------------------------------------------------
# Prompt loading — cached so files are read once per process
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def merchant_system_prompt() -> str:
    return _load_prompt("merchant_system.txt")


def shopping_system_prompt(persona: Persona) -> str:
    return _load_prompt(PERSONA_PROMPT_FILES[persona])


def load_persona_prompt(persona_key: str) -> str:
    """Load a shopping-agent persona prompt by key string (e.g. 'budget_shopper')."""
    return _load_prompt(f"persona_{persona_key}.txt")


# ---------------------------------------------------------------------------
# Core Gemini call — captures latency + token metadata for observability
# ---------------------------------------------------------------------------

async def _call_gemini_raw(
    model_name: str,
    system_prompt: str,
    user_content: str,
    *,
    response_schema: Optional[Any] = None,
    max_output_tokens: int = 2048,
    temperature: float = 0.7,
    timeout_s: Optional[float] = None,
) -> tuple[str, dict]:
    """
    Call Gemini and return (raw_text, metadata).
    metadata = {model, latency_ms, prompt_tokens, output_tokens, thoughts_tokens}
    Runs the blocking SDK call in a thread so FastAPI's event loop isn't blocked.
    """
    client = _get_client()

    config_kwargs: dict = {
        "system_instruction": system_prompt,
        "max_output_tokens": max_output_tokens,
        "temperature": temperature,
    }
    if response_schema is not None:
        # Structured output: constrain model to produce valid JSON matching the schema
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema

    def _blocking_call() -> tuple[str, dict]:
        t0 = time.perf_counter()
        response = client.models.generate_content(
            model=model_name,
            contents=user_content,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        usage = getattr(response, "usage_metadata", None)
        meta = {
            "model": model_name,
            "latency_ms": latency_ms,
            "prompt_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
            "thoughts_tokens": getattr(usage, "thoughts_token_count", None),
        }
        return response.text or "", meta

    loop = asyncio.get_event_loop()
    if timeout_s is not None:
        text, meta = await asyncio.wait_for(
            loop.run_in_executor(None, _blocking_call), timeout=timeout_s
        )
    else:
        text, meta = await loop.run_in_executor(None, _blocking_call)
    return text, meta


# ---------------------------------------------------------------------------
# Agent-level helpers called by merchant.py and shopping.py
# ---------------------------------------------------------------------------

async def call_merchant_agent(negotiation_context: str, session_id: Optional[str] = None) -> dict:
    """
    Call the Merchant Agent with the current negotiation context.
    Returns parsed JSON dict. Logs a gemini_call entry for observability.
    """
    if _dry_run:
        # Record a simulated metric so the Metrics dashboard is populated in demo mode
        _metrics.record_call(
            agent="merchant",
            model=f"{MERCHANT_MODEL} [simulated]",
            latency_ms=random.randint(600, 2500),
            prompt_tokens=random.randint(250, 650),
            output_tokens=random.randint(60, 200),
            session_id=session_id,
        )
        return {
            "intent":       "counter_offer",
            "display_text": "Thanks for your interest! I've reviewed your request and put together a competitive offer that works for both of us.",
            "reasoning":    "Dry-run placeholder — rules engine controls the actual numbers.",
        }
    t0 = time.perf_counter()
    try:
        text, meta = await _call_gemini_raw(
            model_name=MERCHANT_MODEL,
            system_prompt=merchant_system_prompt(),
            user_content=negotiation_context,
        )
        log.info(json.dumps({"event": "gemini_call", "agent": "merchant", **meta}))
        _metrics.record_call(agent="merchant", session_id=session_id, **meta)
        return _parse_json_response(text)
    except Exception:
        # Record the failed attempt so the dashboard shows the call was made
        _metrics.record_call(
            agent="merchant",
            model=MERCHANT_MODEL,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            session_id=session_id,
        )
        raise


async def call_gemini_shopping(
    system_prompt: str,
    user_content: str,
    response_schema: Optional[Any] = None,
    timeout_s: float = 10.0,
    session_id: Optional[str] = None,
) -> tuple[str, dict]:
    """
    Shopping agent Gemini call. Returns (raw_text, metadata).
    shopping.py owns parsing, retry, and per-turn logging; this is a thin transport layer.
    Logs a gemini_call entry for the raw-call metrics dashboard.
    """
    if _dry_run:
        return "", {}  # shopping.py detects dry-run before calling this
    t0 = time.perf_counter()
    try:
        text, meta = await _call_gemini_raw(
            model_name=SHOPPING_MODEL,
            system_prompt=system_prompt,
            user_content=user_content,
            response_schema=response_schema,
            timeout_s=timeout_s,
        )
        log.info(json.dumps({"event": "gemini_call", "agent": "shopping", **meta}))
        _metrics.record_call(agent="shopping", session_id=session_id, **meta)
        return text, meta
    except Exception:
        # Record the failed attempt so the dashboard shows the call was made
        _metrics.record_call(
            agent="shopping",
            model=SHOPPING_MODEL,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            session_id=session_id,
        )
        raise


# ---------------------------------------------------------------------------
# Response parsing (merchant path)
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str) -> dict:
    """Parse Gemini's text output as JSON. Strips markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned non-JSON response: {e}\nRaw: {raw[:300]}")
