# Week sample: development results (#256, #345), 2026-10-25

The owner's ratings of the seven-day sample ([WEEK_SAMPLE_2026-10.md](WEEK_SAMPLE_2026-10.md)) and
the focused #345 set, compared with what the system decides today, stage by stage. **This uses
the 70 `dev` rows only. The 35 `test` rows (the holdout) were not read.** See the holdout
section for what had already been exposed.

- Ratings: [`week_sample_2026-10_ratings.json`](week_sample_2026-10_ratings.json) (105 rows,
  including the holdout) and [`focused_345_2026-10_ratings.json`](focused_345_2026-10_ratings.json)
  (30). The owner rated blind on 2026-10-25. The files are as written by the rating page and are
  not edited.
- Analysis: [`week_sample_2026-10_dev_analysis.json`](week_sample_2026-10_dev_analysis.json),
  every row with its facts, gate, LLM outcome, decision and stage.
- Script: [`backend/scripts/analyze_week_sample.py`](../../backend/scripts/analyze_week_sample.py).
- Model answers: [`week_sample_responses/`](week_sample_responses/) (30 Groq responses). A re-run
  uses them and makes **no** model call (`llm_calls: live 0, cached 60` in the committed run).

## What was run

| | |
|---|---|
| Code | `main` at `74541ab` plus the analysis script |
| Pipeline | the production `_normalise` (rules, gate, LLM merge and guardrails, facts), then `score_article_v2` with Guy's live profile (read-only) |
| Gate | production gate, enabled |
| Runs | **rules**: LLM disabled. **groq20b**: `openai/gpt-oss-20b` on Groq, `json_schema`, reasoning `low`, 1,000 output tokens (the production configuration since 2026-10-25). **groq20b_guard_off**: the same, with the cross-sport entity guard switched off in memory, as a counterfactual |
| Prompt | system prompt sha256 `a77e2348…ca4d4` |

## Definitions

- **Wanted**: the owner rated `feed`, `high` or `push`.
- **Shown**: the system's decision is anything other than `hidden`, including `low_feed`. So a
  wanted article decided `low_feed` counts as shown.
- **Shown but rated hide**: the system shows it; the owner rated `hide`.
- **Exact tier**: the decision equals the rating on the five-step scale (hide / low / feed / high /
  push). **Below / above owner**: the decision is lower or higher on that scale.
- **System push / owner push**: rows the system decides `push`, and rows the owner rated `push`.

## Results

| Run | Set | n | Wanted shown | Shown | Shown but rated hide | Exact tier | Below owner | Above owner | System push / owner push |
|---|---|---|---|---|---|---|---|---|---|
| rules | dev | 70 | 21/24 (88%) | 23 | 0 | 53/70 (76%) | 13 | 4 | 0 / 0 |
| rules | focused | 30 | 7/11 (64%) | 8 | 0 | 21/30 (70%) | 6 | 3 | 0 / 1 |
| rules | regression | 7 | 0/7 (0%) | 0 | 0 | 0/7 | 7 | 0 | 0 / 0 |
| groq20b | dev | 70 | 21/24 (88%) | 23 | 0 | 53/70 (76%) | 13 | 4 | 0 / 0 |
| groq20b | focused | 30 | 7/11 (64%) | 8 | 0 | 21/30 (70%) | 6 | 3 | 0 / 1 |
| groq20b | regression | 7 | 0/7 (0%) | 0 | 0 | 0/7 | 7 | 0 | 0 / 0 |
| guard off | dev | 70 | 21/24 (88%) | 23 | 0 | 53/70 (76%) | 13 | 4 | 0 / 0 |
| guard off | focused | 30 | 10/11 (91%) | 16 | **5** | 18/30 (60%) | 4 | 8 | 0 / 1 |
| guard off | regression | 7 | 5/7 (71%) | 5 | 0 | 3/7 | 3 | 1 | 0 / 0 |

Rules and Groq give the same decisions on every row of all three sets.

**Owner rating (rows) × system decision (columns), groq20b**

dev (70):

| owner \ system | hidden | low_feed | feed | high_feed | push |
|---|---|---|---|---|---|
| hide | 42 | 0 | 0 | 0 | 0 |
| low | 2 | 0 | 1 | 1 | 0 |
| feed | 3 | 4 | 9 | 2 | 0 |
| high | 0 | 0 | 4 | 2 | 0 |
| push | 0 | 0 | 0 | 0 | 0 |

