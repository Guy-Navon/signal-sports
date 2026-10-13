"""Hosted-LLM bake-off on the owner's census ratings (#262, docs/HOSTING_PLAN.md §10.4).

Which hosted model should replace the PC's Ollama? Not the one that agrees most
with the old model, and not the cheapest on paper: the one whose FEED DECISIONS
match the owner's ratings best (docs/LLM_CLASSIFICATION.md, "Judge by
decisions, not by agreement"). For every candidate this script:

1. replays each rated census article through the PRODUCTION path
   (``ingestion_service._normalise``: rules, the LLM gate, the merge and
   guardrails) with only the LLM provider swapped;
2. scores the result with the owner's LIVE profile (read-only from the DB),
   exactly like the census engine decision (``score_article_v2``);
3. compares decisions with the owner's ratings, and with two baselines on the
   same rows: the facts stored today (mostly Ollama) and current rules-only.

    python scripts/llm_bakeoff.py --list-candidates
    python scripts/llm_bakeoff.py --candidate groq-gpt-oss-20b --candidate groq-gpt-oss-120b      # dry run
    python scripts/llm_bakeoff.py --candidate groq-gpt-oss-20b --stage smoke --live                # <= 30 calls
    python scripts/llm_bakeoff.py --candidate groq-gpt-oss-20b --stage accuracy --live --out ../docs/qa/llm_bakeoff.json

Safety and bounds:
- DRY RUN BY DEFAULT: without ``--live`` no provider is built and nothing is
  sent; it prints the selection, the calls, an estimate of tokens and cost,
  and whether each key is present (never its value).
- ``--max-calls`` per candidate (smoke 30, accuracy 225; at most 500), plus a
  1,000-call ceiling for the whole run. Rows are chosen once, in id order, so
  every candidate is judged on the SAME rows.
- Pacing per candidate for free-tier limits; a 429 waits for the provider's
  pause and retries that row once, then stops the candidate.
- Every response is cached (``backend/data/bakeoff/``, untracked): a re-run
  re-scores for free and never pays twice for the same prompt.
- The corpus is opened read-only (SQLite ``mode=ro``) and the app's own engine
  is pinned to an in-memory database: nothing is written to any database.
- Keys come from the environment / ``backend/.env``: GROQ_API_KEY,
  GEMINI_API_KEY, OPENAI_API_KEY. They are never printed.
- ``mode`` is ``dry_run``, ``live`` or ``offline`` (a fake provider in tests),
  so a mocked result can never pass for a measurement.

Prices are the providers' official list prices as checked on 2026-10-13
(HOSTING_PLAN §10.2); the report labels every cost as an estimate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

STAGE_DEFAULT_CALLS = {"smoke": 30, "accuracy": 225}
MAX_CALLS_PER_CANDIDATE = 500
MAX_CALLS_PER_RUN = 1000
CALLS_PER_MONTH = 1350          # ~45 LLM calls a day in production (HOSTING_PLAN F4)
ASSUMED_PROMPT_TOKENS = 1250    # dry-run estimates only
ASSUMED_OUTPUT_TOKENS = 250
RATING_TO_TIER = {"push": "push", "high": "high_feed", "feed": "feed", "low": "low_feed", "hide": "hidden"}
TIER_RANK = {"hidden": 0, "low_feed": 1, "feed": 2, "high_feed": 3, "push": 4}
WANTED = ("feed", "high_feed", "push")
PRICES_CHECKED = "2026-10-13"


@dataclass(frozen=True)
class Candidate:
    name: str
    kind: str                     # "openai_compat" | "gemini" | "fake" (tests)
    model: str
    key_env: str
    base_url: str = ""
    price_in: float = 0.0         # USD per 1M input tokens
    price_cached_in: float = 0.0  # USD per 1M cached input tokens
    price_out: float = 0.0        # USD per 1M output tokens (reasoning included)
    min_interval_s: float = 1.0
    response_format: str = "json_schema"
    reasoning_effort: str = "low"
    token_limit_param: str = "max_tokens"
    send_temperature: bool = True
    max_output_tokens: int = 1000
    note: str = ""


CANDIDATES: dict[str, Candidate] = {
    c.name: c for c in (
        Candidate(
            "groq-gpt-oss-20b", "openai_compat", "openai/gpt-oss-20b", "GROQ_API_KEY",
            "https://api.groq.com/openai/v1", 0.075, 0.0375, 0.30, 8.0,
            note="Groq production model; strict JSON schema; free plan 30 RPM, 8K TPM, 1K RPD, "
                 "200K TPD per organization; cached prompt tokens are half price and don't count "
                 "toward rate limits",
        ),
        Candidate(
            "groq-gpt-oss-120b", "openai_compat", "openai/gpt-oss-120b", "GROQ_API_KEY",
            "https://api.groq.com/openai/v1", 0.15, 0.075, 0.60, 8.0,
            note="Groq production model; strict JSON schema; same free-plan limits as the 20b",
        ),
        Candidate(
            "gemini-3.1-flash-lite", "gemini", "gemini-3.1-flash-lite", "GEMINI_API_KEY",
            price_in=0.25, price_cached_in=0.025, price_out=1.50, min_interval_s=4.0,
            max_output_tokens=500,
            note="existing Gemini provider at the production output cap (500 tokens, so a thinking "
                 "truncation shows up); free-tier content may be used to improve Google's products",
        ),
        Candidate(
            "openai-gpt-5-nano", "openai_compat", "gpt-5-nano", "OPENAI_API_KEY",
            "https://api.openai.com/v1", 0.05, 0.005, 0.40, 1.0,
            reasoning_effort="minimal", token_limit_param="max_completion_tokens",
            send_temperature=False, max_output_tokens=2000,
            note="paid only (no free tier); reasoning model: max_completion_tokens, default temperature",
        ),
    )
}


# ── Provider construction, pacing, retry and cache ───────────────────────────

class CandidateRefused(RuntimeError):
    """The candidate cannot run (missing key, budget, rate limit)."""


def build_provider(candidate: Candidate, api_key: str):
    if candidate.kind == "gemini":
        from app.classification.providers import GeminiLLMProvider
        return GeminiLLMProvider(api_key=api_key, model=candidate.model,
                                 max_output_tokens=candidate.max_output_tokens)
    if candidate.kind == "openai_compat":
        from app.classification.providers import OpenAICompatibleProvider
        return OpenAICompatibleProvider(
            base_url=candidate.base_url, api_key=api_key, model=candidate.model, timeout=30.0,
            max_output_tokens=candidate.max_output_tokens, response_format=candidate.response_format,
            reasoning_effort=candidate.reasoning_effort, token_limit_param=candidate.token_limit_param,
            send_temperature=candidate.send_temperature,
        )
    raise CandidateRefused(f"no live provider for kind {candidate.kind!r}")


def prompt_key(candidate: Candidate, title: str, subtitle: Optional[str]) -> str:
    from app.classification.prompt import CLASSIFICATION_SYSTEM_PROMPT, build_user_message

    material = json.dumps([candidate.kind, candidate.model, candidate.response_format,
                           candidate.reasoning_effort, candidate.max_output_tokens,
                           CLASSIFICATION_SYSTEM_PROMPT, build_user_message(title, subtitle)],
                          ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ResponseCache:
    """Append-only JSONL of raw responses, keyed by the exact prompt."""

    def __init__(self, path: Optional[Path]):
        self.path = path
        self.entries: dict[str, dict] = {}
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self.entries[entry["key"]] = entry

    def get(self, key: str) -> Optional[dict]:
        return self.entries.get(key)

    def put(self, entry: dict) -> None:
        self.entries[entry["key"]] = entry
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


class Recorder:
    """Stands in for the production provider during a replay.

    Live calls are bounded by ``budget`` and paced by ``min_interval_s``; a 429
    waits out the provider's pause and retries once. Cached prompts replay
    without a call. Every outcome is logged for the report.
    """

    can_classify = True

    def __init__(self, candidate: Candidate, inner, cache: ResponseCache, budget: int,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.candidate, self.inner, self.cache, self.budget = candidate, inner, cache, budget
        self.sleep, self.clock = sleep, clock
        self.live_calls = 0           # every attempt, including rejected 429s
        self.answered_calls = 0       # attempts the provider answered: what the budget bounds
        self.cached_calls = 0
        self.rate_limited_retries = 0
        self.stopped: Optional[str] = None
        self.log: list[dict] = []
        self._last_call_at: Optional[float] = None
        self._reset()

    def _reset(self) -> None:
        self.last_failure_was_connect_error = False
        self.last_failure_reason = "none"
        self.last_call_latency_ms = None
        self.last_raw_content = None
        self.last_usage = None

    @property
    def provider_id(self) -> str:
        return getattr(self.inner, "provider_id", f"{self.candidate.kind}:{self.candidate.model}")

    def _apply(self, entry: dict):
        from app.classification.validation import parse_and_validate_llm_json

        self.last_failure_reason = entry["failure_reason"]
        self.last_failure_was_connect_error = entry["failure_reason"] == "connect_error"
        self.last_call_latency_ms = entry.get("latency_ms")
        self.last_raw_content = entry.get("raw")
        self.last_usage = entry.get("usage")
        if entry["failure_reason"] != "none" or entry.get("raw") is None:
            return None
        return parse_and_validate_llm_json(entry["raw"])

    def _call_inner(self, title, language, subtitle):
        if self._last_call_at is not None:
            wait = self.candidate.min_interval_s - (self.clock() - self._last_call_at)
            if wait > 0:
                self.sleep(wait)
        self._last_call_at = self.clock()
        self.live_calls += 1
        result = self.inner.classify_title(title, language, subtitle=subtitle)
        if getattr(self.inner, "last_http_status", None) != 429:
            self.answered_calls += 1
        return result

    def classify_title(self, title: str, language: str, subtitle: Optional[str] = None):
        self._reset()
        key = prompt_key(self.candidate, title, subtitle)
        cached = self.cache.get(key)
        if cached is not None:
            self.cached_calls += 1
            self.log.append({**cached, "from_cache": True})
            return self._apply(cached)
        if self.stopped or self.answered_calls >= self.budget:
            self.stopped = self.stopped or "budget"
            raise CandidateRefused(f"{self.candidate.name}: {self.stopped}")

        result = self._call_inner(title, language, subtitle)
        if getattr(self.inner, "last_http_status", None) == 429:
            deadline = self.clock() + 300
            while getattr(self.inner, "rate_limit_paused", lambda: False)() and self.clock() < deadline:
                self.sleep(5)
            self.rate_limited_retries += 1
            result = self._call_inner(title, language, subtitle)
            if getattr(self.inner, "last_http_status", None) == 429:
                self.stopped = "rate_limited"
                raise CandidateRefused(f"{self.candidate.name}: still rate-limited after one retry")

        entry = {
            "key": key,
            "candidate": self.candidate.name,
            "failure_reason": getattr(self.inner, "last_failure_reason", "none")
            if result is None else "none",
            "raw": getattr(self.inner, "last_raw_content", None),
            "latency_ms": getattr(self.inner, "last_call_latency_ms", None),
            "usage": getattr(self.inner, "last_usage", None),
            "finish_reason": getattr(self.inner, "last_finish_reason", None),
            "http_status": getattr(self.inner, "last_http_status", None),
            "at": datetime.now(tz=timezone.utc).isoformat(),
        }
        if result is None and entry["failure_reason"] == "none":
            entry["failure_reason"] = "bad_response_shape"
        self.cache.put(entry)
        self.log.append({**entry, "from_cache": False})
        return self._apply(entry)


class _GateProbe:
    """Records which rows the production gate would send to the LLM. Never calls out."""

    can_classify = True
    provider_id = "gate-probe"
    last_failure_was_connect_error = False
    last_failure_reason = "none"
    last_call_latency_ms = None
    last_raw_content = None
    last_usage = None

    def __init__(self):
        self.called = False

    def classify_title(self, title, language, subtitle=None):
        self.called = True
        return None


# ── Data ──────────────────────────────────────────────────────────────────────

@dataclass
class Row:
    id: str
    source: str
    url: str
    title: str
    subtitle: Optional[str]
    published_at: Optional[datetime]
    rating: str                  # owner's tier (hidden..push)


def load_ratings(ratings_path: Path, review_path: Optional[Path], profile: str) -> dict[str, str]:
    raw = json.loads(ratings_path.read_text(encoding="utf-8"))
    ratings = dict((raw.get("ratings", raw)).get(profile, {}))
    if review_path:
        rev = json.loads(review_path.read_text(encoding="utf-8"))
        ratings.update((rev.get("ratings", rev)).get(profile, {}))
    return {k: RATING_TO_TIER[v] for k, v in ratings.items() if v in RATING_TO_TIER}


def open_readonly(db_path: Path):
    """A SQLAlchemy session on the corpus that SQLite itself makes read-only."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///file:{db_path.resolve().as_posix()}?mode=ro&uri=true")
    return engine, sessionmaker(bind=engine)()


