---
name: differential-review
description: "Security-focused differential review of Signal Sports changes that touch authentication, sessions, authorization, CSRF/CORS, secrets or tokens, untrusted input (source RSS/HTML/JSON, LLM output, request bodies), deploy and hosting boundaries (DEPLOY_ENV, deploy/, Dockerfiles, nginx), destructive dev routes, or CI workflows with permissions, secrets or publishing. Depth scales with risk; findings feed signal-pr-open/signal-pr-merge rather than a separate gate. NOT for docs-only, styling or test-only diffs."
---

# Differential Security Review

## Signal Sports adaptation (read first; overrides the upstream text below where they differ)

Adapted from Trail of Bits' `differential-review` under **CC BY-SA 4.0**. This directory, including
these adaptations, is distributed under that license (see [LICENSE](LICENSE) and
[UPSTREAM.md](UPSTREAM.md) for attribution and the list of changes).

**Risk triggers in this repo**

| Risk | Paths and changes |
|---|---|
| HIGH | `backend/app/services/auth_service.py`, `app/core/security_deps.py`, `app/core/csrf.py`, `app/api/routes_auth.py`, `routes_me.py`; any change to a route's `require_*` dependency or to the authz inventory (`tests/test_authz_inventory.py`, `test_authz_matrix.py`, `test_identity_isolation.py`); `app/core/deploy_mode.py`, `app/db/corpus_protection.py`, `app/api/routes_dev.py`; handling of secrets and tokens (`.env*`, Telegram token/chat id, LLM API keys, `deploy/*.env.example`); `deploy/` (compose, host scripts, sudoers, ssh, systemd), Dockerfiles, `frontend/nginx/`; `.github/workflows/*` changes to permissions, secrets, triggers or publish/deploy steps |
| MEDIUM | parsing untrusted input: source adapters (RSS/HTML/JSON), `ingestion/subtitle.py`, LLM output handling and prompt construction from article text (`app/classification/validation.py`, `merge.py`, `prompt.py`), request-body models; outbound requests built from data (source URLs, provider base URLs); new public routes; account lifecycle; rate limits |
| LOW / skip | docs-only, styling, tests-only, copy — normal review instead |

Classify by risk, not size: a one-line change to `require_admin` is HIGH; a 500-line Orbit CSS
change needs no security review.

**Local adjustments to the workflow below**
- **Findings feed the existing gates.** Record each finding in the `signal-pr-open` §5 /
  `signal-pr-merge` §4 shape (location, scenario, impact, remedy; blocker / improvement /
  follow-up). There is no separate security approval step.
- **Report output:** upstream's "always write a report file" becomes a concise security section in
  the PR's self-review evidence. Write a full markdown report to the session scratchpad (never the
  repo) only for HIGH-risk reviews or when Guy asks. This replaces the output locations in
  `reporting.md` ("File Naming and Location": working directory, Desktop, `~/.claude/...`).
- **No external skills or agents.** `audit-context-building`, `issue-writer` and the
  `differential-review:adversarial-modeler` agent are not installed here. Do the baseline and
  context work with Read, Grep and git, and apply [adversarial.md](adversarial.md) inline for
  HIGH-risk changes.
- **Patterns:** [patterns.md](patterns.md) leans toward smart contracts (reentrancy, overflow). Read
  [signal-security-patterns.md](signal-security-patterns.md) first for this stack.
- **Blast radius:** count callers with Grep over `backend/app` and `frontend/src`; for a route, also
  check its consumer in `frontend/src/api/client.js`.
- **Never** exercise a suspected exploit against the hosted host, real accounts, real tokens or the
  live corpus — reproduce with the test client and a temp DB. Report secret presence/absence, never
  values.
- **Don't `git checkout` the baseline** as [methodology.md](methodology.md) suggests: the PC worker
  runs from this checkout, and there may be uncommitted work. Read baseline files with
  `git show <base>:<path>`, compare with `git diff <base>...HEAD`, or add a separate worktree in
  the scratchpad (`git worktree add <scratch>/base <base>`) and remove it afterwards.
- State confidence and coverage limits. A clean security review is not proof that no
  vulnerability exists.

---

*Upstream text follows (lightly edited; see UPSTREAM.md).*

Security-focused code review for PRs, commits, and diffs.

## Core Principles

1. **Risk-First**: Focus on auth, crypto, value transfer, external calls
2. **Evidence-Based**: Every finding backed by git history, line numbers, attack scenarios
3. **Adaptive**: Scale to codebase size (SMALL/MEDIUM/LARGE)
4. **Honest**: Explicitly state coverage limits and confidence level
5. **Output-Driven**: Always record findings (in this repo: in the PR self-review; a full report file only for HIGH risk — see adaptation)

---

## Rationalizations (Do Not Skip)

| Rationalization | Why It's Wrong | Required Action |
|-----------------|----------------|-----------------|
| "Small PR, quick review" | Heartbleed was 2 lines | Classify by RISK, not size |
| "I know this codebase" | Familiarity breeds blind spots | Build explicit baseline context |
| "Git history takes too long" | History reveals regressions | Never skip Phase 1 |
| "Blast radius is obvious" | You'll miss transitive callers | Calculate quantitatively |
| "No tests = not my problem" | Missing tests = elevated risk rating | Flag in report, elevate severity |
| "Just a refactor, no security impact" | Refactors break invariants | Analyze as HIGH until proven LOW |
| "I'll explain verbally" | No artifact = findings lost | Record findings (PR self-review; report file for HIGH risk) |

