"""
Parse and validate raw LLM JSON output against allowed enum values.
Invalid enum values are replaced with safe defaults — never raise.
"""

import json
import logging
import re
from typing import Optional

from app.classification.llm_result import LLMClassificationResult

logger = logging.getLogger(__name__)

ALLOWED_SPORTS = {"basketball", "football", "tennis", "unknown"}
ALLOWED_LEAGUES = {
    "NBA", "EuroLeague", "EuroCup", "Israeli Basketball League",
    "Spanish ACB", "Turkish BSL", "Greek Basket League", "Italian LBA",
    "French LNB", "Wimbledon", "Roland Garros", "US Open", "Australian Open",
    "Israeli Premier League",
}
ALLOWED_EVENT_TYPES = {
    "signing", "negotiation", "candidate", "injury", "major_trade",
    "match_result", "regular_season_result", "finals_result", "title_win",
    "grand_slam_winner", "playoff_result", "early_round_result",
    "schedule", "release", "news",
}
ALLOWED_IMPORTANCES = {"very_high", "high", "medium", "low"}

LLM_MIN_CONFIDENCE = 0.65


def _normalize_keys(raw: str) -> str:
    """
    Fix llama3.2:3b quirk where it outputs "key:": value instead of "key": value.
    Strips trailing colons from inside JSON string keys.
    Also strips chat-format garbage that appears after the closing brace.
    """
    # Remove trailing colon from inside quoted keys: "reason:" -> "reason"
    raw = re.sub(r'"(\w+):"\s*:', r'"\1":', raw)
    # Keep only up to the first top-level closing brace
    depth = 0
    for i, ch in enumerate(raw):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return raw[:i + 1]
    return raw


def _parse_raw(raw_content: str) -> Optional[dict]:
    """Parse LLM JSON with key-normalization and regex fallback."""
    cleaned = _normalize_keys(raw_content.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            candidate = _normalize_keys(match.group())
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    logger.warning("Could not parse LLM JSON: %r", raw_content[:200])
    return None


def parse_and_validate_llm_json(raw_content: str) -> Optional[LLMClassificationResult]:
    """
    Parse raw LLM JSON string and validate against allowed enum values.
    Returns None if JSON is unparseable.
    Invalid enum values fall back to safe defaults (never raises).
    """
    data = _parse_raw(raw_content)
    if data is None:
        return None
    if not isinstance(data, dict):
        return None

    sport = data.get("sport", "unknown")
    sport = sport if sport in ALLOWED_SPORTS else "unknown"

    league = data.get("league")
    league = league if isinstance(league, str) and league in ALLOWED_LEAGUES else None

    event_type = data.get("event_type", "news")
    event_type = event_type if event_type in ALLOWED_EVENT_TYPES else "news"

    importance = data.get("importance", "medium")
    importance = importance if importance in ALLOWED_IMPORTANCES else "medium"

    raw_confidence = data.get("confidence", 0.0)
    try:
        confidence = float(raw_confidence)
        if not (0.0 <= confidence <= 1.0):
            confidence = 0.0
    except (TypeError, ValueError):
        confidence = 0.0

    reason = str(data.get("reason", ""))[:500]

    raw_entities = data.get("entities", [])
    entities = [str(e) for e in raw_entities if isinstance(e, str)][:10]

    return LLMClassificationResult(
        sport=sport,
        league=league,
        entities=entities,
        event_type=event_type,
        importance=importance,
        confidence=confidence,
        reason=reason,
    )
