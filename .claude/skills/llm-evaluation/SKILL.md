---
name: llm-evaluation
description: Generic LLM-evaluation methodology reference: classification metrics, human labeling and inter-rater agreement, LLM-as-judge, pairwise/A-B statistics, regression detection. For Signal Sports classification, feed, clustering, prompt or model evaluation, start with signal-quality-eval, which owns the workflow and cites this skill for method details.
---

# LLM Evaluation

## Signal Sports adaptation (read first; overrides the upstream text below where they differ)

Local adaptation of wshobson/agents `llm-evaluation` (MIT); provenance in [UPSTREAM.md](UPSTREAM.md).

This is a **methodology reference**. In Signal Sports, `signal-quality-eval` owns the evaluation
workflow (data, tools, holdout discipline, reporting) and `signal-real-data-qa` owns the per-change
feed gate. Read this skill for the method details they cite.

Local constraints that override the generic advice:
- **The product question is decisions, not text similarity.** BLEU, ROUGE, BERTScore and perplexity
  don't apply: the LLM proposes structured facts (sport, event type, entities, competitions) that
  pass deterministic guardrails (`docs/LLM_CLASSIFICATION.md`). Judge a model or prompt by facts
  accuracy against human labels, and by the resulting feed decisions against Guy's ratings ("judge
  by decisions, not by agreement").
- **Human labels are ground truth; LLM-as-judge is supporting evidence only** — never a label source
  for the gate, and never the tie-breaker against Guy's rating.
- **No new evaluation dependencies** (numpy, scipy, LangSmith, bert-score, transformers). The
  backend doesn't carry them, and `.claude/skills/signal-quality-eval/scripts/eval_stats.py` covers the needed
  statistics with the standard library.
- **No live provider calls or spend without a bound:** reuse `backend/scripts/llm_bakeoff.py`
  (dry run by default, call ceilings, response cache, read-only corpus).
- **Report sample size and an interval with every number.** With a few hundred rated rows, small
  differences are noise; census #2's owner review found about one notch of rating noise on
  borderline items.

---

*Upstream text follows (lightly edited; see UPSTREAM.md).*

Master comprehensive evaluation strategies for LLM applications, from automated metrics to human evaluation and A/B testing.

## When to Use This Skill

- Measuring LLM application performance systematically
- Comparing different models or prompts
- Detecting performance regressions before deployment
- Validating improvements from prompt changes
- Building confidence in production systems
- Establishing baselines and tracking progress over time
- Debugging unexpected model behavior

## Core Evaluation Types

### 1. Automated Metrics

Fast, repeatable, scalable evaluation using computed scores.

**Text Generation:**

- **BLEU**: N-gram overlap (translation)
- **ROUGE**: Recall-oriented (summarization)
- **METEOR**: Semantic similarity
- **BERTScore**: Embedding-based similarity
- **Perplexity**: Language model confidence

**Classification:**

- **Accuracy**: Percentage correct
- **Precision/Recall/F1**: Class-specific performance
- **Confusion Matrix**: Error patterns
- **AUC-ROC**: Ranking quality

**Retrieval (RAG):**

- **MRR**: Mean Reciprocal Rank
- **NDCG**: Normalized Discounted Cumulative Gain
- **Precision@K**: Relevant in top K
- **Recall@K**: Coverage in top K

### 2. Human Evaluation

Manual assessment for quality aspects difficult to automate.

**Dimensions:**

- **Accuracy**: Factual correctness
- **Coherence**: Logical flow
- **Relevance**: Answers the question
- **Fluency**: Natural language quality
- **Safety**: No harmful content
- **Helpfulness**: Useful to the user

### 3. LLM-as-Judge

Use stronger LLMs to evaluate weaker model outputs.

**Approaches:**

- **Pointwise**: Score individual responses
- **Pairwise**: Compare two responses
- **Reference-based**: Compare to gold standard
- **Reference-free**: Judge without ground truth

## Quick Start

```python
from dataclasses import dataclass
from typing import Callable
import numpy as np

@dataclass
class Metric:
    name: str
    fn: Callable

    @staticmethod
    def accuracy():
        return Metric("accuracy", calculate_accuracy)

    @staticmethod
    def bleu():
        return Metric("bleu", calculate_bleu)

    @staticmethod
    def bertscore():
        return Metric("bertscore", calculate_bertscore)

    @staticmethod
    def custom(name: str, fn: Callable):
        return Metric(name, fn)

class EvaluationSuite:
    def __init__(self, metrics: list[Metric]):
        self.metrics = metrics

    async def evaluate(self, model, test_cases: list[dict]) -> dict:
        results = {m.name: [] for m in self.metrics}

        for test in test_cases:
            prediction = await model.predict(test["input"])

            for metric in self.metrics:
                score = metric.fn(
                    prediction=prediction,
                    reference=test.get("expected"),
                    context=test.get("context")
                )
                results[metric.name].append(score)

        return {
            "metrics": {k: np.mean(v) for k, v in results.items()},
            "raw_scores": results
        }

# Usage
suite = EvaluationSuite([
    Metric.accuracy(),
    Metric.bleu(),
    Metric.bertscore(),
    Metric.custom("groundedness", check_groundedness)
])

test_cases = [
    {
        "input": "What is the capital of France?",
        "expected": "Paris",
        "context": "France is a country in Europe. Paris is its capital."
    },
]

results = await suite.evaluate(model=your_model, test_cases=test_cases)
```

## Detailed patterns and worked examples

Detailed pattern documentation lives in `references/details.md`. Read that file when the navigation tier above is insufficient.

