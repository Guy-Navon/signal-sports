from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMClassificationResult:
    """Raw output from an LLM classification call, before merging with rules."""
    sport: str                      # "basketball" | "football" | "tennis" | "unknown"
    league: Optional[str]           # canonical league name or None
    entities: list[str]             # free-text entity names as returned by LLM
    event_type: str                 # e.g. "signing", "title_win", "news"
    importance: str                 # "very_high" | "high" | "medium" | "low"
    confidence: float               # 0.0–1.0 self-assessed confidence
    reason: str                     # one-sentence explanation from LLM