def load_rows(session, sample_path: Path, ratings: dict[str, str], profile: str) -> list[Row]:
    from sqlalchemy import text

    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    ids = [item["id"] for item in sample["profiles"][profile]["items"] if item["id"] in ratings]
    rows = []
    for article_id in sorted(set(ids)):
        rec = session.execute(text(
            "SELECT source, url, title, subtitle, published_at FROM articles WHERE id = :id"
        ), {"id": article_id}).fetchone()
        if rec is None:
            continue
        published = None
        if rec[4]:
            published = datetime.fromisoformat(rec[4])
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        rows.append(Row(article_id, rec[0], rec[1], rec[2], rec[3], published, ratings[article_id]))
    return rows


# ── Replay and scoring ───────────────────────────────────────────────────────

def _swap_provider(provider):
    from app.ingestion import ingestion_service
    previous = ingestion_service._LLM_PROVIDER
    ingestion_service._LLM_PROVIDER = provider
    return previous


def replay(rows: list[Row], provider) -> dict[str, object]:
    """{id: Article} through the production _normalise with ``provider``."""
    from app.ingestion import ingestion_service
    from app.ingestion.adapters.base import RawSourceItem
    from app.ingestion.config import get_source_config

    previous = _swap_provider(provider)
    try:
        out = {}
        for row in rows:
            cfg = get_source_config(row.source)
            if cfg is None:
                continue
            item = RawSourceItem(source_id=row.source, url=row.url, title=row.title,
                                 published_at=row.published_at, summary=row.subtitle)
            article, _, _ = ingestion_service._normalise(item, cfg)
            out[row.id] = article
        return out
    finally:
        _swap_provider(previous)


