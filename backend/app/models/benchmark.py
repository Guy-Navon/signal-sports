from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class FallbackStats(BaseModel):
    connect_error: int = 0
    timeout_or_parse: int = 0
    low_confidence: int = 0


class SourceBenchmarkStats(BaseModel):
    total_ms: float
    llm_attempts: int = 0
    llm_successes: int = 0
    llm_skipped: int = 0
    skip_rate: Optional[float] = None
    llm_avg_ms: Optional[float] = None
    llm_p95_ms: Optional[float] = None
    fallbacks: FallbackStats = Field(default_factory=FallbackStats)
    llm_skip_reasons: Dict[str, int] = Field(default_factory=dict)
    llm_call_reasons: Dict[str, int] = Field(default_factory=dict)
    sport_unknown: int = 0


class BenchmarkRunResult(BaseModel):
    gating_enabled: bool
    sources: Dict[str, SourceBenchmarkStats]


class SourceComparison(BaseModel):
    llm_call_reduction: int
    skip_rate: float
    total_ms_reduction: float
    sport_unknown_delta: int
    passes_targets: bool


class LLMGatingBenchmarkResponse(BaseModel):
    provider: str
    sources: List[str]
    baseline: BenchmarkRunResult
    gated: BenchmarkRunResult
    comparison: Dict[str, SourceComparison]
