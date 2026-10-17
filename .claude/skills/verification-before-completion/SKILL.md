---
name: verification-before-completion
description: Use immediately before claiming Signal Sports work is done, fixed, passing or ready - in a final message, commit, PR body, review verdict or handoff. Requires fresh evidence from the final changed state and reports every check as passed, failed, skipped or unavailable. Which checks a change needs is owned by signal-pr-finish; this skill governs how results are claimed.
---

# Verification Before Completion

## Signal Sports adaptation (read first; overrides the upstream text below where they differ)

Local adaptation of obra/superpowers `verification-before-completion`; provenance in [UPSTREAM.md](UPSTREAM.md).

**Ownership.** This skill governs *how* results are claimed. *Which* checks a substantive change
needs is owned by `signal-pr-finish` (suites, generated artifacts, contracts, docs), by
`signal-real-data-qa` for feed-affecting changes, and by `signal-quality-eval` for quality claims.
Do not build a second checklist here.

**Fresh, relevant, final.** Evidence must come from the final changed state. An edit after a run
invalidates that run for whatever the edit touched. Reuse earlier evidence only for code and
inputs that provably did not change, and say that you reused it.

**Report every check in exactly one state:**

| State | Meaning |
|---|---|
| passed | ran on the final state; output and exit code read |
| failed | ran and failed — quote the failure; never soften it |
| skipped | deliberately not run — say why it does not apply to this diff |
| unavailable | could not run here (missing tool, needs Guy's device, credentials or a live service) — say what it would need |

Never fold *skipped* or *unavailable* into *passed*. CI that has not finished is *pending*.

**Proportion.** A prose edit needs link/command verification, not the test suite; a CSS change
needs lint/build plus the visual steps in `signal-pr-finish`; a logic change needs its tests and
the suites. The iron law (no claim without evidence) always applies; the amount of evidence scales
with the claim.

**Repo specifics.** Take commands from `scripts/check.ps1`, `.github/workflows/checks.yml` and the
area skills; verify flags rather than recalling them. Never quote suite counts from docs — quote
what the run printed, and check the collected count did not drop versus the base branch. A green
suite or green CI shows what the tests cover; it does not prove the requirement is met. Map each
requirement to its evidence (the "Requirements" row below), and make sure the summary you give
matches the final code, not an earlier iteration.

---

*Upstream text follows (lightly edited; see UPSTREAM.md).*

## Overview

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags - STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)
```

**Build:**
```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion
- Moving to next task
- Delegating to agents

**Rule applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness
