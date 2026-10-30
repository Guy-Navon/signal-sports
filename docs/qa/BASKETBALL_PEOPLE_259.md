# Israeli-league basketball people (#259): selection, semantics and measurement

Updated 2026-10-26, after review.

## Scope: more than a data change

This PR goes beyond adding registry entries. It changes three things:

1. **Registry data.** 28 Maccabi and Hapoel Tel Aviv players and Hapoel's coach (Itoudis)
   carry a new flag, `implies_team`. They are not followable.
2. **Sport evidence (classifier rule).** A resolved club person proves the sport
   (`classifier._club_person_sport`). This applies in the title and in the subtitle gap-fill.
   Kattash was the only person who did this before, as a hand-written keyword.
3. **Club evidence (classifier rule, narrower than sport).** A club person implies their
   current club only when:
   - the person is named in the **title**, and
   - the text has **no national-team context** (`נבחרת`).

   A person named only in the subtitle, or in a national-team story, proves the sport and
   nothing more. The club still resolves when the text itself names it (for example
   `מכבי ת"א` plus a player in the subtitle).

`cross_sport_entity_requires_explicit_sport` is unchanged. Jason Levin (#229) gains apostrophe
variants. Only newly ingested articles are affected; there is no backfill.

## Selection: official roster and corpus

A person is registered when they are (a) on the club's 2026-27 roster on the Israeli league's
official site, **checked 2026-10-26**, and (b) named in the corpus. The pages are
[Maccabi Rapyd Tel Aviv](https://basket.co.il/team.asp?TeamId=2111&lang=en) and
[Hapoel IBI Tel Aviv](https://basket.co.il/team.asp?TeamId=2112&lang=en). "Inactive" there means
on the club but not registered for the domestic league; those players are kept.

| Club | Registered (aliases are word-bounded; full name only where marked *) |
|---|---|
| Maccabi | Madar, Colson, DiBartolomeo (2 spellings), Clark III*, Brissett, Theis (inactive), Leaf*, Hoard*, Lundberg, Sorkin, Rayman, Wallace*, Hunter* |
| Hapoel | coach Itoudis, Oturu, Toppin (inactive), Micic (inactive), Blakeney, Caboclo (inactive), Ginat*, Timor*, Wainright, Satoransky (inactive), **Blatt\***, Bryant*, German*, Carrington*, LeDay* (inactive), Coffey* |

**Correction from the first version.** Tamir Blatt was left out because a corpus headline
reported him loaned abroad. The official roster lists him as active, so he is now registered.
A headline is not a roster source. Roster names with no corpus mention (Bacot, Dodo, Ebo, Lavy,
Heidegger, Segev, Palatin, Blayzer, Bourdillon, Odiase, Ennis) are not registered.

**Full name only, with the reason:**

| Surname | Why the bare surname is unsafe |
|---|---|
| `קלארק` | also names Caitlin Clark |
| `הורד` | a Hebrew verb |
| `בלאט` | also names David Blatt |
| `בראיינט` | also names Kobe Bryant |
| `לידיי` | appears inside `לידיים` |
| `קופי`, `קרינגטון` | a football hit in the corpus |
| `ליף`, `וואלאס`, `האנטר`, `גינת`, `טימור`, `ג'רמן` | common words or names |

Substring checks used the corpus, with the 35 holdout rows excluded. `בריסט` is safe only
word-bounded (`בריסטול`), and so is `מדר` (`מדריד`, `מדריך`, `שחקנים מדרגים`).

## Semantics: sport is not the same as the article's club

A name is strong evidence of the **sport**. It is weaker evidence that the article is about the
person's **current club**. Review of the changed rows:

| Case | Behavior now | Evidence |
|---|---|---|
| National team (`ים מדר הוביל את נבחרת ישראל`) | sport only, no club | tested; none in this corpus window |
| Person only in the subtitle, incidental | sport only, no club | corpus: a David Blatt gossip item named his son Tamir (a Maccabi player *last* season) in the subtitle and got Hapoel attached; tested |
| Person in the title, club named elsewhere | club from person, plus the named club | for example `ים מדר נפרד מהפועל ת"א` gets Maccabi and Hapoel |
| Former club or transfer | the **current** club is attached | known limitation, see below |
| Several people or clubs | each title person adds their club | `קולסון עקץ את הפועל` gets Maccabi (Hapoel is a bare family name) |

**Known limitation.** `team_id` is today's club. For articles ingested from now on, today's club
is the right one while the roster data is current, but it must be maintained at every roster
change. Applied to past articles (a backfill), it would attach today's club to a July transfer
story. **Do not backfill** with this registry.

## Measurements

All runs are on a verified copy of the corpus. The 35 holdout rows were removed (3,203 rows
compared). The whole-corpus rerun is **rules only**, so it approximates production.

### Three semantics on the same data (census #2, Guy)

| | main | sport only (no club from person) | first #353 (club from any person) | **this PR** (club from title person, not national team) |
|---|---|---|---|---|
| feed+ recall | 113/138 | 117/138 | 121/138 | **120/138** |
| shown precision | 153/163 | 158/168 | 162/172 | **161/171** |
| exact tier | 662 | 663 | 667 | **667** |
| N05 feed+ recall | 85/99 | 85/99 | 86/99 | **86/99** |
| N05 shown precision | 113/116 | 113/116 | 115/118 | **115/118** |
| N05 push precision / recall | 8/9, 8/9 | 8/9, 8/9 | 8/9, 8/9 | **8/9, 8/9** |
| Deni fan (visible, push) | 72, 4 | 72, 4 | 72, 4 | **72, 4** |
| Guy push, seed profile, rules-only (articles; context 1 below) | 18 | 19 | 19 | **19** |

A naive "sport only" that records the person as an entity scored **below main** (110/138). The
title entity blocks the subtitle's club gap-fill. The "sport only" column above records no
entity.

**Title rule vs the first version, rated rows:**
- "יפתחו את היורוליג? מצב הפצועים של מכבי" goes from high to **feed**, now exact with the owner's
  rating.
- "הצגת בכורה: מכבי זכתה בסופרקאפ מול הפועל" goes from feed to **hidden**; the owner rated feed.
  The title names only the bare family names, and the players are in the subtitle.

### Week sample (Groq 20b, cached answers, 0 model calls)

| Set | main | this PR | shown but rated hide |
|---|---|---|---|
| dev (70) | 21/24 | 21/24 | 0 → 0 |
| focused (30) | 7/11 | 8/11 (Levin, via the apostrophe variant) | 0 → 0 |
| #345 regression (7) | 0/7 | 5/7 | 0 → 0 |

### Design evidence vs independent evidence

- **Design:** the names were partly chosen from the regression and focused rows, so those gains
  are not independent.
- **Independent:**
  - census #2's other rated rows: Brissett, Madar "בלתי נתפס", Theis and Colson "עקץ" move toward
    the owner; "הצגת בכורה" moves away (hidden; owner feed);
  - N05: the Madar deal, now feed (owner high), and Bar Timor, now feed (owner low);
  - dev: no change.
- **Holdout:** not used. It is partially exposed; see WEEK_SAMPLE_2026-10_DEV_RESULTS.md.

### New pushes and messages: three evaluation contexts (not approved; no workaround added)

An explicit push rule fires only after the **push-severity gate**: the article's
`classification_trace.attention` must say the development is an agreement or completion (or
an imminent renewal, a current injury, or a concrete governance step) for the followed subject.
The gate dates from 2026-09-11 (d6462ba). **Rows stored before it carry no `attention`, and the
engine then skips the gate** (1,409 of 3,291 rows in the frozen copy, including every July
Lundberg row). That one fact explains why the contexts below disagree. The profile does not:
the seed and the live DB `guy` profile have identical Maccabi rules (very_high; push on signing,
negotiation, injury, title_win, club_governance).

| Context | Facts and trace | Profile | Guy push articles | Messages (Lundberg week replay) |
|---|---|---|---|---|
| 1. Rules-only rerun of every row (the earlier "one new push") | recomputed by each arm's code, attention included | seed | +1 (18 → 19) | — |
| 2. Stored historical rows + this PR's sport/entity delta (first replay) | July traces **without** attention, so the gate is skipped | DB + learned | +3 (14 → 17) | **+2** |
| 3. Every row of the week recomputed by each arm's own code | consistent, attention included | DB + learned | +1 in the week (5 → 6) | **+0** |

**Context 2 overstated the impact.** It mixed this PR's new facts with traces older than the
gate, a state production does not reach: every new article gets `attention` at ingestion, and
this PR changes no stored row (no backfill). Context 3 is the faithful one. Its residual
caveats:
- it is rules-only: on the LLM path, sport, entities and event can differ;
- the replay covers one week.

The three articles, per context:

| Article | Your rating | Facts main → PR | Attention (current code) | Guy: ctx 1 / ctx 2 / ctx 3 | Cluster and message (ctx 3) |
|---|---|---|---|---|---|
| walla 07-23 [איפה לונדברג סיכם על חוזה חדש… סומן מחליף לווקר](https://sports.walla.co.il/item/3855583) | none (blind set) | unknown → basketball; + `team:maccabi_tlv_bb` (title person Lundberg); negotiation | agreement_or_completion, subject Maccabi | push / push / **push** | `cluster_154662894917b642` with Sport5 and ynet; **expansion** of the Sport5 07-22 event, no message |
| walla 07-18 [שבוע קריטי במו"מ עם לונדברג](https://sports.walla.co.il/item/3854409) | none (blind set) | unknown → basketball; + Maccabi; negotiation (confirmed) | routine_or_uncertain, no subject | high / push / **high** | unclustered; not push, so no event |
| walla 07-23 [מירוץ החימוש / השוק האירופי משתגע… עם אבי אבן באולפן](https://sports.walla.co.il/item/3855762) | none (blind set) | unknown → basketball (subtitle people); + Maccabi (the subtitle names "מכבי תל אביב"); signing | routine_or_uncertain, no subject | high / push / **high** | unclustered; not push, so no event |

**The studio episode's "signing".**
- **Stored:** `rules_fallback_after_llm_failure` (the Ollama call failed in July).
- **Reproducible today:** current rules still say `signing` (probable). The cue "חתמה" ("she
  signed") matches inside the noun "ההחתמה" in the subtitle ("מה אמר אבי אבן על ההחתמה של ים מדר").
- **#353's role:** on `main` the item stays hidden (sport unknown). With this PR it becomes
  basketball + Maccabi and reaches the signing rule. The attention gate withholds the push, so it
  shows as `high`.
- **A general fix** (mask the noun forms for the signing rule) is prepared separately as a
  **draft**, because your ratings are mixed (one toward, two away).

**Still true in every context:** today's code sends the same Lundberg agreement twice
(Israel Hayom 07-20 and Sport5 07-22, about 52 h apart, beyond the 24 h window), with or without
this PR. Tracked as #371 with a strict-xfail regression test.

**Do not backfill.** Applying this PR's facts to stored rows without recomputing attention
would recreate context 2.

### The 16 unrated changes, rated blind by the owner (2026-10-26)

**What this is.** A targeted check of the articles this PR *changes*. It is not an independent
estimate of overall feed quality: the set was selected because the decision changed, the
articles are about the clubs the PR touches, and the population is small (16).

The owner rated all 16 on the blind page (`people_259_flips_ratings.json`; decisions were not
shown). The owner's own tolerance: one step (3 vs 4, 2 vs 3) is a judgment call, not an error.
The clear-cut cases ("a player agreed a new contract = push") are what must be right. Decisions
are from the rules-only rerun (seed profile).

| On the 16 | `main` | this PR |
|---|---|---|
| Exact | 0 | **11** |
| Within one step | 3 | **15** |
| Rated feed or higher, but hidden | 13 | **0** |
| Shown, rated hide | 0 | 0 |
| Push not rated push | 0 | 0 |

- **The one push** (Lundberg agreed a new contract) is rated push.
- **The studio episode** is `high`, rated feed (within one); no push.
- **The one miss of two steps:** "הפתעה גדולה: מכבי ראשון לציון היממה את מכבי תל אביב", rated
  **push**, decided feed. A Maccabi match result: Guy's profile has no push rule for results.
  That is a profile question, not this PR's classification.
- **Hapoel Tel Aviv items** (Toppin talks, Blakeney's extension, Panathinaikos away, the Madar
  farewell) are rated feed or high, so the owner wants them visible. This informs #257 and golden
  case C9.

## Final semantic review: "belongs to the club" vs "the article is about the club"

`implies_team` attaches a person's **current** club, from the registry (the official 2026-27
roster). That is a proxy for "this article is about that club". The two differ, and roster
maintenance alone does not close the gap.

**Where the proxy held, in the changed set.** 10 of the 29 changed articles got a club only
from a person (the text did not name the club):
- 8 are about that club: Brissett and Theis around Maccabi games, Madar's shot, Colson's jab,
  Blakeney's and Timor's contracts, Toppin's talks, the Madar deal;
- 2 are Madar's farewells from Hapoel. They get the destination club (Maccabi), while the club
  they are mainly about (Hapoel) is attached only when the text names it. The owner rated both
  feed/high, so no harm here, but it is the proxy, not the meaning.

**Remaining risks and assumptions:**

| Case | Behavior | Risk |
|---|---|---|
| National team | the text marker "נבחרת" suppresses the club (sport still counts) | Only that word is recognized; "ישראל ניצחה", "יורובאסקט" or age-group teams are not. The marker also fires on incidental mentions inside club stories ("שחקן הנבחרת"), dropping club evidence. 1 corpus case, where dropping it happened to be right (Blatt, July: "still looking for a team") |
| Former club, transfer, farewell | the current club is attached; the former club only if named | A farewell is filed under the destination club. A future "X returns to his old club" headline would attach the current one |
| Historical or retrospective articles | today's roster is applied to past events | A July article about Blatt seeking a team would carry today's Hapoel. Safe only for articles ingested while the roster is current: **no backfill** |
| Roster changes mid-season | stale entries attach the wrong club until updated | No automatic expiry: the roster-maintenance routine in [TAXONOMY.md](../TAXONOMY.md#roster-maintenance-club-people-implies_team-377) keeps it current (#377) |
| Incidental person in the subtitle | sport only | covered by tests |
| Ambiguous surnames | full-name aliases only | covered by tests and the alias table |

A fuller fix would need the article's *subject* (who or what the headline is about), not
membership. That is out of scope; the attention evidence's `subject_entity_ids` is the nearest
existing signal.

## Transfers and farewells: extra association or wrong subject? (2026-10-26)

**The three Madar farewells** (11 July). Decisions are rules-only with the seed profile; the
reason line is the reader's "למה אצלך"; all three are `release`, which no push rule of Guy's
covers, so none is push-eligible.

| Article | Owner | Facts `main` → this PR | Guy | Reason shown |
|---|---|---|---|---|
| walla "כך ים מדר נפרד מהפועל ת"א" | feed | none → Maccabi **+ Hapoel** | hidden → high | "מכבי תל אביב (כדורסל) ברשימת המעקב שלך" |
| ynet "ים מדר נפרד מהפועל ת"א…" | high | Hapoel → Maccabi **+ Hapoel** | feed → high | same |
| sport5 "מדר: עוזב בראש מורם" | high | none → **Maccabi only** | hidden → high | same |

- **walla and ynet: an extra association.** The club the article is about (Hapoel) is present.
- **sport5: a wrong subject.** The subtitle names Hapoel only by the family name ("מהפועל"),
  which never resolves, so the facts read "Maccabi + release". The feed outcome matches the
  owner's rating (high: Madar is a new Maccabi player).
- Who would be misled: a Hapoel follower misses this farewell, and a profile with a Maccabi
  `release` push rule would get a false push. No current profile has such a rule.

**New coverage: the same failure, plus a found and fixed case.** Probing current code with new
transfer headlines:
- "רשמי: ג'ימי קלארק חתם בפנאתינייקוס" (a registered Maccabi player signing elsewhere) carried
  **only Maccabi**. Panathinaikos and Olympiacos are guarded names that need basketball
  evidence, and the person's sport evidence never reached them.
- **Fixed in this PR:** when a title person proves the sport, the title is re-resolved with it,
  as the ambiguous-club path already did. The destination club is now attached too.
- Corpus effect: 1 fact change (Barcelona added to a Maccabi game report), 0 decision changes,
  census metrics identical.
- The Maccabi association stays: Guy sees "a Maccabi player leaves for Panathinaikos" as Maccabi
  news (`high`). The push gate keeps it from being a push, because there is no Maccabi subject
  in the attention evidence.

**Corrected (owner decision 2026-10-26: an unresolved club beats an unsupported one).** In
departure or transfer context the roster club is no longer inferred:
- a departure word (נפרד / פרידה / עוזב / עזב / עבר ל…) in the title, or
- a transfer verb (חתם / סיכם / הצטרף / מו"מ…) next to a **different** named club.

A club the text names is still attached. Ordinary current-club stories keep the roster club:
an injury before a game against Hapoel, an extension, a quote.

- **Clark → Panathinaikos:** only Panathinaikos.
- **The Madar farewells:** walla and ynet carry Hapoel only (decision high → feed); sport5,
  naming no club, is now unresolved (high → hidden).
- **Corpus:** 3 decision changes (exactly the farewells); census #2 and N05 unchanged against
  the previous version.
- **Blind set:** exact 11 → 10, within one 15 → 14, one wanted-but-hidden (the sport5
  farewell, rated high). That is the accepted tradeoff.

**Still open (follow-up):** a stale registry attaches a former club to ordinary stories that
have no departure context. Roster maintenance is required.

## Owner decisions recorded (2026-10-26)

- **#257 / C9:** feed is the baseline for Hapoel Tel Aviv basketball coverage in Guy's profile,
  with high where justified. It is profile-specific, not a global rule. Golden C9 `desired` now
  asserts `guy: feed`.
- **Lundberg push:** the classification is accepted. Notification deduplication stays a
  separate concern.
- **#371:** accepted as a documented, pre-existing gap for this review. The faithful replay
  shows this PR adds 0 duplicate messages. It stays high priority for the MVP.
- **Maccabi match results:** no general push rule from the single Rishon LeZion example; the
  question is recorded separately.

## Clustering

Re-measured with the final branch on a frozen copy (2026-10-25 20:01 JST, 3,307 articles), with
this branch's facts and anchors applied as an isolated delta (`docs/CLUSTERING.md` §12.2):
161 rows gain a canonical person anchor, 54 entity changes, 17 sport changes.

- **0 clusters change, and 0 accepted edges are added or removed** vs `main`. 14 accepted edges
  gain a person id next to the lexical name they already had.
- 356 pairs move to a cross-sport hard reject, which is protective.
- The latent risk is B3: a shared person rescuing two different stories. It is fixed in #369.
  #369 with this branch gives exactly #369's single change: the LeBron wrong merge is split.
- Do not re-enrich anchors or backfill facts on the live corpus.

## Not done (separate follow-ups)

- #352: three dev misses outside #259.
- #257: whether Hapoel stories belong in Guy's feed. That is profile-driven, not classification.
