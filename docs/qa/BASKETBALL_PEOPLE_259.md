# Israeli-league basketball people (#259): selection and measurement, 2026-10-25

**What changed.** 22 Maccabi and Hapoel Tel Aviv players and Hapoel's coach are registered
with `implies_team`: a mention emits the club and proves basketball. The people are not
followable. Jason Levin (#229) gains apostrophe variants. A resolved club person now counts as
sport evidence in `classify()` ([RSS_QUALITY_GUARDRAILS.md](../RSS_QUALITY_GUARDRAILS.md) §19).
The guard `cross_sport_entity_requires_explicit_sport` is **unchanged**.

## Why people, not a weaker guard

On the week sample's focused set, switching the guard off in memory recovers 3 wanted articles,
and it shows **5 football Maccabi stories the owner rated hide**: Sakhnin, Dor Turgeman, Abuksis,
the Europa League draw, and the plea bargains
([WEEK_SAMPLE_2026-10_DEV_RESULTS.md](WEEK_SAMPLE_2026-10_DEV_RESULTS.md)). A named basketball
person is evidence the guard can trust.

## Selection

A person is in the batch when they are (1) on a 2026-27 roster source and (2) named in the
corpus. All counts exclude the week sample's 35 holdout rows.

Roster sources: [RealGM, Maccabi](https://basketball.realgm.com/international/league/1/Euroleague/team/4/Maccabi-FOX-Tel-Aviv/rosters),
[Basketnews, Hapoel](https://basketnews.com/teams/635-hapoel-ibi-tel-aviv.html),
[Eurobasket, Hapoel](https://basketball.eurobasket.com/team/Hapoel-Shlomo-Tel-Aviv/160?Year=2026-2027).
Itoudis is also on [Wikipedia](https://en.wikipedia.org/wiki/Dimitrios_Itoudis) and
[Flashscore](https://www.flashscore.com/team/hapoel-tel-aviv/x0WjVzjP/). Yam Madar's move
(Hapoel → Maccabi, July 2026) is on [Wikipedia](https://en.wikipedia.org/wiki/Yam_Madar). The
sources disagree on parts of the Hapoel roster. Satoransky is on one source only, and a corpus
title reports his signing ("סטרונסקי סיכם בהפועל ת"א").

| Person | Club | Aliases (all word-bounded) | Corpus hits (word) | Note |
|---|---|---|---|---|
| Yam Madar | Maccabi | ים מדר, מדר | 61 (51 basketball) | bare "מדר" as a substring: 179 (מדריד, מדריך) |
| Bonzie Colson | Maccabi | בונזי קולסון, קולסון | 8 | |
| John DiBartolomeo | Maccabi | two spellings, full and surname | 5 | "דיברתולומאו" and "דיברתולומיאו" both occur |
| Jimmy Clark III | Maccabi | ג'ימי קלארק | 3 | bare "קלארק" also names Caitlin Clark |
| Oshae Brissett | Maccabi | אושיי בריסט, בריסט | 10 | as a substring also "בריסטול" |
| Daniel Theis | Maccabi | דניאל תייס, תייס | 12 | |
| T. J. Leaf | Maccabi | טי ג'יי ליף, טי.ג'יי ליף | 2 | full name only |
| Jaylen Hoard | Maccabi | ג'יילן הורד | 1 | "הורד" is a Hebrew verb |
| Iffe Lundberg | Maccabi | איפה לונדברג, לונדברג | 15 | "איפה" alone is "where" |
| Roman Sorkin | Maccabi | רומן סורקין, סורקין | 9 | |
| Will Rayman | Maccabi | וויל / ויל ריימן, ריימן | 5 | |
| Keaton Wallace | Maccabi | קיטון וואלאס | 1 | full name only |
| Shane Hunter | Maccabi | שיין האנטר | 1 | full name only |
| Dimitris Itoudis (coach) | Hapoel | דימיטריס איטודיס, איטודיס | 37 (32 basketball) | |
| Daniel Oturu | Hapoel | דן / דניאל אוטורו, אוטורו | 9 | |
| Jacob Toppin | Hapoel | ג'ייקוב טופין, טופין | 7 | the corpus writes "ג`ייקוב" |
| Vasilije Micic | Hapoel | ואסיליה / ואסה מיציץ', מיציץ', מיצ'יץ' | 7 + 1 | |
| Antonio Blakeney | Hapoel | אנטוניו בלייקני, בלייקני | 8 | |
| Bruno Caboclo | Hapoel | ברונו קאבוקלו, קאבוקלו | 1 | |
| Tomer Ginat | Hapoel | תומר גינת | 1 | full name only |
| Bar Timor | Hapoel | בר טימור | 4 | full name only |
| Ishmail Wainright | Hapoel | וויינרייט | 2 | |
| Tomas Satoransky | Hapoel | סאטורנסקי, סטרונסקי | 2 | one roster source |

Every alias also gets its `׳` and `` ` `` spellings. **Left out:** Tamir Blatt (a corpus title
reports him loaned to another European club) and roster names with no corpus mention (for
example Bacot, Dodo, Abo, Blayzer, Ennis, Palatin).

**Stored sport labels are not ground truth.** Some "football" hits above are basketball
stories stored with a wrong sport (for example "עדיין מושלמת: הפועל ת"א ניצחה 78:80 את רומא").
Collision review used the titles, not the stored sport.

## Measurements

Unless a row says otherwise, all runs are on a verified copy of the corpus (3,227 rows) with the
holdout rows removed (3,203 compared).

### Census #2 and N05: whole-corpus rerun (rules only, in memory)

`corpus_rerun_diff.py` replays every row through `_normalise` with the LLM disabled. It
approximates production.

| | before | after |
|---|---|---|
| census #2 feed+ recall | 113/138 | **121/138** |
| census #2 shown precision | 153/163 | 162/172 |
| census #2 exact tier | 662/804 | 667/804 |
| N05 feed+ recall | 85/99 | 86/99 |
| N05 shown precision | 113/116 | 115/118 |
| N05 push precision / recall | 8/9, 8/9 | 8/9, 8/9 |
| Guy visible / push | 631 / 18 | 657 / **19** |
| Deni fan visible / push | 72 / 4 | 72 / 4 |

31 decision flips, all for Guy, and none for the Deni fan.

**Rated flips (census #2 / N05), toward or away from the owner:**

| Article | Owner | Before → after | Direction |
|---|---|---|---|
| בריסט: "חשוב לנו לשחק נגד יריבות חזקות" | feed | hidden → high | toward (one step over) |
| קולסון כיכב, 87:92 למכבי ת"א על אריס | high | hidden → feed | toward |
| "בלתי נתפס": באירופה נדהמו מהסל של ים מדר | feed | hidden → feed | toward, exact |
| הפועל תל אביב כבר מתחרטת? "יש בים מדר משהו קוסמי" | feed | hidden → feed | toward, exact |
| "אין הצהרות": מכבי ת"א מרוצה מהזכייה בסופרקאפ | feed | hidden → feed | toward, exact |
| בסימן שאלה: דניאל תייס ייעדר מול הפועל ת"א? | high | feed → high | toward, exact |
| "בראינט מעניין רק את בראינט. למדר יש בייגלה מעל הראש" | feed | hidden → high | toward (one step over) |
| קולסון עקץ את הפועל | high | feed → high | toward, exact |
| דרבי על תואר: מכבי תל אביב והפועל תל אביב ייפגשו בסופרקאפ | feed | hidden → high | toward (one step over) |
| הצגת בכורה: מכבי זכתה בסופרקאפ מול הפועל | feed | hidden → feed | toward, exact |
| הסיפור המלא נחשף: מאחורי עסקת מדר למכבי (N05) | high | hidden → feed | toward |
| חי ממשחק ההכנה: אולימפיאקוס - מכבי תל אביב 35:35 | low | hidden → feed | now shown; owner low |
| בר טימור במשא ומתן על חוזה חדש בהפועל (N05) | low | hidden → feed | now shown; owner low |
| יפתחו את היורוליג? מצב הפצועים של מכבי | feed | feed → high | **away** (one step) |

**The new push**, unrated: "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב. סומן מחליף לווקר". It
was hidden, because Lundberg resolved to nothing. Now it resolves to Maccabi, and Guy's existing
Maccabi signing rule pushes a concluded contract. #259's acceptance asks for **no new push**, so
this needs the owner's call. The push follows an existing rule; it is not a new one.

The 17 flips rated in neither census #2 nor N05 are all Maccabi or Hapoel Tel Aviv basketball stories now shown (Madar's
move, Lundberg's negotiation, Blakeney's extension, the Toppin talks, Hapoel at Panathinaikos).
Whether Guy wants Hapoel narrative stories is the open product question #257.

### Review of every new match (zero false resolutions found)

All 56 rows whose facts or decisions changed were read. For the 18 whose title names no
registered person, the person was found in the subtitle (for example Sorkin's 23 points;
Brissett and Theis missing from the derby). Every new resolution names a registered person, in a
basketball story. Losses, with no decision change:

- 4 rows lose a club that came only from subtitle gap-filling. Since the title now resolves its
  subject, the subtitle no longer adds entities (an existing rule, as with the #229 executives):
  - "ערב גדול של מדר לא הספיק בברצלונה" and "ים מדר הוא סקורר כמו מיקי ברקוביץ'" lose Barcelona.
  - "ים מדר: היה קיץ ארוך" and the Hinas handshake clip lose Hapoel.
- "איטודיס הזהיר: אין לנו זכות לשחק ככה ביורוליג" (dev) keeps Hapoel and loses four subtitle
  teams.
- "דני אבדיה לים מדר: אתה לא נורמלי" gains Maccabi next to Deni. The Deni fan's decision is
  unchanged.

### Week sample (production configuration: Groq 20b, cached answers, gate on)

| Set | before | after | shown but rated hide |
|---|---|---|---|
| dev (70) | 21/24 | 21/24 | 0 → 0 |
| focused (30) | 7/11 | 8/11 | 0 → 0 |
| #345 regression (7) | 0/7 | 5/7 | 0 → 0 |

Changed decisions:
- **focused:** Jason Levin's interview (rated push), hidden → feed. That is the apostrophe-variant
  fix: "ג`ייסון".
- **regression:** the Aris win, Madar "קוסמי", "אין הצהרות", "בראינט…מדר", and the Super Cup derby.
- Dan Otoro (focused) now resolves to Hapoel but stays hidden. That is the profile question
  (#257), not identification.
- dev: no decision changes. The gate now sends fewer of these articles to the LLM, because the
  taxonomy resolves them.

### N05 gate (stored facts)

`feed_ground_truth.py gate` passes, unchanged: shown precision 113/115, false hide 18.0%, push
7/7. It scores stored facts, so it does **not** exercise a classifier change. The rerun above is
the measurement for that.

## Design evidence vs independent evidence

- **Design:** the names were picked partly from the #345 regression rows' subtitles and the
  focused misses (Madar, Colson, Brissett, Theis, Otoro, Toppin, Levin). The regression (0 → 5)
  and focused (7 → 8) gains are therefore **not independent**.
- **Independent:** census #2's other rated rows, N05, and the dev sample. Census #2 gains 8 wanted
  rows; several are regression rows (the Aris win, "קוסמי", "אין הצהרות", "בראינט", the derby).
  Excluding those five, 5 other census #2 rated rows move toward the owner (Brissett, Madar
  "בלתי נתפס", Theis, Colson's "עקץ", the Super Cup win) and 1 moves away ("יפתחו את
  היורוליג", feed → high). dev shows no change.
- **Holdout:** the 35 test rows were not used and not read. Freeze this candidate before opening
  them.

## Effect on clustering and duplicates

Story anchors resolve taxonomy entities directly, so a registered person adds a canonical anchor
(`player:yam_madar`) **next to** the lexical one ("מדר"), which is still stored. Old and new
articles keep sharing the lexical key, so the change adds keys and removes none. Coaches stay
role-holders, never story anchors. Exact-duplicate detection is by URL and does not read
entities. `test_anchor_validation_141` used "ים מדר" as an example of an unregistered name; its
fixture now uses an unregistered name. A broader clustering check is a separate PR.

## Not done (separate follow-ups)

- The three dev misses are outside #259: the LLM calling Hapoel's EuroLeague game football;
  Avdija named only in a subtitle, with no NBA competition; the national-team coach story with no
  entity. See [WEEK_SAMPLE_2026-10_DEV_RESULTS.md](WEEK_SAMPLE_2026-10_DEV_RESULTS.md).
- Stored rows are not reclassified. Only new articles get the people. A reviewed backfill is a
  separate decision.
- Hapoel Jerusalem and other clubs: not in this batch.
