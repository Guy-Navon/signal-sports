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
| Guy push (articles) | 18 | 19 | 19 | **19** |

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

### The new push: Lundberg (not approved; no workaround added)

- **Article:** `rss_9ccfed7f40f424ede65d` (walla, 2026-07-23),
  "איפה לונדברג סיכם על חוזה חדש במכבי תל אביב. סומן מחליף לווקר". It has no owner rating.
- **Path:** Lundberg in the title gives basketball, so `מכבי תל אביב` resolves to
  `team:maccabi_tlv_bb`. The event is `negotiation` (probable). Guy's profile rule
  `always_push:negotiation` on Maccabi then decides **push**. Before this PR the same article was
  `unknown` and hidden.
- **Context:** the same agreement was pushed twice in July, by Israel Hayom (07-20) and Sport5
  (07-22), and the owner rated both **push** in N05. This walla article is in the **same
  cluster** as the Sport5 one, so live it would join that notification's lineage, not send a
  new message. The +1 is an article-level count.
- **The owner decides** whether this meets "no new push".

### Unrated changed decisions

16 changed decisions have no owner rating in any file (the full list with before/after and the facts change is in [BASKETBALL_PEOPLE_259_BEFORE_AFTER.md](BASKETBALL_PEOPLE_259_BEFORE_AFTER.md)). They are served blind for rating
(`docs/qa/people_259_flips_sample.json`, `rate_census.py serve`).

## Clustering

Clustering measured with the first version (PR #362): 68 = 68 clusters with identical members.
A registered person adds a canonical anchor next to the lexical one. The latent risk is B3
(#364), a shared person rescuing different stories; it is fixed separately in its own PR.

## Not done (separate follow-ups)

- #352: three dev misses outside #259.
- #257: whether Hapoel stories belong in Guy's feed. That is profile-driven, not classification.