focused (30):

| owner \ system | hidden | low_feed | feed | high_feed | push |
|---|---|---|---|---|---|
| hide | 17 | 0 | 0 | 0 | 0 |
| low | 1 | 0 | 1 | 0 | 0 |
| feed | 3 | 0 | 4 | 2 | 0 |
| high | 0 | 0 | 1 | 0 | 0 |
| push | 1 | 0 | 0 | 0 | 0 |

regression (7): 6 rated `feed`, 1 rated `high`; all 7 decided `hidden`.

**High or push rated, assigned lower (groq20b):**

- dev, 4 rows, all `high` → `feed`: "דיווח: שחקן ה-NBA שמועמד להצטרף למכבי תל אביב", "התאמן במכבי
  תל אביב, רצה להישאר - אך יעזוב את ישראל", "הקאמבק של בן סימונס יחכה: קרע את גיד האכילס",
  "\"אז תנו לי לעזוב\": דורסי פתח במתקפה".
- focused: `push` → `hidden`, "ג'ייסון לוין בראיון בלעדי: המטרה - להחזיר את מכבי ת"א לגדולתה";
  `high` → `feed`, "מכבי תל אביב פנתה לשחקן מה-NBA - שסירב בגלל המלחמה".
- regression: `high` → `hidden`, "קולסון כיכב, 87:92 למכבי ת"א על אריס".

## LLM: technical failures, fallbacks, decisions (groq20b)

| Set | Gate did not call | Called, answer used | Fallback: low confidence | Technical failure |
|---|---|---|---|---|
| dev | 60 | 10 | 0 | 0 |
| focused | 17 | 13 | 0 | 0 |
| regression | 0 | 6 | 1 | 0 |

When the answers were first collected, one call got a 429 and its single retry succeeded, so no
row was left without an answer. "Answer used" means the merge took the LLM's proposal. The facts
stage can still drop part of it, which is what happens below.

## Where the misses come from (groq20b)

| Set | Facts dropped a cross-sport entity | No sport | No entity or competition | Facts resolved, profile hides |
|---|---|---|---|---|
| dev (3 misses) | 0 | 0 | 2 | 1 |
| focused (4) | 4 | 0 | 0 | 0 |
| regression (7) | 5 | 1 | 1 | 0 |

**The three dev misses**, each a different problem. They are follow-ups, outside #259:

1. "מי יכתיב את הקצב? הפועל תל אביב מוכנה לבשיקטאש" (rated feed): a basketball game, with
   Valencia named in the subtitle. **The model said football** and proposed `Hapoel Tel Aviv
   Football`; the final facts have no entity. Stage: sport identification (LLM error).
2. "פורטלנד הרבה יותר מסוכנת, יש לי רמה להגיע אליה העונה" (rated feed): Avdija is named only in
   the subtitle, and the title calls him "הישראלי של פורטלנד". Facts: basketball,
   `Portland Trail Blazers`, no competition, Deni not resolved. Hidden. Stage: entity (Deni) or
   competition (NBA from a team) missing, then the profile.
3. "איש השעה: המאמן שחייב להחליף את אריאל בית הלחמי בנבחרת" (rated feed): basketball, candidate
   event, **no entity**. The national team and its coach are not resolved. Stage: missing
   entity.

**The four focused misses** are all the cross-sport guard dropping a correct basketball entity:
Jason Levin's interview (push), Maccabi's games in Cyprus, Nadav Zilberstein's appointment, and
Dan Otoro at Hapoel Tel Aviv.

## What the cross-sport guard actually does (counterfactual)

With the guard off, in memory, on the same rows and the same Groq answers:

- **Gained**: focused 7 → 10 of 11 wanted, and regression 0 → 5 of 7 (the Aris win, the Super Cup
  grant, the Super Cup derby, "אין הצהרות", Madar). Jason Levin moves from hidden to feed.
- **Lost**: 5 focused articles the owner rated `hide` become `feed`. **All five are football
  Maccabi stories** that had been labelled basketball: "רק אנחנו אשמים: האכזבה והמסקנה במכבי ת"א
  אחרי סכנין", "צפו: דור תורג'מן כבש צמד", "בית הדין אישר את הסדרי הטיעון של מכבי ת"א והפועל
  ב"ש", "כולם שונאים את יוסי אבוקסיס", "עם 8 זרים בהרכב: נקבעה יריבת מכבי תל אביב בליגה
  האירופית".
