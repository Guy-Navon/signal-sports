# Clustering, dedup and push-suppression check before the person registry (#259)

**Date:** 2026-10-25. **Scope:** measurement only. No classification, taxonomy, clustering
or notification code was changed. **Corpus:** a WAL-safe copy (`scripts/backup_db.py`, sha256
`46b95229…cbc`, integrity and foreign keys ok) of the live DB taken 2026-10-25 at about 06:27
UTC: 3,209 RSS articles published 2026-07-10 → 2026-10-25, 68 persisted clusters (153
members), 21 notification events (14 sent, 7 watermark-suppressed). The live DB was only read
by the backup API. All replays ran on further copies in the session scratchpad. The 35 sealed
holdout article ids (17 of them are in this copy) were excluded from every listing and judged
sample, and 2 persisted clusters that contain one were left out of the review. Telegram stayed
off and no send path ran.

**The quality judgments below are mine, made from titles and subtitles. They are not ground
truth or owner ratings.** Every count comes from a command run on the copy in this session.

## 1. Summary

| Question | Result |
|---|---|
| Regression suites (clustering, anchors, claims, intra-source, dedup, collapse, notifications) | **448 passed, 1 skipped** (the skip needs a live corpus inside the worktree) |
| Does current `main` reproduce the persisted clusters? | **Yes, exactly.** The replay gives 68 clusters, 0 created, changed or removed |
| Persisted clusters reviewed | 66 of 68 (all non-holdout) |
| Judged correct / borderline / **wrong or impure** | 39 / 6 / **21** |
| Exact copies of one article under two URLs | 3 pairs, **0 collapsed** |
| Seeded sample of 30 near-miss cross-source pairs: same story, left split | 7 clear + 4 borderline |
| **PR #353** (the real #259 branch) before/after, same copy | **0 cluster differences** (68 = 68 clusters, 154 = 154 members). 0 edge decisions changed over 52,187 re-evaluated pairs. 356 pairs moved from "below threshold" to a cross-sport hard reject |

The headline is not about the person registry. **Current clustering over-merges far more than
the July activation record says (0 over-merges).** 14 of the 21 wrong or impure clusters formed
under rule version 1 after activation and 7 under rule version 2, and the current code
reproduces all of them. The evidence classes behind them were never in the #126 review:
canonical **team** ids and inflected Hebrew **verbs** used as tier-N "names". PR #353 itself
changes no cluster on this corpus. It does add `player:` anchors to the same tier-N path, so
the latent risk is real but was not triggered here (§5).

## 2. Which inputs a person entity would change (code trace)

The change under review registers Israeli basketball people in `app/taxonomy/entities.py`, so a
name yields sport evidence, team evidence and a new entity id. Nothing in the three subsystems
reads the taxonomy directly except anchor generation; everything else reads stored article
facts.

| Consumer | Reads | Effect of a new person entity |
|---|---|---|
| URL dedup `app/ingestion/dedup.py:17-26` | the exact URL string only | **none** |
| Tier selection `app/clustering/matcher.py:100-118` | `sport`, `entity_ids`, `primary_competition` | `unknown` sport → basketball moves a pair out of Tier C (jaccard 0.35, 2 rare tokens) into A or B; a shared person or implied team id selects **Tier A** (0.30, 1 rare token). **A looser bar, so merges are possible.** Measured for PR #353 in §5: 28 pairs changed tier, none near the floor |
| Cross-sport hard reject `matcher.py:84-97`, coherence `coherence.py:138-141` | `sport` | a newly proven basketball article now hard-rejects a proven football one. Can only remove merges |
| Tier-N anchor rescue `matcher.py:208-242`, `anchor_enrichment.py:140-153` | persisted `story_anchors` | `anchors.py:262-273` resolves the title and subtitle with the taxonomy and emits a canonical candidate for every resolved entity: role `unknown` (story-identifying) for players, executives **and teams**, `role_holder` for coaches. The validator accepts any canonical id (`anchor_validators.py:136-137`) and `_match_keys` matches it verbatim (`anchor_enrichment.py:39-40`). **A registered player becomes a `player:` anchor that rescues pairs below every jaccard floor in the nine person-centric states.** A coach does not |
| Anchor population `anchor_enrichment.py:156-177` | `sport` | which peers corroborate lone surname mentions changes at enrichment time |
| Anchor freshness `ingest_stage.py:191-193`, `scripts/backfill_story_anchors.py` | `anchor_validator_version` | a registry change does **not** bump the validator version, so stored rows keep their old anchors. Only new articles get the canonical anchor. Old and new rows still meet on surface forms such as `מדר` |
| Representative ladder `coherence.py:48-71`, feed collapse `services/cluster_collapse.py:40-63` | `entity_ids` non-empty, `primary_competition` | a member that gains an entity can become the displayed card. Cosmetic |
| Live re-clustering `ingest_stage.py:94-142, 218-259` | every row in the ±48 h window | each cycle recomputes the whole window from stored facts, so a backfill of facts would re-cluster old stories the next time a neighbour arrives |
| Push identity `notifications/outbox.py:129-226`, `planner.py:63-139` | article ids of the cluster's members | no entity input. Indirectly, **a wrong merge with an already-notified story suppresses a later, different push for good** (lineage rows are never removed), and **a split pushes one story twice** |