def gate_eligible(rows: list[Row]) -> list[str]:
    """Ids the production gate sends to the LLM, in id order (no call is made)."""
    eligible = []
    for row in rows:
        probe = _GateProbe()
        replay([row], probe)
        if probe.called:
            eligible.append(row.id)
    return eligible


def decisions(articles: dict, profile) -> dict[str, str]:
    from app.services.preference_engine import score_article_v2
    return {k: score_article_v2(a, profile, set()).decision for k, a in articles.items()}


def metrics(dec: dict[str, str], truth: dict[str, str], ids: list[str]) -> dict:
    ids = [i for i in ids if i in dec and i in truth]
    if not ids:
        return {"rated": 0}
    shown = [i for i in ids if dec[i] != "hidden"]
    wanted = [i for i in ids if truth[i] in WANTED]
    pushes = [i for i in ids if dec[i] == "push"]
    return {
        "rated": len(ids),
        "exact": sum(dec[i] == truth[i] for i in ids),
        "mean_abs_gap": round(sum(abs(TIER_RANK[dec[i]] - TIER_RANK[truth[i]]) for i in ids) / len(ids), 3),
        "shown": len(shown),
        "shown_precision": round(sum(truth[i] != "hidden" for i in shown) / len(shown), 4) if shown else None,
        "wanted": len(wanted),
        "feed_plus_recall": round(sum(dec[i] != "hidden" for i in wanted) / len(wanted), 4) if wanted else None,
        "pushes": len(pushes),
        "push_precision": round(sum(truth[i] == "push" for i in pushes) / len(pushes), 4) if pushes else None,
        "wrong_pushes": sorted(i for i in pushes if truth[i] != "push"),
        "false_hides_of_wanted": sorted(i for i in wanted if dec[i] == "hidden"),
    }


