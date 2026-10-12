"""
metrics.py — In-memory LLM call metrics store.

Records every real Gemini call with latency and token counts.
Resets on server restart — good enough for demo purposes.
"""

import statistics
from datetime import datetime, timezone
from typing import Optional

_calls: list[dict] = []


def record_call(
    agent: str,
    model: str,
    latency_ms: int,
    prompt_tokens:   Optional[int] = None,
    output_tokens:   Optional[int] = None,
    thoughts_tokens: Optional[int] = None,
    session_id:      Optional[str] = None,
) -> None:
    """Append one LLM call record to the in-memory store."""
    _calls.append({
        "ts":             datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent":          agent,
        "model":          model,
        "latency_ms":     latency_ms,
        "prompt_tokens":  prompt_tokens,
        "output_tokens":  output_tokens,
        "thoughts_tokens": thoughts_tokens,
        "session_id":     session_id,
    })


def total_call_count() -> int:
    """Current number of recorded calls — use as a snapshot offset before a turn."""
    return len(_calls)


def calls_since(offset: int, session_id: Optional[str] = None) -> list[dict]:
    """Return calls appended after position `offset`, optionally filtered by session_id."""
    subset = _calls[offset:]
    if session_id is not None:
        subset = [c for c in subset if c.get("session_id") == session_id]
    return subset


def _agent_summary(agent: str) -> dict:
    subset = [c for c in _calls if c["agent"] == agent]
    if not subset:
        return {"calls": 0, "avg_latency_ms": 0, "prompt_tokens": 0, "output_tokens": 0}
    latencies = [c["latency_ms"] for c in subset if c["latency_ms"] is not None]
    return {
        "calls":          len(subset),
        "avg_latency_ms": int(statistics.mean(latencies)) if latencies else 0,
        "prompt_tokens":  sum(c["prompt_tokens"]  or 0 for c in subset),
        "output_tokens":  sum(c["output_tokens"]  or 0 for c in subset),
    }


def get_metrics() -> dict:
    """Return aggregated summary + last 100 raw call records."""
    empty_summary = {
        "total_calls":         0,
        "merchant_calls":      0,
        "shopping_calls":      0,
        "avg_latency_ms":      0,
        "p50_latency_ms":      0,
        "p95_latency_ms":      0,
        "max_latency_ms":      0,
        "total_prompt_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens":        0,
    }
    if not _calls:
        return {
            "calls":    [],
            "summary":  empty_summary,
            "by_agent": {
                "merchant": _agent_summary("merchant"),
                "shopping": _agent_summary("shopping"),
            },
        }

    latencies    = sorted(c["latency_ms"] for c in _calls if c["latency_ms"] is not None)
    n            = len(latencies)
    prompt_total = sum(c["prompt_tokens"]  or 0 for c in _calls)
    output_total = sum(c["output_tokens"]  or 0 for c in _calls)

    return {
        "calls": _calls[-100:],
        "summary": {
            "total_calls":         len(_calls),
            "merchant_calls":      sum(1 for c in _calls if c["agent"] == "merchant"),
            "shopping_calls":      sum(1 for c in _calls if c["agent"] == "shopping"),
            "avg_latency_ms":      int(statistics.mean(latencies)) if latencies else 0,
            "p50_latency_ms":      latencies[n // 2]         if n else 0,
            "p95_latency_ms":      latencies[max(0, int(n * 0.95) - 1)] if n else 0,
            "max_latency_ms":      latencies[-1]              if n else 0,
            "total_prompt_tokens": prompt_total,
            "total_output_tokens": output_total,
            "total_tokens":        prompt_total + output_total,
        },
        "by_agent": {
            "merchant": _agent_summary("merchant"),
            "shopping": _agent_summary("shopping"),
        },
    }
