---
name: signal-doc-truth
description: Use when updating Signal Sports documentation after a behavior change, running a "truth sweep", deciding which doc is authoritative for a subsystem, or when doc claims conflict with code. Triggers on "update the docs", "truth sweep", "which doc covers X", or as the doc step other signal-* skills point here for. Encodes the docs/ topology — which files are living contracts, which are superseded, and the known drift patterns.
---

Docs in this repo are contracts agents build against, so a doc that restates old intent is
worse than no doc. The recurring failure mode is an agent trusting a stale doc over the code —
the topology below is what prevents it.

## The docs/ topology

**Living contracts (authoritative for their layer — keep these true):**

| Doc | Layer |
|---|---|
| `CURRENT_PROJECT_STATE.md` | Top-level truth; almost every behavior change touches it |
| `RELEVANCE_CONTRACT.md` | Umbrella: pipeline map + decision semantics (issue #35) |
| `TAXONOMY.md` | Registry rules + coverage audit table |
| `ARTICLE_FACTS.md` | Facts stage: evidence weights, triangle, trace shape |
| `RELEVANCE_VISIBILITY_CONTRACT.md` | Four-tier matching, reach allowlists, feed ceiling |
| `PREFERENCE_MODEL_V2.md` | ProfileV2, scorer layers, shadow checkpoint record |
| `CALIBRATION_V2.md` | Calibration dataset/inference/apply |
| `FEEDBACK_LEARNING.md` | Learning pipeline + safety invariants |
| `LLM_CLASSIFICATION.md` | Providers, gating, merge guardrails, run metrics (#31) |
| `RSS_INGESTION.md`, `RSS_QUALITY_GUARDRAILS.md`, `HEBREW_RSS_SOURCE.md` | Ingestion + classifier changelog |
| `FRONTEND_DESIGN_SYSTEM.md` | Tokens, product-vs-console split, RTL rules |
| `INTELLIGENCE_ROADMAP.md` | Initiative plan — milestone marked COMPLETE; §2 invariants still bind |
| `MOBILE_REMOTE_ACCESS.md`, `BACKEND_FOUNDATION.md` | Ops/foundation reference |
| `USER_PLATFORM.md` | User Platform milestone (auth/accounts/onboarding/ownership) — **approved architecture contract, not yet implemented**; design authority for that milestone's PRs. Until they land, "no auth" statements in other docs remain the current-state truth |
| `docs/fixtures/profile_parity.json` | Canonical legacy-profile snapshot — changes only with both seeds |

**Historical / superseded (never cite as current behavior):**

- `IMPLEMENTATION_AUDIT.md` — explicitly-marked snapshot predating the backend.
- `CALIBRATION_V0.md`, `CALIBRATION_APPLY.md` — superseded by `CALIBRATION_V2.md`; they
  describe a deleted frontend-only flow. Reimplementing anything from them is a regression.
- `TITLE_TRANSLATION.md` — post-MVP capability, module preserved but disabled.
- `PRODUCT_UNDERSTANDING.md` — product vision, still conceptually valid, not an implementation
  reference.
- `SQLITE_PERSISTENCE.md` — schema/seed/test-isolation sections are current, but its "What Is
  Still Not Persisted or Applied" table predates v2 (calibration inference, profile mutation,
  and feedback learning DO exist now). Trust the v2 layer docs over it on those points.

**Known drift patterns (check these, don't propagate them):**

- **Test counts.** `CURRENT_PROJECT_STATE.md` cites multiple conflicting suite counts and all
  go stale. When editing near one, either update it from an actual run
  (`pytest tests/ --collect-only -q` / `npm run test`) or replace the hard number with "see the
  suite output". Never copy a count from one doc section to another.
- **`CURRENT_PROJECT_STATE.md` §11/§13** (next steps / handoff prompt) predate the v2
  milestone in places; the roadmap pointer at the top of §11 is the corrective.
- Timestamps and "Last updated" lines — update them when materially editing a doc.

## Truth-sweep procedure (after a behavior change, or on request)

1. Diff-driven scope: from the actual change, list affected layers → their docs from the table
   above. `CURRENT_PROJECT_STATE.md` is almost always in scope (§3 architecture, §5 backend,
   §7 profiles/relevance, §8 classification).
2. For each doc: read the affected section AGAINST THE CODE, not against your memory of the
   change. Update behavior statements, invariants, tables, and endpoint lists.
3. Follow house style: dated changelog entries ("2026-07-08 — issue #NN …"), worked examples
   for semantics changes, explicit "what was deliberately NOT done" notes.
4. Cross-doc consistency: a contract stated in two docs (e.g. push discipline, evidence
   weights) must read identically — prefer stating it once and linking.
5. Re-read each updated section once more against reality — the specific failure this repo has
   seen is a doc updated to restate the *intent* rather than the shipped behavior.

## Done means

Every doc in the diff-driven scope updated or explicitly judged unaffected, no new hard-coded
counts/hashes introduced, superseded docs untouched (they are history, not to be "fixed"), and
`CURRENT_PROJECT_STATE.md` still reads as a correct cold-start orientation.