def llm_stats(recorder: Recorder, articles: dict, ids: list[str], candidate: Candidate) -> dict:
    entries = [e for e in recorder.log]
    reasons: dict[str, int] = {}
    for e in entries:
        reasons[e["failure_reason"]] = reasons.get(e["failure_reason"], 0) + 1
    calls = len(entries)
    invalid = reasons.get("unparseable_json", 0) + reasons.get("bad_response_shape", 0)
    truncated = sum(1 for e in entries if e.get("finish_reason") in ("length", "MAX_TOKENS"))
    latencies = sorted(e["latency_ms"] for e in entries if not e["from_cache"] and e.get("latency_ms") is not None)
    tokens = {"prompt": 0, "cached_prompt": 0, "completion": 0, "reasoning": 0}
    for e in entries:
        usage = e.get("usage") or {}
        tokens["prompt"] += usage.get("prompt_tokens") or 0
        tokens["cached_prompt"] += usage.get("cached_prompt_tokens") or 0
        tokens["completion"] += usage.get("completion_tokens") or 0
        tokens["reasoning"] += usage.get("reasoning_tokens") or 0
    # OpenAI-style APIs count reasoning inside completion_tokens; Gemini reports it apart.
    output = tokens["completion"] + (tokens["reasoning"] if candidate.kind == "gemini" else 0)
    cost = ((tokens["prompt"] - tokens["cached_prompt"]) / 1e6 * candidate.price_in
            + tokens["cached_prompt"] / 1e6 * candidate.price_cached_in
            + output / 1e6 * candidate.price_out)
    low_conf = sum(1 for i in ids if getattr(articles.get(i), "classified_by", "") == "rules_fallback_low_confidence")
    return {
        "calls": calls,
        "live_calls": recorder.live_calls,
        "from_cache": recorder.cached_calls,
        "rate_limited_retries": recorder.rate_limited_retries,
        "failure_reasons": reasons,
        "validation_failure_rate": round(invalid / calls, 4) if calls else None,
        "low_confidence_fallbacks": low_conf,
        "truncated": truncated,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 1) if latencies else None,
            "p95": round(latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))], 1) if latencies else None,
        },
        "tokens": tokens,
        # What these responses cost at list price, whether fresh or replayed from the cache.
        "cost_usd_of_these_responses": round(cost, 6),
        "est_cost_usd_per_month": round(cost / calls * CALLS_PER_MONTH, 4) if calls else None,
        "cost_note": f"list prices checked {PRICES_CHECKED}; an estimate, not a bill",
    }


