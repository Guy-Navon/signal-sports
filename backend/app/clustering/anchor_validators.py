"""The three #141 approaches. EVALUATED, not selected.

  V1  LexicalFrequencyValidator — a pinned local Hebrew language resource.
  V2  LocalModelValidator       — the existing local model, as an EXCEPTION PATH.
  V3  HybridValidator           — deterministic-first; only UNRESOLVED candidates reach V2.

Plus V0 (TaxonomyValidator), the baseline that ships today: canonical matches only, everything
else abstains. V0 is safe and recovers 0/17.

THE INSIGHT V1 RESTS ON — and it is the same distinction this whole investigation kept
circling, finally stated correctly:

    RARE IN THE CORPUS is not RARE IN THE LANGUAGE.

    מדר   is COMMON in our corpus (df=13, because the story got saturation coverage)
          and RARE in Hebrew        (zipf 3.25) → it is a NAME.
    אדום  is RARE in our corpus
          and COMMON in Hebrew      (zipf 4.99, "red") → it is a WORD.

Document frequency could never separate these because it only ever looked at our corpus. A
Hebrew LANGUAGE-frequency resource looks at Hebrew. That is why it succeeds where every
rarity-over-the-corpus model failed.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from app.clustering.anchor_contract import (
    ABSTAINED,
    ACCEPTED,
    REJECTED,
    AnchorCandidate,
    ValidationDecision,
)
from app.clustering.anchors import _candidate_forms

_HEB = re.compile(r"^[֐-׿׳״'\"-]+$")


def _hebrew_words(normalized: str) -> list[str]:
    return [w for w in normalized.split() if _HEB.match(w)]


def _most_ordinary_zipf(word: str, zipf) -> float:
    """The frequency of a token's MOST ORDINARY reading.

    A prefixed ordinary word is the leak: 'בצהוב' ("in-yellow") has zipf 3.38 and looks
    rare, but it is just 'צהוב' ("yellow", zipf 4.45) with a preposition glued on — and
    matching strips that prefix, so it bridges as if it were a name. The validator must judge
    a token the same way the matcher will read it: across every candidate form, take the MOST
    ORDINARY (highest zipf). Precision-favouring by construction — a real name's stripped form
    is still rare (הנקינס → נקינס), so this never demotes a genuine name."""
    return max(float(zipf(f, "he")) for f in _candidate_forms(word))


# ══════════════════════════════════════════════════════════════════════════════
# V0 — baseline: canonical taxonomy only. Ships today.
# ══════════════════════════════════════════════════════════════════════════════

class TaxonomyValidator:
    """Accept ONLY what the taxonomy already proved. Abstain on everything else.

    Safe by construction and recovers 0/17 — which is the whole reason #141 exists. Canonical
    matches remain valid without further inference under EVERY approach below.
    """

    validator_id = "taxonomy"
    validator_version = "1"

    def available(self) -> bool:
        return True

    def validate(self, c: AnchorCandidate) -> ValidationDecision:
        if c.entity_id:
            return ValidationDecision(
                c.span_id(), ACCEPTED, self.validator_id, self.validator_version,
                "canonical_taxonomy", f"taxonomy:{c.taxonomy_kind}",
                normalized_anchor=c.entity_id,
            )
        return ValidationDecision(
            c.span_id(), ABSTAINED, self.validator_id, self.validator_version,
            "no_canonical_match", "the taxonomy has never heard of this span",
        )


# ══════════════════════════════════════════════════════════════════════════════
# V1 — pinned local Hebrew language-frequency resource
# ══════════════════════════════════════════════════════════════════════════════

#: A word of the Hebrew LANGUAGE at or above this zipf is not a name. Calibrated against the
#: adjudicated spans, where the separation is clean and wide:
#:      ordinary  ≥ 4.47  (יאללה 4.47 · שיא 4.62 · אדום 4.99 · נשאר 5.11 · הכל 5.87)
#:      names     ≤ 3.25  (מדר 3.25 · בראיינט 2.91 · דיארה 1.61 · הנקינס 1.14 · אוטורו 0.00)
#: The band between them is the ABSTENTION zone — V1 does not guess inside it.
ORDINARY_WORD_ZIPF = 4.4
NAME_ZIPF_MAX = 3.4


class LexicalFrequencyValidator:
    """Approach 1. Deterministic, offline, pinned. No model, no GPU, no network.

    A span is name-like when its Hebrew-language frequency is LOW. A span containing any
    high-frequency ordinary Hebrew word is REJECTED — that is what kills "נשאר אדום"
    ("stayed red"), which the generator happily proposed as a name.

    Fails closed: if the resource is missing, it abstains.
    """

    validator_id = "lexical_frequency"

    def __init__(self) -> None:
        self._zipf = None
        self._version = "unavailable"
        try:
            import importlib.metadata

            import wordfreq

            self._zipf = wordfreq.zipf_frequency
            self._version = f"wordfreq-{importlib.metadata.version('wordfreq')}"
        except Exception:
            pass

    @property
    def validator_version(self) -> str:  # type: ignore[override]
        return self._version

    def available(self) -> bool:
        return self._zipf is not None

    def validate(self, c: AnchorCandidate) -> ValidationDecision:
        if c.entity_id:
            return TaxonomyValidator().validate(c)
        if not self.available():
            return ValidationDecision(
                c.span_id(), ABSTAINED, self.validator_id, self._version,
                "resource_unavailable", "the Hebrew frequency resource is not installed",
            )

        words = _hebrew_words(c.normalized)
        if not words:
            return ValidationDecision(
                c.span_id(), ABSTAINED, self.validator_id, self._version,
                "no_hebrew_tokens", "nothing to judge",
            )

        freqs = {w: _most_ordinary_zipf(w, self._zipf) for w in words}
        worst = max(freqs.values())      # the MOST ordinary word in the span
        signals = {"zipf_he": freqs, "max_zipf": round(worst, 2)}

        if worst >= ORDINARY_WORD_ZIPF:
            common = [w for w, f in freqs.items() if f >= ORDINARY_WORD_ZIPF]
            return ValidationDecision(
                c.span_id(), REJECTED, self.validator_id, self._version,
                "ordinary_hebrew_word",
                f"contains ordinary Hebrew: {common} — a word of the language, not a name",
                signals=signals,
            )
        if worst <= NAME_ZIPF_MAX:
            return ValidationDecision(
                c.span_id(), ACCEPTED, self.validator_id, self._version,
                "rare_in_language",
                f"every token is rare in HEBREW (max zipf {worst:.2f}) — name-like",
                normalized_anchor=c.normalized, signals=signals,
            )
        return ValidationDecision(
            c.span_id(), ABSTAINED, self.validator_id, self._version,
            "uncertain_band",
            f"max zipf {worst:.2f} sits between the name and ordinary-word bands",
            signals=signals,
        )


# ══════════════════════════════════════════════════════════════════════════════
# V2 — the existing local model, as an exception path
# ══════════════════════════════════════════════════════════════════════════════

_PROMPT = """You are a Hebrew named-entity validator for a sports news system.