- dev: no change.

So the guard costs real recall **and** prevents real false shows on these rows. This evidence
supports keeping the guard and adding real sport evidence, not relaxing it (#259).

## Corrections to earlier statements (2026-10-25 chat)

- **This is not a representative random week.** It is a random sample from seven **selected**
  days (three corpus days 10-12/13/14 and four archive days 10-19/21/22/24). On three of those days
  Ynet and Sport5 are missing.
- **Stored sport labels are not ground truth.** Earlier corpus cue counts were split by stored
  sport. Some stored "football" rows are basketball (for example "עדיין מושלמת: הפועל ת"א ניצחה
  78:80 את רומא").
- **"Zero football leakage" did not by itself show that the guard works.** That needed the
  counterfactual above, which shows it does on these rows.
- **"Not solvable by a cue" was too strong.** No cue was identified for the Cyprus article. That
  does not mean none exists.
- "Probably below about 12%" for the guard's share of misses in a random week was a rule-of-three
  bound on 0 of 24. It is a bound, not an estimate, and it holds for these seven days only.

## Holdout: what has been exposed

The 35 `test` rows were not read for this analysis. Before it, three things had already been seen:

1. While the sample was being built, the title and subtitle start of **2 holdout articles** were
   printed in a quality check. Their ratings and system decisions were not shown.
2. The **rating distribution of all 105 rows** (hide 64, low 7, feed 27, high 7, push 0) was
   printed when the ratings were checked. Together with the dev count, that gives the holdout's
   **aggregate: 10 wanted of 35**. No per-article holdout rating was seen.
3. Corpus-wide cue counts (names, a venue, score patterns, a show name, split by stored sport)
   were run over the whole corpus. That corpus includes the **17 corpus-origin holdout articles**.
   Counts only, without ratings.

**Status: the holdout is partially exposed, not clean.** Timeline:

| When (JST) | What | Holdout content seen? |
|---|---|---|
| 2026-10-25 morning, sample build | (1) 2 titles and subtitle starts printed by a quality check | 2 texts, no rating, no decision |
| 2026-10-25, rating check | (2) the 105-row distribution | only the aggregate, 10 wanted of 35 |
| 2026-10-25 evening and overnight | (3) corpus-wide cue counts (#352 analysis) over a corpus that held the 17 corpus-origin holdout rows | counts only, no text or rating |
| 2026-10-25/26, #353 and B3 runs | Rules-only reruns and clustering replays processed every corpus row, holdout included | none. Holdout ids were removed before any output was read (`*_nohold` snapshots). Changed clusters were checked for holdout ids before they were printed |

**Did it influence choices?**
- (1) **Cannot be fully ruled out.** The two texts were seen before #259's name list was drawn up.
  The final registered names come from the clubs' official 2026-27 rosters (basket.co.il,
  checked 2026-10-26). A name was kept only if it is mentioned in the corpus with the holdout
  excluded (`mine_people.py` drops the holdout ids), so the selection rule does not depend on the
  holdout.
- (2) The aggregate set no threshold or target.
- (3) The counts were used to *reject* cues (#352). No rule was added from them.
- Separately, #353's first name list was partly chosen from the dev regression and focused rows.
  Those gains are design evidence and are reported as such.

**Recommendation for the final evaluation.**
- Use these 35 rows **once**, after the candidate changes are frozen (#353 plus whatever else is
  approved), as a secondary check, labeled "partially exposed". Do not iterate on its result.
- With 10 wanted rows, one row is 10 points of recall, so it can only show a gross regression.
- The independent evidence should come from a **fresh holdout**: articles ingested after the
  freeze date, drawn by the same sampler, rated blind before anyone looks at system decisions,
  and sealed until one final run.
- Original ratings stay unchanged. New blind ratings go to new files.

Corpus-wide analyses exclude the holdout ids. Run with `--include-holdout` only at that final
check.

## Limits

- 24 wanted rows in dev. One row is about 4 points of recall.
- One rater, one pass. Census #2 found that about half of the borderline ratings change on a blind
  re-rate. Large gaps should be re-rated before they are acted on.
- The focused set was chosen by a mention rule and stratified by stored sport. Its rates say
  nothing about how often these cases occur.
- Archive rows came from sitemaps and article pages, not from the feed. Their text was checked to
  match the RSS text on two sources (see WEEK_SAMPLE_2026-10.md).