def field_changes(a: dict, b: dict, ids: list[str]) -> dict[str, int]:
    out = {"sport": 0, "league": 0, "event_type": 0}
    for i in ids:
        if i in a and i in b:
            for f in out:
                if getattr(a[i], f) != getattr(b[i], f):
                    out[f] += 1
    return out


def verdict(stage: str, cand: dict, base: dict, stats: dict) -> dict:
    checks = {}
    if stage == "smoke":
        checks["all_valid_json"] = stats["validation_failure_rate"] in (0, 0.0)
        checks["no_truncation"] = stats["truncated"] == 0
        p95 = stats["latency_ms"]["p95"]
        checks["p95_latency_le_5s"] = p95 is None or p95 <= 5000
    else:
        rate = stats["validation_failure_rate"]
        checks["validation_failures_le_2pct"] = rate is not None and rate <= 0.02
        new_wrong = sorted(set(cand.get("wrong_pushes", [])) - set(base.get("wrong_pushes", [])))
        checks["no_new_wrong_push"] = not new_wrong
        for key in ("feed_plus_recall", "shown_precision"):
            c, b = cand.get(key), base.get(key)
            checks[f"{key}_within_3pp_of_baseline"] = c is not None and b is not None and c >= b - 0.03
    return {"passes": all(checks.values()), "checks": checks}


# ── Orchestration ────────────────────────────────────────────────────────────

