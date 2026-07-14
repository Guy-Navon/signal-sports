# Cross-source fact consistency (#113) — corpus QA

**All QA ran against COPIES. The live corpus was never opened for write.**

## Root causes (all three oracle cases)

| # | Case | Root cause | Layer fixed |
|---|---|---|---|
| 1 | **Gal Raviv** — Israel youth women's Euro final. walla=`football`, ynet=`basketball` | **Missing deterministic evidence** + a **deterministic-evidence-first violation**. walla has no URL sport hint and no sport word in the title; the only evidence was the subtitle ("נבחרה ל**חמישיית הטורניר** … ב**אסיסטים**" — unmistakably basketball). The LLM guessed *football*, and **nothing could contradict it**: `merge.py` guardrail 2 only overrides the LLM when the LLM says *unknown*. If the rules resolved a sport and the LLM disagreed, **the LLM silently won.** | `sport_guards.py` (new) + `merge.py` **guardrail 1b** + `classifier._detect_sport` |
| 2 | **Yam Madar leaves Hapoel TLV** — ynet=`signing`, sport5=`news` | **Event-type validation gap.** `_RELEASE_COMPLETE` contained the **feminine** `נפרדה מ` but **not the masculine `נפרד מ`** — so the signing blocker missed *"ים מדר **נפרד** מהפועל ת״א"*, and a **farewell** article inherited `signing` from a subtitle that merely mentioned the already-completed transfer (*"אחרי ש**חתם** במכבי ת״א"*). A departure is not a signing. | `event_evidence.py` — departure forms added to the signing blocker |
| 3 | **McGregor UFC comeback** — walla=`unknown`/`match_result`, israel_hayom=`football`/`injury` | **Unsupported domain that should abstain** + **LLM inconsistency.** MMA is not modelled by the taxonomy. The LLM invented *football* — its own reason literally read *"Football match result between Conor McGregor and Max Holloway in UFC"*. | `sport_guards.py` + `merge.py` **guardrail 0** (abstain) |

## Classifier rules changed

1. **Guardrail 0 — unsupported domain abstains.** MMA/UFC/boxing ⇒ `sport="unknown"`. Runs first; **a source hint cannot resurrect it**.
2. **Guardrail 1b — committed sport vocabulary beats a contradicting LLM sport.** Only *unambiguous, single-sport* terms qualify. When **both** sports' vocabulary is present, `committed_sport()` returns `None` and the decision is left alone — real ambiguity, so abstention beats picking a side.
3. **Departure blockers.** `נפרד מ` / `נפרדו מ` / `עוזב את` / `פרידה מ` now block `signing`.
4. **Hint precedence corrected.** A source hint **fills a missing sport** but **never overrides committed contradictory evidence** — a football report filed under a basketball section is still football.

### A false positive I caught in my own guard
The first draft of the committed-football list included **`קרן`** (corner kick). It is also *fund / ray / horn*, **and it is a substring of `שקרן` ("liar")**. It turned a **Maccabiah bar-mitzvah story** and a **police-transcript story** into *football*. Removed, along with `נבדל` (also the ordinary word for "differs") and bare `מהקשת`. **A committed term must be unambiguous *and* substring-safe.**

## Effect (isolated #113 delta, applied to a copy)

Applying **only** the #113 rules to the stored facts — a full reclassification would re-roll every LLM verdict and change many articles for reasons unrelated to the change under test:

**8 articles changed.** Four are **pre-existing stale seed/mock rows** (`eurohoops`/`sport5` seeds whose stored events no longer satisfy current evidence rules) — *not rss, not caused by #113*. The **four genuine #113 corrections**:

| Article | Before | After |
|---|---|---|
| Gal Raviv (walla) | `football` / finals_result | **`basketball`** / finals_result |
| Yam Madar (ynet) | basketball / **`signing`** | basketball / **`news`** |
| McGregor (israel_hayom) ×2 | **`football`** / injury | **`unknown`** / injury |

## Oracle: fact disagreements 3 → 1

The one remaining disagreement is McGregor's **event** state (`match_result` vs `injury`). Its **sport conflict is resolved** — both are now `unknown`. The residual event split is an untracked-sport article where neither reading is provably right; **abstention is the correct outcome** and we do not force it.

## Clustering replay — matcher and config UNCHANGED

| | Before #113 | After #113 |
|---|---|---|
| Proposed clusters | **0** | **1** |
| Cards | 273 → 273 | 273 → **272** |
| Manually confirmed false positives | 0 | **0** |

**The one cluster, manually reviewed:**
`cluster_475745527e7506e4` · `finals_result` · basketball · Tier **B**, J=**0.44**, **2.53h** apart, carried by discriminative tokens (`גאות`, `הטורניר`, `כוכבת`, `הפנתיאון`, …)
- `[ynet_sport]` גל רביב: "רצינו שזה יסתיים אחרת, אבל יש לנו במה להיות גאות"
- `[walla_sport]` גל רביב: "רצינו שזה ייגמר אחרת, אבל יש לנו במה להיות גאות"

**Verdict: a genuine true positive.** Same event, two sources, same facts.

## Decision impact — intended corrections vs unintended drift

Across all **257 rss** articles:

| | Count | |
|---|---|---|
| **Guy** decision changes | **1** | **INTENDED fact correction** |
| **Deni** decision changes | **0** | — |
| Push counts | **Guy 5 / Deni 0 → Guy 5 / Deni 0** | **no push inflation** |

**The single change, justified:**
> `ים מדר נפרד מהפועל ת"א` — Guy: **`feed` → `hidden`**

That article was in Guy's feed **only because it was wrongly classified as a `signing`**. It is a farewell post, not a transfer. Correcting the fact removes an article that was being promoted by a false fact. **This is the system working, not drift.** There is **zero unintended drift**.

## Honest limitation

**One cluster is not enough to judge clustering precision.** Checkpoint 2's bar is *enough genuine cross-source overlap for a meaningful manual precision review*, and a single pair does not meet it. **No thresholds were lowered to manufacture more.** The tooling is complete and unchanged; the corpus needs to keep accumulating.