Classifier side (`app/ingestion/classifier.py:483-499` on `main`): a coach or executive emits
only the team, and a player emits only the player. PR #353 extends the team-only rule to
players marked `implies_team`, and adds `_club_person_sport`, which lets a named club person
prove the sport. So each mention of a registered person adds a `team:` entity and can turn
`unknown` into basketball. That feeds tier selection, the cross-sport reject and the
representative ladder. Because `anchors.py` resolves the taxonomy directly, a registered player
also adds a canonical `player:` anchor next to the lexical one.

## 3. Method

1. Ran 22 regression files with the backend venv: anchors (#137, #141, #135/#136), claims (#142),
   clustering acceptance, adversarial, backfill, fixtures, ingestion, matcher and persistence,
   intra-source (#123), feed collapse and dedup (#121, #125), URL dedup, the article-id golden
   test, and notifications (#151–#153, #156).
2. Copied the corpus with `scripts/backup_db.py`. Reviewed every persisted cluster from its
   members' titles and subtitles, plus its stored edges, tiers and evidence.
3. Enumerated cross-source pairs within 24 h that are not in the same cluster and either have a
   title jaccard ≥ 0.30 or share a title-borne name anchor with jaccard ≥ 0.12. That gave 635
   pairs, 629 without holdout articles. I re-ran `match_pair` on each with a ±48 h document-frequency window, an
   approximation of the live window, and judged a seeded sample of 30 (`random.Random(20261025)`).
4. Looked for exact copies: identical normalized titles from one source, and the same
   per-publisher article key (ynet slug, sport5 `docID`, walla item, Israel Hayom article id)
   under different URLs.
5. **Drift check.** Replayed the existing `scripts/backfill_clusters.py --apply
   --rule-version 2`, which replays the live stage article by article, on a copy with `main`
   code. Then diffed the partition against the persisted one by membership.
6. **Real before/after for PR #353** (`origin/feat/basketball-people-259` at `6091de3`,
   exported with `git archive`; the clustering code is unchanged from `main`).
   - *Facts:* an isolated delta (`docs/CLUSTERING.md` §12.2), not a full reclassification.
     `scripts/corpus_rerun_diff.py snapshot` ran rules-only over the copy with `main` code and
     with PR code. Only the fields where the two rules runs differ were applied to the PR copy:
     entity ids were added or removed, and `sport`, event and competition were changed only
     where the stored value equals `main`'s rules value. Where the LLM had stored something
     else, the stored value was kept.
   - *Anchors:* `scripts/backfill_story_anchors.py --apply --force` on both copies, each with its
     own code.
   - *Clusters:* `backfill_clusters.py` on both copies, each with its own code, then a partition
     diff. Separately, every pair within 48 h that touches a changed article was re-evaluated
     with the matcher on both fact sets.

   An earlier home-made simulation (10 hypothetical people injected by hand) was stopped
   unfinished once the real branch existed. None of its results are used.
7. Reproduced each wrong-merge class with pure `cluster_articles()` calls, without a DB.

## 4. Current quality

### 4.1 Persisted clusters: 66 reviewed

Sizes: 54 pairs, 11 triples and 3 quads (all 68). Edge tiers: N 91, C 8, A 4, I 3, B 1, so
**tier-N anchor evidence carries 91 of the 107 stored edges**. Rule version 1 formed 14 of the 21 wrong
or impure clusters and rule version 2 formed 7, the newest on 2026-10-25. The defect is live.

| Verdict | n | Root cause |
|---|---|---|
| Correct | 39 | e.g. Madar ×4, Hankins ×4, Satoransky ×4, Sinner ×3, Noam Yaakov ×3, Lundberg ×3 |
| Borderline | 6 | same press event or saga, different angle: `1054a01e`, `199f9bff`, `71e771ed`, `9b8d2c8c`, `f0b665ab`, `f2bd132a` |
| **Wrong or impure** | **21** | below |

Wrong or impure, by evidence class:

- **Canonical team id as the only tier-N evidence: 7.** 18 stored N edges rest only on `team:`
  ids.
  - `cluster_3775a5a141be673c`: three unrelated Maccabi Haifa items (season-ticket prices,
    compensating Haziza, talks with a Wolves centre-back).
  - `cluster_f242a8ef970160f1`: Red Star demands €250k for Glazer, and separately the
    Brazilian centre-back Tsunami agrees terms.
  - `cluster_d99572cb93acc751`: two different Netanya deals.
  - `cluster_59f85f38f2c24f23`: Novakovic agrees terms, plus a Glazer member.
  - `cluster_45639593bcb6e690`: Harmesh signs in Austria; Batubinsika signs in Romania.
  - `cluster_6be1b991081d0c5d`: Davida doubtful vs Beitar; Haifa's Champions League heroes four
    years on.
  - `cluster_60ceeacea385ac47`: two different career interviews.

  Three team-only clusters happen to be right (`5ed9767e`, `388805ed`, `c01e99b7`).
- **Ordinary Hebrew word validated as a name: 8.** The V1 validator accepts rare *inflections*.
  `ייעדר` / `ייעדרו` ("will miss") and `שינחת` ("will land") return `accepted
  rare_in_language`, and so does `העתודה` ("the youth team"). See `repro.py` in §7.
  - `cluster_866ab6e17134ce0f`: Kompany in hospital, and Barcelona missing 5 for the Clásico.
  - `cluster_52847c99b790fc81`: Capdevila's visa, and the sprinter Afriyie.
  - `cluster_4e81ade140d1c923`, `cluster_d534311c5830ff4e`: unrelated injury notes.
  - `cluster_0ad709cbd9e00565`: two different football signings.
  - `cluster_7fefb52f2ccdfde9`: two different youth-team players.
  - `cluster_da532362cda8cfad`: two different FIFA stories, joined by the fragment `פיפ`.
  - `cluster_398d8bec93908c7b`: Sesko's interview and Shua's message, joined only by the
    transliteration key `translit:סטר` at jaccard 0.00.
- **Canonical player id: 1.** `cluster_bd22bd306010dc08` merges "Philadelphia courting LeBron"
  with "a pickleball star says Portland is trying to sign LeBron" on `player:lebron_james`.
  **This is the anchor class PR #353 (#259) adds for Israeli players.**
- **Shared surname, different development: 4.**
  - `cluster_0804ae9d20059200`: Kangwa agrees elsewhere, and Beer Sheva's training news.
  - `cluster_3b146376b35f3b10`: the Haziza release, and a radio segment.
  - `cluster_07c239f0a49fc289`: the Gderani extension, plus an unrelated Beitar player in
    crisis.
  - `cluster_d5ab78c94f793c29`: "Jerusalem wants him" merged with "Albi signed at HaEmek", a
    material update hidden.
- **Intra-source live template: 1.** `cluster_77b2333cbecb0388` (tier I, ynet) merges `דקה 5:
  מכבי פ"ת - הפועל י-ם 0:0` with `דקה 4: בני סכנין - הפועל ר"ג 0:0`. These are two different
  matches. `דקה N:` is not an in-play marker (`event_states.py:34-47`), and the shared
  "ליגת העל, מחזור 5" plus `במומנטום` clears the title and evidence bars.

**Wrong merges also cause splits.** Under the one-member-per-source rule
(`coherence.py:214-219`), the first member from a source holds that source's slot. 13
cross-source pairs that `match_pair` accepts today are not co-clustered:

- **Slot held by a member of a wrong cluster, true duplicate left out (4 pairs):**
  - the second LeBron/Portland report, because Israel Hayom's sits in `bd22bd30`;
  - the second Tsunami report, because walla's slot is held by the Glazer item in `f242a8ef`;
  - 2 Lonwijk "talks" pairs, because ynet's item sits in `3775a5a1`.
- **Slot held by a legitimate member (6 pairs):** Dasa ×2, Gderani injury ×2, the Gderani
  signing and Konchar.
- **Not a duplicate at all (1):** the two Kiouf items, which the matcher would wrongly accept.
- **Not investigated (2):** the Novakovic and Lonwijk signing pairs.

### 4.2 Same-story splits: seeded sample of 30 near-miss pairs

The near-miss rejection reasons over all 629 pairs: event state differs 257, below the jaccard
floor 237, not a clusterable state 60, in play 40, cross-sport 13, matcher would accept 13,
outside the window 5, claim reversal 4.

In the sample, **7 are the same story left split**, 4 are borderline, and 19 are genuinely
different stories (abstention correct). The 7 clear splits:

| Pair | Cause |
|---|---|
| Whaley signs at Ness Ziona (sport5 basketball / walla **football**) | classification: cross-sport hard reject |
| Messi cries and Scaloni speaks after the final (`finals_result` / `news`) | classification: event state differs |
| Motley leaves Hapoel TLV (`news` / `release`) | classification: event state differs |
| Eliniv Barda: "four turbulent days" (ynet / walla `unknown` sport) | **unknown sport → Tier C**, jaccard 0.34 < 0.35 |
| Halaili sale not off the table (ynet / walla) | claim gate false positive: `לא ירדה מהפרק` ("did **not** come off the table") matches the reversal marker `ירדה מהפרק` (`claims.py:54`). Safe direction; this `news` pair would fail Tier C anyway |
| Draymond Green on Avdija (two interviews) | by design: `interview` is never clustered |
| Lonwijk signs at Haifa (ynet / walla) | the matcher accepts it (tier N); why it is not clustered was not investigated |

Classification differences cause most splits, not matcher strictness. That is consistent with
`docs/CLUSTERING.md` §5.

### 4.3 Exact copies (one article under two URLs) versus different publishers

URL dedup keys on the exact URL string. **3 pairs** are the same publisher article reached
under two section paths. **0 were collapsed**, and they show as two cards:

| Copy pair | State | Why clustering missed it |
|---|---|---|
| ynet `…/sport/article/syj8d3dnzg` and `…/sport/worldcup2026/article/syj8d3dnzg` (identical title, same second) | `news` | intra-source excludes `news` (`docs/CLUSTERING.md` §7.5) |
| ynet `hy6rmptnzg`, same two paths (titles differ by one word) | `news` | same |
| sport5 `docID=553851` under `FolderID=274` and `FolderID=11840` (Rodi agrees terms with Hapoel Jerusalem) | `negotiation` | the `ingest_fallback` timestamps are 9.9 h apart, beyond the 6 h intra-source window |

Different publishers covering one event is what clustering exists for: 149 of the 153 clustered
articles sit in 66 cross-source clusters. The other 2 clusters are same-source (tier I): one is
a genuine republish (Noskova), and one is the wrong live-snapshot merge in §4.1. Same-source
URL copies are not protected at all. A push-tier copy pair would plan **two** events, because
lineage is per article id (`outbox.py:165-169`).

### 4.4 Repeated-notification suppression

The stored lineage holds 24 member rows over 21 events: 23 `creation` and 1 `expansion`. The
expansion attached a member to an already-sent event, and that event stayed one message. The
notification unit suites pass. The real duplicate-push case is upstream, in clustering:

- The Lundberg agreement was pushed twice, by sport5 (event created 07-22 22:42) and by ynet
  (07-23 04:15). Both events are `sent`, and both had no cluster at creation.
- The two articles are now together in `cluster_154662894917b642`, but that cluster formed only
  on 2026-09-11, under rule version 2.
- No member of the 21 wrong or impure clusters appears in the notification lineage, so none of
  them has suppressed a push yet.

## 5. PR #353 (#259): real before/after on the copy

**What the branch changes in the inputs:**

- *Facts.* The rules-only snapshots differ on 57 of 3,218 rows. Applied to stored facts:
  - entity ids changed on 53 rows (mostly `team:maccabi_tlv_bb` or `team:hapoel_tlv_bb`
    added);
  - `sport` went from `unknown` to basketball on 17;
  - 10 sport differences were left as stored, because the LLM had a different value. At least
    4 of them are `football` on a Hapoel or Maccabi Tel Aviv basketball story; 1 of the 10 is a
    holdout row and was not inspected.
  - By event type the rows split as: news 32, negotiation 6, match_result 5, injury 4,
    release 3, interview 3, signing 2, schedule 1.
- *Anchors.* 142 articles gained 175 `player:` anchors and 1 `exec:` anchor; none lost one.
  46 of those articles are in person-centric states.

**Effect:**

| Measure (both arms re-enriched, §6) | `main` | PR #353 |
|---|---|---|
| Clusters after replay | 68 | 68, **identical membership** |
| Clustered articles | 154 | 154 |
| 52,187 re-evaluated pairs touching a changed article | — | **0 edges accepted or rejected differently** |
| Replay near-miss `below_threshold` | 49,383 | 49,027 |
| Replay near-miss `cross_sport` | 21,709 | 22,065 (**+356**) |

The 399 pairs whose matcher outcome *text* changed break down as follows:

- **356** moved from "below the jaccard floor" to a **cross-sport hard reject**, because an
  `unknown` article became basketball against a football one. This is protective.
- **28** changed tier but stay far below the floor; the highest jaccard among them is 0.05,
  against floors of 0.30 and 0.35. Of the 23 non-holdout ones, 18 were Tier C, 4 Tier B and 1
  Tier A on `main`; all are Tier A or B on the PR.
- **15** already-accepted edges gained a canonical player id next to the lexical anchor, with the
  same outcome: Madar 9, Oturu 3, Lundberg 3. For example, the Israel Hayom/ynet farewell pair
  in `cluster_747be13e1ccfc1c3` goes from `EDGE N translit:מדר,מדר` to
  `EDGE N player:yam_madar,translit:מדר,מדר`.

**Why there is no effect here (my reading of the evidence above):** every canonical-anchor
change on an accepted edge (Madar, Oturu, Lundberg) duplicated a validated surface anchor the
edge already had. Most
fact changes are on `news` rows, which always use Tier C and are excluded from tier N. The tier
changes that did happen are far below the floors.

**Latent risk (not observed, but structural).** Bug B3 below is the same mechanism with
`player:lebron_james`: one shared canonical person id is sufficient tier-N evidence for two
*different* stories about that person, inside a 24 h person-centric window. PR #353 makes that
reachable for 22 more players and Itoudis, including full-name-only aliases such as `בר טימור`
or `תומר גינת`. Whether the lexical validator already yields an anchor for those names was
**not measured**. Where it does not, the canonical id is new evidence, and new merges become
possible.

## 6. Side finding: anchor re-enrichment alone changes clusters

Both PR-comparison copies were re-enriched with `--force`. That upgrades the 1,427 stored rows
still at validator `wordfreq-3.1.1` to `wordfreq-3.1.1+subject-v2`. With `main` code, the effect
against the persisted partition was **2 clusters removed, 2 created and 1 changed** (the replay
report), with 154 members instead of 153. By my judgment it was a net loss:

- **Removed:** `cluster_45639593bcb6e690` (wrong) and `cluster_f2bd132a173ab6a1` (borderline).
- **Changed:** `cluster_7fefb52f2ccdfde9` (already wrong) grew to three different Galil Elyon
  players (Sela, Sahar, Belga) on `team:hapoel_galil_elyon`.
- **Created:**
  - **wrong:** `cluster_05fc1d3bdd7769c9`, Belga and Kemp, two different signings, on the same
    team id;
  - **wrong:** `cluster_5e87077072eb9a39`, "Maccabi's preparations for the Super Cup" with a
    column on Bryant and Madar, on the lexical anchor `מדר`.

**So do not run `backfill_story_anchors.py --force` on the live corpus as part of the #259
rollout** until B1 is fixed. Under PR #353 the canonical anchors only reach new articles anyway
(§2, anchor freshness).

## 7. Bugs found (not fixed)

B1–B4 reproduce with the current `main` code, purely, in `cluster_articles()` and without a
DB. The script was `repro.py` in the session scratchpad, and its inputs are below. I found B5
by reading `claims.py`, using the corpus pair in §4.2. B6 comes from the corpus pairs in §4.3.

| # | Bug | Minimal case | Proposed fix (needs a `RULE_VERSION` bump, re-enrichment on a copy and a §12.2 review) |
|---|---|---|---|
| B1 | **Canonical team anchors are story-identifying.** `anchors.py:269` gives every non-coach canonical entity role `unknown`, so `team:*` ids become tier-N subject evidence. The module's own reasoning (`anchors.py:70-76`: "every Maccabi story shares the team") already excludes competitions for this reason | two `negotiation` football titles, 23 h apart: "הכוכב האדום דורשת ממכבי חיפה 250 אלף יורו עבור עומרי גלזר" / "חיזוק להגנה: הבלם הברזילאי צונאמי סיכם במכבי חיפה" → `EDGE tier=N evidence=('team:maccabi_haifa_fc',)` | treat canonical `team:` (like `comp:`) as non-identifying in `generate_candidates` or `shared_subject_anchors`. Expected cost: the 3 correct team-only clusters split (cosmetic) |
| B2 | **The V1 lexical validator accepts inflected ordinary words.** wordfreq rates the inflection, not the lemma | "בבאיירן מעדכנים: קומפאני יציב, אך ייעדר מספר שבועות" / "מכה לברצלונה: 5 שחקנים בחוץ לקלאסיקו" (subtitle "…ייעדרו גם הם"), `injury` → `EDGE tier=N evidence=('translit:יעדר',) jaccard=0.0` | also reject a span when a prefix- or suffix-stripped form (future-tense י/ת/נ/א, ש/ה, plural ו/ים/ות) is an ordinary word. Separately, require jaccard > 0, or one shared lexical token, before a translit-only key may rescue a pair |
| B3 | **A canonical player id alone rescues different stories about the same person** in a 24 h person-centric window | "פילדלפיה מגבירה את החיזור אחרי לברון ג'יימס" / "אני יודעת שפורטלנד מנסה להחתים את לברון ג'יימס", `signing` → `EDGE tier=N` on `player:lebron_james` | treat a canonical person anchor as necessary, not sufficient. This is `docs/CLUSTERING.md`'s own rule: "shared identity without shared event semantics must not merge". Require an agreeing club, or a second shared discriminative token. Recommended before the registry grows beyond PR #353 |
| B4 | **The intra-source stage merges live-minute snapshots of different matches** | ynet "דקה 5: מכבי פ"ת - הפועל י-ם 0:0" / "דקה 4: בני סכנין - הפועל ר"ג 0:0" with a shared "ליגת העל, מחזור 5 … להמשיך במומנטום" subtitle → `EDGE tier=I` | add `דקה \d+:` (and a `0:0`-style live score headline) to the in-play markers. Optionally refuse intra-source pairs whose titles name different team entities |
| B5 (minor) | the reversal marker matches its own negation | `לא ירדה מהפרק` | add a negation guard (`לא` immediately before the marker) alongside the conditional guard |
| B6 (dedup) | URL variants of one publisher article become two articles and two possible pushes | the 3 pairs in §4.3 | in addition to the stored URL (do **not** change `article_id_from_url`, which would re-key every article), skip on a per-source canonical article key: the ynet slug, sport5 `docID`, walla item id, Israel Hayom article id |

## 8. Limitations

- **Judgments are mine, from titles and subtitles.** Borderline cases are listed separately. A
  second rater would move a few verdicts. An owner review of the 21 is the next step if these
  numbers are to gate anything.
- The near-miss sample is 30 of 629 pairs, and the candidate filter only finds pairs with some
  lexical or anchor overlap. A split with no shared token at all is invisible to it, so the
  split rate is a lower bound.
- `match_pair` re-runs used a ±48 h document-frequency window, an approximation of the live
  scope. The replay uses the real stage.
- The PR #353 comparison uses an **isolated rules delta**. It does not model how the LLM gate
  would behave once a name supplies sport evidence (`docs/CLUSTERING.md` §12.2 forbids a full
  LLM reclassification for QA). 10 rows where the stored LLM sport disagreed were left
  unchanged. Both copies were re-enriched with `--force` to give the branch's anchors a fair
  baseline; §6 shows that re-enrichment itself moves 3 clusters, identically in both arms.
- The corpus is a snapshot. Telegram is off, so the push path was checked through code, unit
  suites and stored lineage only. No push was simulated.

## 9. Risk verdict for the person registry

- **PR #353 as written: low risk to dedup, clustering and push suppression, measured.** On this
  corpus it changes no cluster and no accepted edge. Its only matcher-visible effect is 356 new
  cross-sport rejections, which is protective. URL dedup and notification identity read no
  entity data.
- **Structural risk: medium, not triggered here.** Each registered player becomes a canonical
  tier-N anchor, and a canonical person or team id on its own already produces wrong merges
  today: B3 (LeBron) and B1 (seven team-only wrong clusters). Growing the registry widens that
  path. The protective step is B3, then B1, each with a `RULE_VERSION` bump and a §12.2 review on
  a copy.
- **The bigger problem is independent of #259:** 21 of the 66 reviewed clusters are wrong or
  impure under the current code (B1, B2, B4), and wrong members also block true duplicates
  through the one-member-per-source rule. Do not run an anchor re-enrichment over the live
  corpus before B1 and B2 are fixed (§6).
