# Hosted-LLM bake-off — 2026-10-25 (#262)

Groq `openai/gpt-oss-20b` and `openai/gpt-oss-120b` against Guy's census #2 ratings, through the
production `_normalise` with only the provider swapped (`backend/scripts/llm_bakeoff.py`, stage
`accuracy`, git `eb0a1e6`). Free Groq plan, no card. The corpus was opened read-only.

- Report: [`llm_bakeoff_2026-10-25.json`](llm_bakeoff_2026-10-25.json)
- Raw responses (262 per model):
  [`llm_bakeoff_responses/`](llm_bakeoff_responses/). Re-scoring after a pipeline change costs
  no API calls, as long as the prompt and model settings are unchanged:

  ```
  cd backend
  python scripts/llm_bakeoff.py --candidate groq-gpt-oss-20b --candidate groq-gpt-oss-120b \
      --stage accuracy --max-calls 262 --live --cache-dir ../docs/qa/llm_bakeoff_responses
  ```

  Verified: `live_calls 0`, `from_cache 262` for both models. `--live` is what builds the replay;
  a cache miss (a changed prompt) would call the API.

## Stages

1. Dry run: 804 rated rows, 262 sent to the LLM by the gate. All 262 were evaluated for each model.
2. Smoke: 20 calls per model. Every response came back within 2 s and none was truncated; one
   HTTP 400 per model.
3. Accuracy: 262 calls per model, no 429. Both models stayed under the 200K tokens/day free limit
   because most prompt tokens were served from Groq's prompt cache (see Tokens).

## Results on the 262 LLM rows

| | stored facts (Ollama) | rules only | gpt-oss-20b | gpt-oss-120b |
|---|---|---|---|---|
| exact tier match | 243 | 242 | 242 | 242 |
| wanted by Guy (feed+) | 7 | 7 | 7 | 7 |
| wanted and hidden | **7** | **7** | **7** | **7** |
| shown but rated hidden | 1 | 2 | 2 | 2 |
| decision changes vs stored | — | — | 2 (both further from Guy) | 2 (same rows) |

Both models make the same decisions as rules-only on every row. **This run cannot rank the
models on quality**: the facts stage removes the model's contribution where it matters (#345).
The model resolves the Maccabi Tel Aviv basketball stories correctly, for example the Super Cup
grant: basketball, `Maccabi Tel Aviv Basketball`, `title_win`, confidence 0.93. The rule
`cross_sport_entity_requires_explicit_sport` in `build_article_facts` then drops the entity,
because the sport came only from the LLM. Identical final decisions therefore do **not** show
that 20b and 120b are equally good.

The two decision changes against the stored facts are "מסי כבש את שערו ה-100 באינטר מיאמי" (rated
hidden, now feed) and "ריבאקינה זכתה באליפות ארה"ב הפתוחה" (rated low, now high). Ollama hid both,
and rules-only scores them the same way the candidates do. The other row shown but rated hidden,
"שבע המשאלות שלנו מתשפ"ז", is shown by every path.

## Reliability, latency, tokens

| | gpt-oss-20b | gpt-oss-120b |
|---|---|---|
| HTTP 400 `json_validate_failed` (empty `failed_generation`) | 1 | 3 |
| low-confidence fallback to rules | 36 | 30 |
| **rows falling back to rules** | **37 (14.1%)** | **33 (12.6%)** |
| truncated | 0 | 0 |
| latency p50 / p95 | 1.04 / 1.43 s | 1.27 / 1.57 s |
| prompt / cached prompt / completion tokens | 365,897 / 256,000 / 52,347 | 363,113 / 285,440 / 52,104 |
| counted toward rate limits (prompt − cached + completion) | ≈ 162K | ≈ 130K |
| estimated monthly cost at list price (checked 2026-10-13) | $0.17 | $0.33 |

The report's `validation_failure_rate` (0.0) counts invalid JSON in responses that arrived. The
HTTP 400s are counted separately under `failure_reasons.http_error`. The 400s hit specific titles
in both models; their cause is not established. The bake-off already ran with a 1,000-token
output cap, so a too-small cap is not a sufficient explanation.

The prompt-cache share comes from a dense run. Production calls are spread across the day and may
hit the cache less often. Without the cache: about 45 calls/day × about 1,520 tokens ≈ 68K
tokens/day, against the free plan's 200K/day and 8K/minute. A cycle with more than about five
LLM calls in one minute would get 429s; the provider then pauses, and those articles fall back
to rules.

## What this does and does not show

- Both models answer reliably and quickly on this hardware-independent path. **No timeouts were
  observed.** Ollama's production timeouts (about 70% of calls on 2026-10-11..14, at a 30 s
  timeout) are a separate measurement.
- Decision quality versus Ollama is unchanged on these rows, and so is decision quality between
  20b and 120b. Both comparisons are confounded by #345.

## Decision (owner, 2026-10-25)

Production configured to `openai/gpt-oss-20b` as an **interim operational choice**: it takes the
model off the PC and costs least. This is not a finding that it matches 120b in quality. Re-run
the comparison from the saved responses after #345.
