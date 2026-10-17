# Signal Sports — Claude Code skills

Each skill's `SKILL.md` is authoritative for its own content. This index records **who owns which
decision**, so overlapping skills supply evidence to one owner instead of competing.

## Gates: one owner each

| Gate | Owner | Contributors (supply findings or evidence; no extra approval round) |
|---|---|---|
| Scope, implementation quality, final-diff self-review, opening a PR | `signal-pr-open` (§5 is the shared review standard, incl. D "domain checklists" and the final-diff questions) | `signal-pipeline-review`, `differential-review`, `web-design-guidelines`, `vercel-react-best-practices`, `async-python-patterns`, `python-testing-patterns`, `test-driven-development` |
| Which checks a change needs: suites, generated artifacts, contracts, docs | `signal-pr-finish` | `signal-real-data-qa`, `signal-quality-eval`, `webapp-testing`, `signal-doc-truth` |
| How results are claimed (passed / failed / skipped / unavailable) | `verification-before-completion` | — |
| Feed-decision regression on real data (N05 gate, decision diff, push discipline) | `signal-real-data-qa` | `signal-quality-eval` (intervals, held-out halves) |
| Review, merge readiness, merging | `signal-pr-merge` | `receiving-code-review` (existing comments), plus the `signal-pr-open` §5 contributors |

## Which skill for which situation

| Situation | Use | Not |
|---|---|---|
| Test/build/CI failure, traceback, misbehaving worker or stage | `systematic-debugging` | feed-quality complaints → `signal-feed-audit` |
| "Why is this article shown / hidden / pushed?" | `signal-feed-audit` | |
| What an article *is* (facts, LLM, evidence) | `signal-classification-change` | |
| What a user *sees* (scoring, profiles, learning) | `signal-relevance-change` | |
| Registry entities, competitions, aliases | `signal-taxonomy-change` | |
| New or changed source / adapter | `signal-source-onboarding` (+ `signal-pipeline-review` for the mechanics) | |
| Ingestion, clustering, notification, scheduling mechanics | `signal-pipeline-review` | rule correctness → classification/relevance skills |
| Security-sensitive diff | `differential-review` | docs-only, styling, tests-only |
| Measuring quality, model/prompt/threshold bake-offs | `signal-quality-eval` (method reference: `llm-evaluation`) | |
| Meaningful logic change or reproducible bug | `test-driven-development` | docs, styling, trivial config |
| Writing pytest tests | `python-testing-patterns` | |
| Async code, threads, timeouts, retries | `async-python-patterns` | converting sync code for style |
| Genuinely new backend component, or explicit scaffolding request | `fastapi-templates` | edits to existing routes |
| React components, hooks, data fetching, bundle | `vercel-react-best-practices` | Next.js/RSC/SSR — not used here |
| UI review: RTL, mobile, keyboard, states, long headlines | `web-design-guidelines` | |
| See the UI in a browser | `webapp-testing` (`npm run capture:orbit` first) | a new committed browser suite |
| Acting on review comments (Guy or bots) | `receiving-code-review` | |
| Handoff note | `signal-handoff` | |
| Docs after a behavior change | `signal-doc-truth` | |

Built-in commands such as `/code-review` and `/security-review` run only when invoked. Treat their
output like any reviewer's (`receiving-code-review`); they don't replace the owners above.

### Activation examples (hypothetical requests illustrating the conditional cases)

| Request or diff | Activates | Does not activate |
|---|---|---|
| Fix: Ynet items lose their subtitle (reproducible) | `systematic-debugging` → `test-driven-development` (regression test first) + `signal-source-onboarding` | `fastapi-templates` |
| Fix a typo in `docs/SCHEDULER.md` | `verification-before-completion` (links checked) | `test-driven-development`, `differential-review` |
| Tweak Orbit card spacing in CSS | `web-design-guidelines`, `webapp-testing` (`capture:orbit`) | `test-driven-development` (no failing test required) |
| Add `GET /api/results/standings` to the existing results router | `test-driven-development`; `differential-review` (new route needs an authz classification) | `fastapi-templates` (extends an existing router) |
| "Scaffold a new push-subscriptions service + router" (new capability) | `fastapi-templates` (mapped onto the existing layout), `differential-review`, `test-driven-development` | — |
| Change `require_admin` or `CSRF_ALLOWED_ORIGINS` | `differential-review` at HIGH depth | — |
| Bump `actions/checkout` in `checks.yml` | `signal-pr-merge` §7 dependency review; `differential-review` only if permissions, secrets or triggers change | `test-driven-development` |
| Change a clustering threshold | `signal-pipeline-review`, `signal-quality-eval` (Checkpoint-2 review on a copy) | — |
| Swap the classification model | `signal-quality-eval` (`llm_bakeoff.py`, bounded), `signal-real-data-qa` gate | `llm-evaluation` as the entry point (it's the method reference) |
| "Why was this Maccabi story hidden for Guy?" | `signal-feed-audit` | `systematic-debugging` |

## Precedence when instructions differ

1. Guy's instructions in the conversation.
2. `CLAUDE.md` and the contracts in `docs/` (`docs/CURRENT_PROJECT_STATE.md` has the doc map).
3. The `signal-*` skills.
4. The **Signal Sports adaptation** section at the top of each imported skill.
5. The upstream text in an imported skill.

## Imported skills

| Skill | Upstream | License |
|---|---|---|
| `systematic-debugging`, `verification-before-completion`, `receiving-code-review`, `test-driven-development` | [obra/superpowers](https://github.com/obra/superpowers) | MIT |
| `webapp-testing` | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 |
| `vercel-react-best-practices`, `web-design-guidelines` (+ pinned [web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines)) | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) | MIT |
| `async-python-patterns`, `python-testing-patterns`, `llm-evaluation`, `fastapi-templates` | [wshobson/agents](https://github.com/wshobson/agents) | MIT |
| `differential-review` | [trailofbits/skills](https://github.com/trailofbits/skills) | CC BY-SA 4.0 (the adapted directory stays under it) |

Each directory has an `UPSTREAM.md` with the exact commit, the tree hash of the imported path, the
license, the files included and excluded, and every local modification.

Deliberately **not** installed: the rest of the Superpowers framework, including its session hooks
and other skills; other Trail of Bits plugins; the `differential-review:adversarial-modeler` agent;
Playwright or any other new test dependency.

## Maintaining

- **Updating an imported skill:** fetch the new upstream commit, diff its path against the tree
  hash recorded in `UPSTREAM.md`, re-apply the adaptation, and update `UPSTREAM.md`. Never point a
  skill at a mutable remote URL at runtime (that's why `web-design-guidelines` vendors its rules).
- **Adding a skill:** give it one owner in the tables above, a description with explicit "NOT for"
  boundaries, and check that no existing skill already claims the same trigger.
- `signal-quality-eval/scripts/eval_stats.py selftest` checks the bundled statistics helper.