Decide whether the marked span [[...]] is a PERSON'S NAME (a player, coach, or official).

Context: {context}
Span: {span}
Field: {source}

Rules:
- A person's name is ACCEPT.
- An ordinary Hebrew word, verb, adjective, colour, or number is REJECT.
- A team, club, or competition name is REJECT (it is not a person).
- If you are not sure, ABSTAIN.

Answer with JSON only: {{"decision": "accept"|"reject"|"abstain", "reason": "<short>"}}"""


class LocalModelValidator:
    """Approach 2. Structured extraction through the local model already in the stack.

    ⚠️ Non-deterministic by nature. Pinned to temperature 0 and a fixed model tag, but the
    runtime is still a model — reproducibility is a REPORTED METRIC, not an assumption.

    Fails closed: if the model is unreachable, it abstains.
    """

    validator_id = "local_model"

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self.model = model or os.getenv("ANCHOR_MODEL", "qwen2.5:3b-instruct")
        self.base_url = base_url or os.getenv(
            "CLASSIFICATION_OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self.validator_version = f"{self.model}@t0"
        self.calls = 0

    def available(self) -> bool:
        try:
            import httpx

            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def validate(self, c: AnchorCandidate) -> ValidationDecision:
        if c.entity_id:
            return TaxonomyValidator().validate(c)
        try:
            import httpx

            self.calls += 1
            r = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": _PROMPT.format(
                        context=c.context_window(), span=c.raw, source=c.source
                    ),
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0, "seed": 7},
                },
                timeout=30.0,
            )
            raw = json.loads(r.json()["response"])
            d = str(raw.get("decision", "abstain")).lower()
            reason = str(raw.get("reason", ""))[:120]
        except Exception as e:
            return ValidationDecision(
                c.span_id(), ABSTAINED, self.validator_id, self.validator_version,
                "model_unavailable", f"fail-closed: {type(e).__name__}",
            )

        if d.startswith("accept"):
            return ValidationDecision(
                c.span_id(), ACCEPTED, self.validator_id, self.validator_version,
                "model_accept", reason, normalized_anchor=c.normalized,
            )
        if d.startswith("reject"):
            return ValidationDecision(
                c.span_id(), REJECTED, self.validator_id, self.validator_version,
                "model_reject", reason,
            )
        return ValidationDecision(
            c.span_id(), ABSTAINED, self.validator_id, self.validator_version,
            "model_abstain", reason,
        )


# ══════════════════════════════════════════════════════════════════════════════
# V3 — deterministic-first hybrid
# ══════════════════════════════════════════════════════════════════════════════

class HybridValidator:
    """Approach 3. The deterministic resource decides whatever it can; ONLY the uncertain band
    reaches the model.

    This is the architecture the rest of the system already uses — deterministic evidence
    first, model as the exception path — applied to anchors.
    """

    validator_id = "hybrid"

    def __init__(self) -> None:
        self.lexical = LexicalFrequencyValidator()
        self.model = LocalModelValidator()
        self.validator_version = f"{self.lexical.validator_version}+{self.model.validator_version}"
        self.escalations = 0

    def available(self) -> bool:
        return self.lexical.available()      # the model is optional; the resource is not

    def validate(self, c: AnchorCandidate) -> ValidationDecision:
        first = self.lexical.validate(c)
        if first.decision != ABSTAINED:
            return first
        if not self.model.available():
            return first                      # fail closed — keep the abstention
        self.escalations += 1
        d = self.model.validate(c)
        return ValidationDecision(
            d.span_id, d.decision, self.validator_id, self.validator_version,
            f"escalated:{d.reason_code}", d.evidence, d.normalized_anchor, d.signals,
        )