def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def run_bakeoff(
    *,
    db_path: Path,
    sample_path: Path,
    ratings_path: Path,
    review_path: Optional[Path],
    candidates: list[Candidate],
    stage: str,
    max_calls: int,
    live: bool,
    cache_dir: Optional[Path],
    profile_id: str = "guy",
    provider_factory: Optional[Callable[[Candidate], object]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    if not 0 < max_calls <= MAX_CALLS_PER_CANDIDATE:
        raise ValueError(f"max_calls must be 1..{MAX_CALLS_PER_CANDIDATE}")
    if max_calls * len(candidates) > MAX_CALLS_PER_RUN:
        raise ValueError(f"more than {MAX_CALLS_PER_RUN} calls in one run")
    from app.repositories import article_repository, profile_repository

    ratings = load_ratings(ratings_path, review_path, profile_id)
    engine, session = open_readonly(db_path)
    try:
        profile = profile_repository.get_by_id(session, profile_id)
        if profile is None:
            raise SystemExit(f"profile {profile_id!r} is not in {db_path}")
        rows = load_rows(session, sample_path, ratings, profile_id)
        stored = {r.id: article_repository.get_by_id(session, r.id) for r in rows}
    finally:
        session.close()
        engine.dispose()

    eligible = gate_eligible(rows)
    selected = eligible[:max_calls]
    selected_set, eligible_set = set(selected), set(eligible)
    evaluated = [r for r in rows if r.id in selected_set or r.id not in eligible_set]
    eval_ids = [r.id for r in evaluated]

    from app.classification.providers import DisabledLLMProvider
    rules = replay(evaluated, DisabledLLMProvider())
    base_dec = decisions(stored, profile)
    rules_dec = decisions(rules, profile)
    truth = {r.id: r.rating for r in rows}

    report = {
        "meta": {
            "mode": "dry_run" if not live else "live",
            "stage": stage,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "git_sha": _git_sha(),
            "database": db_path.name,
            "sample": sample_path.name,
            "ratings": ratings_path.name,
            "review": review_path.name if review_path else None,
            "profile": profile_id,
            "rated_rows": len(rows),
            "llm_eligible_rows": len(eligible),
            "selected_llm_rows": len(selected),
            "evaluated_rows": len(evaluated),
            "max_calls_per_candidate": max_calls,
            "prices_checked": PRICES_CHECKED,
        },
        "baselines": {
            "stored_facts": {
                "llm_rows": metrics(base_dec, truth, selected),
                "all_rows": metrics(base_dec, truth, eval_ids),
                "note": "the facts in the DB today (mostly qwen2.5:3b via Ollama, older code)",
            },
            "rules_only": {
                "llm_rows": metrics(rules_dec, truth, selected),
                "all_rows": metrics(rules_dec, truth, eval_ids),
                "note": "current code, no LLM",
            },
        },
        "candidates": {},
    }

    if not live:
        for c in candidates:
            report["candidates"][c.name] = {
                "model": c.model,
                "key_present": bool(os.environ.get(c.key_env, "").strip()),
                "key_env": c.key_env,
                "planned_calls": len(selected),
                "est_minutes": round(len(selected) * c.min_interval_s / 60, 1),
                "est_cost_usd": round(len(selected) * (ASSUMED_PROMPT_TOKENS / 1e6 * c.price_in
                                                       + ASSUMED_OUTPUT_TOKENS / 1e6 * c.price_out), 4),
                "note": c.note,
            }
        return report

    any_offline = False
    for c in candidates:
        if provider_factory is not None:
            inner = provider_factory(c)
            any_offline = any_offline or c.kind == "fake"
        else:
            key = os.environ.get(c.key_env, "").strip()
            if not key:
                report["candidates"][c.name] = {"skipped": f"{c.key_env} is not set"}
                continue
            inner = build_provider(c, key)
        cache = ResponseCache(cache_dir / f"{c.name}.jsonl" if cache_dir else None)
        recorder = Recorder(c, inner, cache, budget=len(selected), sleep=sleep)
        try:
            articles = replay(evaluated, recorder)
        except CandidateRefused as exc:
            report["candidates"][c.name] = {"stopped": str(exc), "live_calls": recorder.live_calls}
            continue
        cand_dec = decisions(articles, profile)
        llm_rows = metrics(cand_dec, truth, selected)
        stats = llm_stats(recorder, articles, selected, c)
        flips = [i for i in selected if cand_dec.get(i) != base_dec.get(i)]
        report["candidates"][c.name] = {
            "model": c.model,
            "provider_id": recorder.provider_id,
            "llm_rows": llm_rows,
            "all_rows": metrics(cand_dec, truth, eval_ids),
            "llm": stats,
            "field_changes_vs_stored": field_changes(articles, stored, selected),
            "field_changes_vs_rules": field_changes(articles, rules, selected),
            "verdict": verdict(stage, llm_rows, report["baselines"]["stored_facts"]["llm_rows"], stats),
            "decision_changes_vs_stored": {
                "rows": len(flips),
                "closer_to_owner": sum(abs(TIER_RANK[cand_dec[i]] - TIER_RANK[truth[i]])
                                       < abs(TIER_RANK[base_dec[i]] - TIER_RANK[truth[i]]) for i in flips),
                "further": sum(abs(TIER_RANK[cand_dec[i]] - TIER_RANK[truth[i]])
                               > abs(TIER_RANK[base_dec[i]] - TIER_RANK[truth[i]]) for i in flips),
            },
            "disagreements": [
                {"id": i, "title": next(r.title for r in rows if r.id == i)[:90], "owner": truth[i],
                 "candidate": cand_dec[i], "stored": base_dec.get(i), "rules": rules_dec.get(i)}
                for i in selected if cand_dec.get(i) != truth[i]
            ][:40],
        }
    if any_offline:
        report["meta"]["mode"] = "offline"

    passing = [(name, r) for name, r in report["candidates"].items()
               if isinstance(r, dict) and r.get("verdict", {}).get("passes")]
    passing.sort(key=lambda kv: (kv[1]["llm"]["est_cost_usd_per_month"] or 0.0,
                                 -(kv[1]["llm_rows"].get("feed_plus_recall") or 0.0)))
    report["ranking"] = {
        "rule": "cheapest candidate that passes this stage's criteria; ties go to feed+ recall",
        "passing_in_order": [name for name, _ in passing],
        "recommended": passing[0][0] if passing else None,
    }
    return report


def _summary(report: dict) -> str:
    meta = report["meta"]
    lines = [f"mode={meta['mode']} stage={meta['stage']} rated={meta['rated_rows']} "
             f"llm-eligible={meta['llm_eligible_rows']} selected={meta['selected_llm_rows']}"]

    def fmt(m: dict) -> str:
        if not m.get("rated"):
            return "no rows"
        return (f"exact {m['exact']}/{m['rated']} | shown prec {m['shown_precision']} | "
                f"feed+ recall {m['feed_plus_recall']} | push {m['push_precision']} "
                f"(wrong {len(m['wrong_pushes'])})")

    for name, base in report["baselines"].items():
        lines.append(f"BASE {name:12} llm rows: {fmt(base['llm_rows'])}")
    for name, res in report["candidates"].items():
        if "llm_rows" not in res:
            lines.append(f"CAND {name:22} {json.dumps(res, ensure_ascii=False)}")
            continue
        llm = res["llm"]
        lines.append(f"CAND {name:22} llm rows: {fmt(res['llm_rows'])}")
        lines.append(f"     invalid {llm['validation_failure_rate']} | truncated {llm['truncated']} | "
                     f"p95 {llm['latency_ms']['p95']} ms | ~${llm['est_cost_usd_per_month']}/month | "
                     f"{'PASS' if res['verdict']['passes'] else 'FAIL'} {res['verdict']['checks']}")
    if "ranking" in report:
        lines.append(f"recommended: {report['ranking']['recommended']}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", action="append", default=[], help="repeatable; see --list-candidates")
    parser.add_argument("--list-candidates", action="store_true")
    parser.add_argument("--stage", choices=sorted(STAGE_DEFAULT_CALLS), default="smoke")
    parser.add_argument("--max-calls", type=int, help="per candidate (default: 30 smoke, 225 accuracy)")
    parser.add_argument("--live", action="store_true", help="actually call the providers (default: dry run)")
    parser.add_argument("--db", type=Path, default=BACKEND / "data" / "signal_sports.db")
    parser.add_argument("--sample", type=Path, default=REPO / "docs" / "qa" / "census2_sample.json")
    parser.add_argument("--ratings", type=Path, default=REPO / "docs" / "qa" / "census2_ratings.json")
    parser.add_argument("--review", type=Path, help="re-rated rows overriding --ratings")
    parser.add_argument("--cache-dir", type=Path, default=BACKEND / "data" / "bakeoff")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--out", type=Path, help="also write the full JSON report here")
    args = parser.parse_args(argv)

    if args.list_candidates:
        for c in CANDIDATES.values():
            print(f"{c.name:24} {c.model:24} key={c.key_env:16} ${c.price_in}/${c.price_out} per 1M  {c.note}")
        return 0
    unknown = [n for n in args.candidate if n not in CANDIDATES]
    if unknown or not args.candidate:
        parser.error(f"choose --candidate from: {', '.join(CANDIDATES)}")
    if not args.db.is_file():
        print(f"no such database: {args.db}")
        return 1

    # Keys may live in backend/.env; nothing else from it may act here.
    try:
        from dotenv import load_dotenv
        load_dotenv(BACKEND / ".env", override=False)
    except ImportError:  # pragma: no cover
        pass
    os.environ["CLASSIFICATION_PROVIDER"] = "disabled"
    os.environ["TRANSLATION_PROVIDER"] = "disabled"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    report = run_bakeoff(
        db_path=args.db, sample_path=args.sample, ratings_path=args.ratings, review_path=args.review,
        candidates=[CANDIDATES[n] for n in args.candidate], stage=args.stage,
        max_calls=args.max_calls or STAGE_DEFAULT_CALLS[args.stage], live=args.live,
        cache_dir=None if args.no_cache else args.cache_dir,
    )
    print(_summary(report))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8", newline="\n")
        print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
