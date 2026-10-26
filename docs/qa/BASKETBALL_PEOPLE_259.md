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
| Guy push, seed profile (articles; the DB profile gives 14 → 17, below) | 18 | 19 | 19 | **19** |

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

### New pushes: classification vs notification (not approved; no workaround added)

**Classification, production path.** The rules-only rerun above scores the *seed* `guy` profile
and shows 1 new push. The live DB profile is stronger: Maccabi `very_high`, plus explicit push
rules for Maccabi `signing` and `negotiation`. With stored facts, the #353 delta and that profile
with learned feedback, Guy's push articles go **14 → 17** (holdout excluded; the Deni fan stays 3).

| Article | Facts with #353 | Guy (DB profile) |
|---|---|---|
| walla 07-23 "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב. סומן מחליף לווקר" | basketball, `team:maccabi_tlv_bb`, negotiation | hidden → **push** (Maccabi negotiation rule) |
| walla 07-18 "שבוע קריטי במו"מ עם לונדברג" | basketball, Maccabi, negotiation | hidden → **push** |
| walla 07-23 "מירוץ החימוש / השוק האירופי משתגע… עם אבי אבן באולפן" (a studio episode; the subtitle names Madar, Sorkin and "מכבי תל אביב") | basketball, Maccabi, **signing** (stored event type) | hidden → **push** (Maccabi signing rule) |

All three are among the 16 unrated items served blind. The studio episode is the clearest risk.
Its club resolution follows the stated semantics: the subtitle names the club itself. The push,
though, comes from a stored `signing` event type on a talk show. #353 makes such items reach the
explicit push rules. It does not create the wrong event type.

**Notification, isolated chronological replay** (planning only, never dispatched). How it was run:
- a copy of the frozen corpus; clusters and every notification table cleared; activation at
  2026-07-17 00:00 UTC the way `init_notification_watermark.py` does it;
- then every 30 simulated minutes until 07-24 12:00: the articles published in that slot are
  inserted, the real clustering stage runs (rule 2), and the real planner runs with the feed's
  freshness clock at the tick;
- same window, `main` with stored facts vs this branch with the #353 delta:

| Time (UTC) | `main` | #353 |
|---|---|---|
| 07-18 18:00 walla "שבוע קריטי במו"מ עם לונדברג" | — | **new event** |
| 07-20 12:30 walla "…ומתי לונדברג יסגור?" | new event | new event |
| 07-20 18:30 Israel Hayom "…איפה לונדברג סיכם על חוזה חדש" | new event | new event |
| 07-22 23:00 Sport5 "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב" | **new event** (the same agreement again) | **new event** (the same agreement again) |
| 07-23 02:30 ynet "נשאר צהוב: …" | expansion of the Sport5 event | expansion of the Sport5 event |
| 07-23 04:30 walla "…סומן מחליף לווקר" | expansion of the Sport5 event (a hidden member) | **expansion** of the Sport5 event, no message |
| 07-23 14:00 walla "מירוץ החימוש…" | — | **new event** |

Results:
- **The Lundberg walla article does not send a message.** It joins the Sport5 07-22 event's
  lineage as an expansion, with and without #353.
- **#353 does add two messages in this window:**
  - the 07-18 negotiation update, a new development;
  - the 07-23 studio episode, likely noise.
- **Today's code still sends the same agreement twice** (Israel Hayom 07-20 and Sport5 07-22,
  about 52 h apart, beyond the 24 h window). This is the pre-existing clustering split, not a #353 effect. Your push
  rating supports the article's relevance; it does not authorize the second message.

### Unrated changed decisions

16 changed decisions have no owner rating in any file (the full list with before/after and the facts change is in [BASKETBALL_PEOPLE_259_BEFORE_AFTER.md](BASKETBALL_PEOPLE_259_BEFORE_AFTER.md)). They are served blind for rating
(`docs/qa/people_259_flips_sample.json`, `rate_census.py serve`).

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
