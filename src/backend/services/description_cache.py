"""
Description resolver for analyzer recommendations — with an optional cache.

The cache is **disabled by default**. When disabled, every rule fire calls
the LLM with its prompt (matching the original behavior); the static_text is
used only as a fallback when the LLM fails. Nothing is persisted.

When enabled, results are cached forever in the `Descriptions` DynamoDB table
keyed by `(rule_id + hash(key_inputs))`. The static_text becomes the
preferred fast path (zero LLM cost), with the LLM only used if the rule was
called without one.

Flip the toggle two ways:
  - **In code** (fastest): change `USE_DESCRIPTION_CACHE` below to True.
  - **Via env var** (preferred for deployments): set
    `USE_DESCRIPTION_CACHE=true` in your environment / .env file.

The env var wins if both are set (env var of "true"/"1"/"yes" → on).
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, Optional

from connections.db import get_description_from_cache, upsert_description_in_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------

# Flip this to True to enable the cache from code.
USE_DESCRIPTION_CACHE: bool = True


def _cache_enabled() -> bool:
    """True if either the in-code toggle or the env var is set."""
    env = os.getenv("USE_DESCRIPTION_CACHE", "").strip().lower()
    if env in ("true", "1", "yes", "on"):
        return True
    if env in ("false", "0", "no", "off"):
        return False
    return USE_DESCRIPTION_CACHE


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------

def _cache_key(rule_id: str, key_inputs: Optional[Dict[str, Any]] = None) -> str:
    """
    Stable cache key for a rule fire.

    For boilerplate rules with `key_inputs=None`, the key is just `rule:<id>`
    — same description for every resource, written once.

    For context-aware rules, `key_inputs` should include the values that
    actually vary the description (use coarse buckets, not raw floats, so
    similar cases share a cache entry).
    """
    if not key_inputs:
        return f"rule:{rule_id}"
    sorted_inputs = sorted((k, str(v)) for k, v in key_inputs.items())
    digest = hashlib.sha1(repr(sorted_inputs).encode()).hexdigest()[:10]
    return f"rule:{rule_id}:{digest}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_description(
    rule_id: str,
    *,
    static_text: Optional[str] = None,
    prompt: Optional[str] = None,
    key_inputs: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Resolve a description for a recommendation rule.

    Behavior depends on the cache toggle:

    **Cache OFF (default):**
      1. Call the LLM with `prompt` if provided. Return the result on success.
      2. On LLM failure (or no prompt): return `static_text`.
      3. Final fallback: empty string.
      Nothing is read from or written to the DynamoDB cache.

    **Cache ON:**
      1. Cache hit → return cached text.
      2. `static_text` → cache it, return it (fast, free, no LLM).
      3. `prompt` → call LLM, cache result, return it.
      4. On LLM failure: return `static_text` (or `prompt` as final fallback)
         WITHOUT caching, so the next attempt can succeed.
    """
    if _cache_enabled():
        return _resolve_with_cache(rule_id, static_text, prompt, key_inputs)
    return _resolve_without_cache(static_text, prompt)


# ---------------------------------------------------------------------------
# Resolution paths
# ---------------------------------------------------------------------------

def _resolve_without_cache(
    static_text: Optional[str],
    prompt: Optional[str],
) -> str:
    """Live LLM call every time. Static text is fallback only."""
    if prompt:
        try:
            from agent.llm.llm_client import get_llm_client
            llm = get_llm_client()
            text = llm.generate(prompt)
            if text and text.strip():
                logger.info("[desc] LLM call succeeded (cache off)")
                return text.strip()
        except Exception as e:
            logger.warning("[desc] LLM description generation failed: %s", e)
    logger.info("[desc] using static fallback (cache off, no LLM result)")
    return static_text or prompt or ""


def _resolve_with_cache(
    rule_id: str,
    static_text: Optional[str],
    prompt: Optional[str],
    key_inputs: Optional[Dict[str, Any]],
) -> str:
    """Cache → static text → LLM, with each successful resolution persisted."""
    cache_key = _cache_key(rule_id, key_inputs)

    cached = get_description_from_cache(cache_key)
    if cached:
        return cached

    if static_text:
        upsert_description_in_cache(cache_key, static_text)
        return static_text

    if prompt:
        try:
            from agent.llm.llm_client import get_llm_client
            llm = get_llm_client()
            text = llm.generate(prompt)
            if text and text.strip():
                upsert_description_in_cache(cache_key, text.strip())
                return text.strip()
        except Exception as e:
            logger.warning("LLM description generation failed for %s: %s", rule_id, e)
        return prompt

    return ""