---

## Quick Reference

### Codebase Size Strategy

| Codebase Size | Strategy | Approach |
|---------------|----------|----------|
| SMALL (<20 files) | DEEP | Read all deps, full git blame |
| MEDIUM (20-200) | FOCUSED | 1-hop deps, priority files |
| LARGE (200+) | SURGICAL | Critical paths only |

### Risk Level Triggers

| Risk Level | Triggers |
|------------|----------|
| HIGH | Auth, crypto, external calls, value transfer, validation removal |
| MEDIUM | Business logic, state changes, new public APIs |
| LOW | Comments, tests, UI, logging |

---

## Workflow Overview

```
Pre-Analysis → Phase 0: Triage → Phase 1: Code Analysis → Phase 2: Test Coverage
    ↓              ↓                    ↓                        ↓
Phase 3: Blast Radius → Phase 4: Deep Context → Phase 5: Adversarial → Phase 6: Report
```

---

## Decision Tree

**Starting a review?**

```
├─ Need detailed phase-by-phase methodology?
│  └─ Read: methodology.md
│     (Pre-Analysis + Phases 0-4: triage, code analysis, test coverage, blast radius)
│
├─ Analyzing HIGH RISK change?
│  └─ Read: adversarial.md
│     (Phase 5: Attacker modeling, exploit scenarios, exploitability rating)
│
├─ Writing the final report?
│  └─ Read: reporting.md
│     (Phase 6: Report structure, templates, formatting guidelines)
│
├─ Looking for specific vulnerability patterns?
│  └─ Read: patterns.md
│     (Regressions, reentrancy, access control, overflow, etc.)
│
└─ Quick triage only?
   └─ Use Quick Reference above, skip detailed docs
```

---

## Agents

Upstream ships a `differential-review:adversarial-modeler` agent. It is not installed in this
repo; apply [adversarial.md](adversarial.md) directly for Phase 5.

---

## Quality Checklist

Before delivering:

- [ ] All changed files analyzed
- [ ] Git blame on removed security code
- [ ] Blast radius calculated for HIGH risk
- [ ] Attack scenarios are concrete (not generic)
- [ ] Findings reference specific line numbers + commits
- [ ] Findings recorded (PR self-review; report file for HIGH risk)
- [ ] User notified with summary

---

## Integration

Upstream integrates with the `audit-context-building` and `issue-writer` skills. Neither is
installed here: build baseline context manually, and hand findings to `signal-pr-open` /
`signal-pr-merge`.

---

## Example Usage

### Quick Triage (Small PR)
```
Input: 5 file PR, 2 HIGH RISK files
Strategy: Use Quick Reference
1. Classify risk level per file (2 HIGH, 3 LOW)
2. Focus on 2 HIGH files only
3. Git blame removed code
4. Generate minimal report
Time: ~30 minutes
```

### Standard Review (Medium Codebase)
```
Input: 80 files, 12 HIGH RISK changes
Strategy: FOCUSED (see methodology.md)
1. Full workflow on HIGH RISK files
2. Surface scan on MEDIUM
3. Skip LOW risk files
4. Complete report with all sections
Time: ~3-4 hours
```

### Deep Audit (Large, Critical Change)
```
Input: 450 files, auth system rewrite
Strategy: SURGICAL + audit-context-building
1. Baseline context with audit-context-building
2. Deep analysis on auth changes only
3. Blast radius analysis
4. Adversarial modeling
5. Comprehensive report
Time: ~6-8 hours
```

---

## When NOT to Use This Skill

- **Greenfield code** (no baseline to compare)
- **Documentation-only changes** (no security impact)
- **Formatting/linting** (cosmetic changes)
- **User explicitly requests quick summary only** (they accept risk)

For these cases, use standard code review instead.

---

## Red Flags (Stop and Investigate)

**Immediate escalation triggers:**
- Removed code from "security", "CVE", or "fix" commits
- Access control modifiers removed (onlyOwner, internal → external)
- Validation removed without replacement
- External calls added without checks
- High blast radius (50+ callers) + HIGH risk change

These patterns require adversarial analysis even in quick triage.

---

## Tips for Best Results

**Do:**
- Start with git blame for removed code
- Calculate blast radius early to prioritize
- Generate concrete attack scenarios
- Reference specific line numbers and commits
- Be honest about coverage limitations
- Always record the findings (see adaptation for where)

**Don't:**
- Skip git history analysis
- Make generic findings without evidence
- Claim full analysis when time-limited
- Forget to check test coverage
- Miss high blast radius changes
- Leave findings only in chat when a PR or report should carry them

---

## Supporting Documentation

- **[methodology.md](methodology.md)** - Detailed phase-by-phase workflow (Phases 0-4)
- **[adversarial.md](adversarial.md)** - Attacker modeling and exploit scenarios (Phase 5)
- **[reporting.md](reporting.md)** - Report structure and formatting (Phase 6)
- **[patterns.md](patterns.md)** - Common vulnerability patterns reference

---

**For first-time users:** Start with [methodology.md](methodology.md) to understand the complete workflow.

**For experienced users:** Use this page's Quick Reference and Decision Tree to navigate directly to needed content.
