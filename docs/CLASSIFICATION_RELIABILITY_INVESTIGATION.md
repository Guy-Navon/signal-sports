# Classification & Feed Reliability Investigation

**Date:** 2026-07-09
**Status:** Investigation report — no code changes made, no issues created.
**Scope:** 15 production-style observations (9 problematic, 6 strong positives) from the real feed, traced end-to-end through the repository implementation.

**Method:** All 15 cases were located in the production DB (`backend/data/signal_sports.db`, 327 articles at time of investigation), their persisted `classification_trace` rows were read, and every case was re-scored offline through the real Preference V2 engine (`score_article_v2`) for both seed profiles. Every claim below is verified against actual code and persisted traces, not screenshots alone. All screenshot decisions reproduced exactly.

---

## 1. Executive assessment

**The problem is serious, real, and systemic — but it is not architectural.** The four-stage architecture (facts → visibility → preference → learning) is sound and its contracts largely hold. The failures concentrate in **two evidence-semantics defects inside the facts stage**, plus a handful of mapping gaps:

1. **The event-evidence layer validates vocabulary presence, not event assertion.** Hebrew champion-status epithets ("האלופה", "אלופת איטליה", "אלופת העולם"), competition names containing champion words ("אלוף האלופים" = the Israeli Super Cup; "ליגת האלופות" = Champions League — a synthetic UCL headline classifies as `title_win`/`very_high` today, verified), and win-verb substrings inside aspirational infinitives ("זכו" ⊂ "לזכות באליפות") all pass as *confirmed* `title_win` evidence. This is not isolated: **of the 17 `title_win` rows in the corpus, ~15 are false positives**, and the 62-row `finals_result` bucket is similarly contaminated by "גמר" in World Cup previews and even a plea-bargain story.

2. **An LLM-echo loop can lock in a wrong sport for cross-sport clubs.** When a Maccabi/Hapoel title has no explicit sport keyword and no URL hint, the gate correctly force-calls the LLM; if the 3B model guesses wrong, the merge adopts its sport, post-merge enrichment *injects the basketball entity*, and the facts stage then sees `entity_derived` evidence that is actually the LLM's own guess wearing a taxonomy costume. Nothing independent remains to override it.

Downstream layers behaved correctly on the false facts: Guy received **4 pushes from this set, 3 of them false** (Cases 1, 2, 3 — all `always_push` overrides firing on wrong facts), and the Casual Deni Fan profile was fully protected (all 15 hidden). Push discipline is broken by upstream facts, not by the engine.

The right response is **targeted hardening of two subsystems plus mapping fixes, gated by a regression-first golden corpus** — not a redesign.

---

## 2. Current pipeline (as it actually exists)

Per `backend/app/ingestion/ingestion_service.py:_normalise` (the single orchestration point):

```
RSS item (title, summary→subtitle, url)
  │
  ├─ language detect / translate (non-Hebrew only)
  ├─ source_sport_hint = extract_source_sport_hint(source_id, url)     [classification/source_hints.py]
  │
  ├─ [A] DETERMINISTIC classify(title, subtitle, url, hint)            [ingestion/classifier.py]
  │      sport: hint > tennis kw > football-Maccabi kw > ambiguous-club
  │             (Maccabi/Hapoel TLV full-name + ctx kw) > generic kw sets
  │      entities: taxonomy resolver (longest alias, cross-sport abstention,
  │             guarded entities, bare family names never resolve)
  │      subtitle: fills ONLY gaps (sport=unknown, entities=[], event=news,
  │             league=None). Never overrides title.
  │      league: explicit kw > Deni→NBA > Maccabi+IL-ctx > MEMBERSHIP INFERENCE
  │      event: ordered proposal list (title_win before negotiation before
  │             signing…), each validated by event_evidence tables
  │      importance: title_win/finals → very_high automatically
  │
  ├─ [B] LLM GATE (Hebrew broad sources only)                          [classification/gating.py]
  │      force-call: ambiguous_club | sport_unknown | conf<0.55
  │      skip: clear league kw | hint agrees + extra context | league+conf≥0.8 …
  │
  ├─ [C] LLM (ollama qwen2.5:3b) → merge_with_guardrails               [classification/merge.py]
  │      LLM primary; guardrails: football-Maccabi kw, sport/league fill,
  │      RULES NON-NEWS EVENT ALWAYS BEATS LLM "news" (G4),
  │      LLM event needs semantic evidence (G4b), never downgrade importance,
  │      league-sport compat, URL hint override; entity prune + normalize
  │
  ├─ [D] post-merge basketball entity ENRICHMENT                       [classifier.py ~L1044]
  │      sport==basketball + club phrase in title → inject club entity
  │
  ├─ [E] ArticleFacts consistency stage                                [classification/facts.py]
  │      weighted sport evidence: hint/bb-only-source(100) > title kw(80) >
  │      subtitle kw(60) > competition kw(55) > entity_derived(40) > llm(20)
  │      explicit-only competitions; entity/competition sport invariants;
  │      abstention; full trace
  │
  ├─ [F] post-facts event re-validation (idempotent)                   [ingestion_service.py ~L69]
  │
  └─ persist Article (facts fields + trace)

FEED (v2 default): score_article_v2                                    [services/preference_engine.py]
  hard constraints → base scope match (competition scopes via the four-tier
  match_competition_names: explicit > legacy > participant_inference >
  membership[team-anchored events only]) → entity boost → event delta →
  importance (+1 only if already visible) → membership feed-ceiling →
  threshold → always_push overrides (only path to push)
```

Everything in this diagram exists and was exercised by the 15 cases.

---

## 3. Case-by-case diagnosis

Verified feed decisions (offline replay of `score_article_v2` against the persisted rows):

| Case | Article id | Persisted facts | Guy | Deni fan |
|---|---|---|---|---|
| C1 LeBron podcast | `rss_33eef11e564e6ccbd36b` | basketball / NBA / title_win / very_high | **push** (false) | hidden |
| C2 Glazer ynet | `rss_4966b592b253e1237912` | **basketball** / Maccabi TLV **BB** / signing | **push** (false) | hidden |
| C2-sib Glazer ynet | `rss_cb0b4c43ca530340e218` | **basketball** / Maccabi TLV **BB** / **title_win** | **push** (false) | hidden |
| C3 IH double signing | `rss_05c8c1cbe8e772816f61` | **basketball** / Maccabi TLV **BB** / negotiation | **push** (false) | hidden |
| C4 tickets/Super Cup | `rss_e0a2baec61f2f442b009` | football / Maccabi TLV FC / **title_win** | feed (noise) | hidden |
| C5 Inter ynet | `rss_8c01ba5b97becd709976` | football / **title_win** | feed (noise) | hidden |
| C5 Inter walla | `rss_8cb0f5b7f65e0e799a65` | unknown / negotiation (abstained) | hidden | hidden |
| C6 HBS defenders | `rss_b0b7e0ef69b37b780a80` | football / Hapoel B"S FC / **title_win** | feed (noise) | hidden |
| C7 Messi op-ed | `rss_8241cfdb7c303cf65ce2` | football / **title_win** | feed (noise) | hidden |
| C8 Glazer walla ✅ | `rss_d1736b70a0e2919d31a1` | football / Maccabi TLV FC / signing | hidden (correct) | hidden |
| C9 LeDay | `rss_4f373fbfb598575654bb` | basketball / no entity / news | hidden (miss) | hidden |
| C10 Yabusele ✅ | `rss_65ed93aa42045974b4d7` | basketball / signing / primary=comp:nba (wart) | feed | hidden |
| C11 DiBartolomeo ✅ | `rss_cbf82691b2b0c97fd41e` | basketball / Maccabi TLV BB / signing | **push** (legit) | hidden |
| C12 Ness Ziona ✅ | `rss_b3a65b930842b6a7a886` | basketball / negotiation / primary=comp:euroleague (wart) | high_feed | hidden |
| C13 Fernando ✅ | `rss_8283463e8caf737071a4` | basketball / Partizan / negotiation (no Maccabi tag) | feed (should arguably push) | hidden |
| C14 Maccabi drama ✅ | `rss_a47af1f45ce74cfd72f8` | basketball / Maccabi TLV BB / news | feed (correct) | hidden |
| C15 Smith→Budućnost ✅ | `rss_457954c5a61f71aa158a` | basketball / Hapoel JLM BB / signing | feed via EuroCup reach | hidden |

### C1 — LeBron podcast (walla) → FALSE `title_win`, pushed to Guy

Title has no event keyword → event=news → subtitle gap-fill fires. Subtitle quote "הסיכוי הטוב ביותר **לזכות באליפות**": the win-verb list matches `"זכו"` as a *substring of the infinitive* "לזכות", and "באליפות" satisfies the championship-context group → compound `title_win`, certainty *confirmed*, importance `very_high`. Gate skipped (`clear_league_in_title`) — irrelevant, since rules produced the error. Sport/league/entity all correct (NBA, LeBron). Guy: `always_push comp:nba title_win` → **push**. First wrong step: event-evidence validation of an aspirational quote. English aspiration blockers exist ("wants the title") — Hebrew ones don't.

### C2 — "דן גלזר חתם במכבי ת"א" (ynet) → football article persisted as Maccabi Tel Aviv *Basketball* signing, pushed to Guy

The most instructive failure. Title: ambiguous club, no sport context (correct abstention, `ambiguous_club`). ynet URL is generic `/sport/article/` → no hint. Subtitle ("סגר את תנאיו אצל האלופה… דמי המעבר לקייראט…") contains **zero** football context keywords — transfer-fee vocabulary isn't in `_FOOTBALL_CTX_KW`. Gate force-calls LLM → qwen2.5:3b answers *"Basketball player Danny Galzer signs with Maccabi Tel Aviv"* (note: the prompt's own first few-shot example is a nearly isomorphic 'מכבי ת"א חתמה…' headline answered with basketball). Merge adopts sport=basketball → enrichment [D] injects "Maccabi Tel Aviv Basketball" → facts stage sees `entity_derived(40)` + `llm(20)` — **both are the same LLM guess**; no explicit evidence exists to override → locked in. Guy: `always_push maccabi signing` → **push**.

First wrong step: LLM guess; the structural defect is that stages D+E convert the guess into "independent" evidence. A sibling ynet article (`rss_cb0b4c43…`) failed identically *and* additionally got `title_win` from subtitle "האלופה" (LLM proposed `release`, guardrail 4b correctly rejected it for lack of evidence, fallback landed on the rules' subtitle-derived title_win).

### C3 — Maccabi TLV football double-signing (Israel Hayom) → basketball, pushed to Guy

Same chain as C2, with one aggravator: the article URL is `israelhayom.co.il/sport/israeli-soccer/…` — **explicit football evidence existed in the URL, but `source_hints.py` maps only `israeli-basketball`, `world-basketball`, `world-soccer`. `/sport/israeli-soccer/` is missing.** With the hint present, weight 100 would have overridden everything. Event `negotiation` (from "מגעים") is actually right; sport/entity wrong → `always_push maccabi negotiation` → **push**.

### C4 — Ticket sales for the Super Cup (walla) → `title_win`, feed for Guy

Sport/entity correct (football, Maccabi TLV FC, via subtitle "הפועל באר שבע"). Event: title contains "**אלוף האלופים**" — the Israeli Super Cup's *name* — and "אלוף" alone is sufficient `title_win` evidence → `very_high`. Gate skipped as `strong_deterministic_result`: confidence 0.95 partly *because* of the false event (+0.10) and membership-inferred league (+0.15) — the false result reinforced its own skip. Guy: football(-1)→0 pts, `title_win@football +1`, `very_high +1` → **feed**. Noise surfaced through the football-title-win affinity Guy legitimately wants for *real* titles.

### C5 — Inter improving its bid for Khalaili (ynet) → `title_win`, feed for Guy

Sport correct (ynet source URL hint → football). Event: subtitle opens "**מתקרב לאלופת איטליה?**" — "אלופת" is an epithet for Inter (reigning champions). Critically, the subtitle *also* contains genuine negotiation evidence ("מתקרב", "סיכם") — but in `_detect_event_evidence` the proposal list checks `title_win` **before** `negotiation`, so the epithet won. The walla version of the same story (no epithet phrasing, no hint) abstained to sport=unknown and got `negotiation` via LLM — hidden for Guy. Same story, three outcomes across two vendors.

### C6 — Hapoel B"S squad building (walla) → `title_win`, feed for Guy

Sport/entity correct. Title has no event keyword ("מחפשת", "לסגור" aren't in any list) → subtitle gap-fill → "**האלופה** חזרה ממחנה האימון" + "אלוף האלופים" → `title_win`/`very_high`. Same mechanism as C4/C5.

### C7 — Messi/Mondial conspiracies op-ed (ynet) → `title_win`, feed for Guy

Sport correct (hint + "מונדיאל"). Title events: none → subtitle "**אלופת העולם**" (epithet for Argentina) → `title_win`. Same mechanism.

### C8 — POSITIVE: "דן גלזר חתם במכבי תל אביב" (walla) → football signing, correctly suppressed for Guy

Same story as C2. The *only* material difference: walla's subtitle says "**הקשר** בן ה-29" — "קשר" (midfielder) is in `_FOOTBALL_CTX_KW` → subtitle resolves sport=football deterministically → entities re-resolve to Maccabi TLV FC → league via membership → confidence 0.95 → gate skips the LLM entirely. **The success is real but hinges on a single common word in the vendor's subtitle style.** It is not structurally reliable: C2 is the same article without that word.

### C9 — Zach LeDay on the verge of signing (sport5) → correct facts as far as they go, hidden for Guy

A genuinely multi-layer case, *not* the same root cause as above:

- **(a) Entities:** "בהפועל" is a bare family name (correct abstention — which Hapoel is genuinely ambiguous from the text); LeDay isn't in the taxonomy; the LLM's proposals ("Zakandyy", "Hapoel Tel Aviv Football") were rightly rejected.
- **(b) Sport:** LLM said football; subtitle keyword "פורוורד" (explicit, weight 60) outweighed the LLM (20) → `weighted_evidence_override` to basketball — **the weighted-evidence design working exactly as intended, and correctly.**
- **(c) Event:** "על סף **סיכום**" is not in the negotiation list ("על סף חתימה" and "סיכם" are; "סיכום" is neither) and the LLM's `negotiation` failed semantic validation → news.
- **(d) Decision:** Guy's profile has **no `sport:basketball` scope at all** — his Israeli-basketball interest exists only as `comp:ibl` — so a basketball article with no entity and no competition is `no_matching_scope` → hidden. Even with the entity resolved, `news` is in neither reach allowlist, so `comp:ibl` would not have matched; the entity/event extraction gap and the profile-coverage gap compound.

### C10 — POSITIVE with a wart: Yabusele → Panathinaikos (walla) → signing, feed for Guy

Signing from title "חתם" (confirmed); sport from subtitle "כדורסל"; Panathinaikos resolved (guarded entity + basketball evidence). The wart: the persisted row's `primary_competition` is **`comp:nba`** and league="NBA" — the subtitle's "עוזב שוב את ה-NBA" (background: *leaving* the NBA) was promoted to primary because the explicit competition scan has no aboutness weighting. Guy's EuroLeague visibility came from **Panathinaikos's membership reach** (and in the screenshot variant, whose subtitle says "ביורוליג", from explicit evidence). Robust mechanism overall; the background-mention promotion is a real, mild defect.

*(Observed-vs-inferred note: the screenshot shows explicit EuroLeague evidence while the persisted walla row's subtitle says "בכדורסל האירופי" and carries `primary_competition=comp:nba` — the screenshot is evidently a variant edit of the story; both paths are analyzed here.)*

### C11 — POSITIVE: DiBartolomeo re-signs (ynet) → signing, push for Guy (legitimate)

Why "במדי **האלופה**" in the subtitle did *not* contaminate: `classify()` scans the subtitle for events **only when the title yields `news`**. The title's "חתם" produced `signing` first, so the subtitle was never consulted. This is the whole championship-language divergence: C11's protection is title-primacy ordering, not epithet understanding. Sport anchored by the ynet `israelibasketball` URL hint; entity resolved via hint-driven re-resolution of the ambiguous club. This is Guy's one *earned* push in the set.

### C12 — POSITIVE: "מלך החטיפות ביורוליג בדרך לנס ציונה" (sport5) → negotiation, high_feed for Guy

sport5 folder-274 hint → basketball; "במו"מ מתקדם" in subtitle → negotiation (confirmed); guarded Ness Ziona resolved under basketball evidence. Wart, same shape as C10: `primary_competition=comp:euroleague` from "ביורוליג" — the player's *past* — on what is an IBL move; Guy's match rode the EuroLeague scope. Useful outcome, slightly wrong attribution.

### C13 — POSITIVE with a gap: "מכבי הולכת על ברונו פרננדו" (sport5) → negotiation, feed for Guy

Hint → basketball; subtitle "מאיצים **מגעים**" → negotiation; "**סנטר** פרטיזן" → guarded Partizan resolves. The missing Maccabi tag is **by-design abstention doing its job at the alias level** ("מכבי" bare family name never resolves; "הצהובים" is not an alias) — but the downstream cost is real: without `team:maccabi_tlv_bb`, Guy's `always_push maccabi negotiation` override cannot fire, and the level-2 base is lost. The article scored via EuroLeague membership reach (Partizan) and was **capped at feed by the membership ceiling**. So: not a trace/UI issue, a genuine entity-coverage gap (nickname + player registry) with a real decision delta (feed instead of push).

### C14 — POSITIVE: Maccabi ownership drama (ynet) → news, feed for Guy

Hint → basketball; hint-driven re-resolution → Maccabi TLV BB; the transfer-adjacent content ("כבר סגרו עם הולמס ופרננדו") stayed `news` because "סגרו" happens to be in no keyword list. Correct outcome; honest mechanism assessment: **keyword non-coverage, not comprehension** — the sibling C3 flipped to `negotiation` on "מגעים" in an equally news-like piece. The decision path (base 3, `news@maccabi −1` → feed) is the profile design working exactly as intended.

### C15 — POSITIVE: Justin Smith → Budućnost (walla) → signing, feed for Guy via EuroCup

Sport via "פורוורד"; entity = **Hapoel Jerusalem Basketball from the subtitle** (Budućnost is not in the taxonomy at all). The "EuroCup recognized" outcome is **membership reach from the club the player left** — Hapoel Jerusalem's `comp:eurocup` membership — matched at the membership tier and correctly ceiling-capped at feed. Stable and reasonable ("news reaching fans of the departure club"), but it is *not* evidence the system can resolve Budućnost/ABA/EuroCup; if the subtitle hadn't named an Israeli club, the article would have been entity-less. Brittle in the same way C8 is.

---

## 4. Root-cause groups

Cases 1–7 do **not** all share one cause (C1 vs C2/C3 differ), and C9 belongs to neither bucket.

### RC-1 — Event evidence validates vocabulary, not assertion

**Cases:** C1, C2-sibling, C4, C5, C6, C7. **Corpus-wide:** ~15/17 false `title_win`; contaminated `finals_result` (62 rows include knockout previews, color pieces, a plea-bargain story).

Four concrete sub-mechanisms:

1. Champion-status **epithets**: "האלופה", "אלופת איטליה", "אלופת העולם" describing the reigning champion, not a new title.
2. **Competition names** containing champion words: "אלוף האלופים" (Super Cup), "ליגת האלופות" (Champions League — verified to classify `title_win`/`very_high` today).
3. Win-verb **substring** overreach: "זכו" ⊂ "לזכות" (aspirational infinitive) + "באליפות" satisfies the compound rule.
4. Two **amplifiers**: proposal ordering (`title_win` checked before `negotiation` — decided C5), and the subtitle gap-fill asymmetry (subtitle events only when title=news — which is also what *saves* C11).

`title_win` auto-assigns `very_high` importance and "confirmed" certainty, maximizing blast radius. Merge guardrail 4 (`merge.py` — rules non-news always beats LLM "news") makes rules event false-positives **uncorrectable by the LLM**. Blockers for aspiration exist in English only ("wants the title"); no Hebrew modality guards.

### RC-2 — LLM-echo circularity on ambiguous clubs

**Cases:** C2, C2-sibling, C3.

Only fires in the exact configuration: cross-sport club title + no explicit sport keyword in title/subtitle + no URL hint + LLM guesses wrong. Chain: `ambiguous_club` (correct) → gate force-call (correct) → qwen2.5:3b wrong guess → merge adopts LLM sport → post-merge enrichment injects the basketball club entity → facts stage counts `entity_derived(40)` + `llm(20)` as if independent — both are the same guess → locked in. C9 proves the weighted-evidence design works whenever *any* explicit keyword exists; the failure window is exactly "no explicit evidence anywhere."

Contributing: the LLM prompt's few-shot set is basketball-skewed, and its first example ('מכבי ת"א חתמה על גארד…' → basketball) is nearly isomorphic to C2's title.

### RC-3 — Coverage gaps in deterministic evidence (the enabler of RC-2)

- `source_hints.py`: Israel Hayom `/sport/israeli-soccer/` missing (C3's URL evidence was ignored); **walla has no hints at all** (C2/C4/C6 all walla/ynet-generic).
- `_FOOTBALL_CTX_KW` misses transfer-market vocabulary ("דמי מעבר", "עסקת העברה") — C2's subtitle had football-typical content, zero matched keywords.
- Negotiation keywords miss "על סף סיכום" (C9).
- Taxonomy: no Budućnost (C15), no relevant players (LeDay, Bruno Fernando, Holmes, Paris Lee), no nickname strategy ("הצהובים", C13).

### RC-4 — Background-mention competition promotion

**Cases:** C10, C12. The explicit competition scan makes any competition-name mention `primary_competition`, including "leaving the NBA" and "king of steals *in the EuroLeague*". Same "presence = fact" pattern as RC-1, at lower severity (decisions stayed reasonable).

### RC-5 — Profile scope coverage (distinct layer)

**Case:** C9 downstream. Guy has no low-level `sport:basketball` floor, so under-resolved basketball articles vanish entirely. Not an engine bug — a relevance-layer product decision — but it converts every upstream extraction miss into total invisibility.

---

## 5. Cross-case comparisons

### A. Maccabi Tel Aviv cross-sport ambiguity

The ambiguity machinery itself (resolver abstention, `ambiguous_club`, guarded entities) is consistent and correct in all compared cases. Divergence is decided entirely by **which disambiguating evidence happens to exist**:

| Case | Disambiguating evidence | Outcome |
|---|---|---|
| C11, C14 | ynet URL hint (weight 100) | correct basketball |
| C8 | one subtitle word "קשר" (weight 60) | correct football |
| C2, C3 | nothing explicit → LLM guess → RC-2 lock-in | **wrong basketball** |
| C13 | bare "מכבי" + nickname → by-design abstention | no Maccabi tag (missed push) |

Pipeline order matters only in the nothing-case; subtitle evidence is decisive in C8/C9; competition evidence decided none of them. One mechanism (evidence scarcity → LLM last resort → echo lock-in) is consistently responsible for the failures.

### B. Championship/title language

The discriminator is *where* the champion word sits relative to the title-primacy rule: C11's title already carried `signing`, so its subtitle's "האלופה" was never scanned; C2-sib/C4/C5/C6/C7 had event-less titles, so the subtitle (or a competition name in the title) supplied the event. The existing hardening (`RSS_QUALITY_GUARDRAILS.md` §8d) fixed win-*verbs* but deliberately kept champion-*nouns* as standalone evidence — and `tests/test_event_evidence.py` encodes "ניו יורק אלופת ה-NBA" (a genuine title win) as valid, which is exactly the minimal pair any fix must preserve: **"אלופת ה-NBA" as predicate (valid) vs "מתקרב לאלופת איטליה" as epithet (invalid).**

### C. Transfer-related event types

signing/negotiation/candidate distinctions are implemented consistently and reasonably well (blockers prevent negotiation→signing; C10/C11/C15 signing confirmed; C12/C13 negotiation; C3's `negotiation` right even with wrong sport). The gaps are lexical ("על סף סיכום", "סגרו עם"), and the C14 "success" shows the news/negotiation boundary is keyword coverage, not semantics. Ordering: `title_win` outranking negotiation (C5) is the one genuinely wrong precedence.

### D. Competition resolution

Explicit competition keywords are high-precision for *sport* but not for *aboutness* (C10, C12). Membership reach is doing most of the real personalization work (C13, C15 — EuroLeague/EuroCup "recognition" is memberships, not text), correctly tempered by the feed ceiling. `primary_competition` should be read as "a competition mentioned", not "the competition this event happened in" — the docs' framing is honest about this, but the Debug UI's presentation ("EuroLeague · negotiation") over-claims.

### E. Title vs subtitle

The gap-fill contract (subtitle fills, never overrides) is coherent for **sport** (C8, C9, C10, C15 all correct via subtitle) but is **inverted in effect for events**: precisely because subtitles are only consulted when the title is event-less, low-signal subtitles decide the event for feature-ish titles — the entire RC-1 failure surface. Sport uses weighted title>subtitle evidence in the facts stage; **events have no equivalent weighting** — a subtitle event and a title event are indistinguishable downstream.

---

## 6. What is already working well (preserve these)

- **Weighted sport-evidence resolution with explicit-beats-derived** (`facts.py`) — C9's override of a wrong LLM sport is the design working perfectly.
- **Abstention machinery**: family names, cross-sport aliases, guarded entities, `sport=unknown` (C5-walla abstained honestly; no bare "מכבי" ever resolved wrongly in any case).
- **Guardrail 4b / post-facts event validation** — rejected LLM `release` (C2-sib) and unsupported LLM `negotiation` (C9); LLM `title_win` cannot enter without text evidence. **All observed false `title_win` came from rules, none from the LLM.**
- **Title-primacy for events** (protects C11) — keep the primacy, fix what subtitle evidence may claim.
- **URL hints where mapped** — anchored every ynet/sport5 success (C11, C12, C13, C14).
- **Membership reach + feed ceiling + participant inference** — delivered C13/C15 sensibly; participant inference implicated in zero failures.
- **Preference V2 engine** — executed every profile faithfully; Deni fan protected on all 15; push only via explicit overrides.
- **Trace quality** — every one of the 15 cases was fully diagnosable from persisted traces alone.

---

## 7. Architecture assessment

**Fundamentally sound, locally inconsistent in two places.** Responsibilities are clear and real: classifier proposes, gate economizes, merge arbitrates with guardrails, facts enforces the triangle and traces, relevance matches without re-deriving visibility. Two violations of the system's own stated principles:

1. *"The LLM reduces uncertainty; it does not define truth"* (`facts.py` header) is violated by the enrichment→`entity_derived` laundering path (RC-2) — a pipeline-order/provenance bug, not a design flaw.
2. *"Specific non-news events are accepted only with positive evidence"* (`event_evidence.py`) is implemented as *lexical presence*, which is not evidence of an event assertion (RC-1).

**Stale/misleading docs:** `RSS_QUALITY_GUARDRAILS.md` §8d presents `title_win` as "hardened" (only verbs were; the champion-noun path was left open — the corpus proves it), and `tests/test_event_evidence.py` canonizes the champion-noun-suffices rule as a positive test.

---

## 8. Recommended technical direction

The smallest structurally sound package — four changes inside existing components, no resequencing, no redesign:

1. **Event-assertion semantics for championship/result events** (`signal-classification-change` scope). Champion nouns stop being standalone evidence: require an assertion pattern (champion noun as predicate of the article's subject, or noun + crowning/win verb), add Hebrew aspiration/epithet blockers ("לזכות ב", "בדרך ל", definite-epithet "האלופה", "אלופת ה[country/world]" adjacent to a different subject), and **exclude spans already claimed by the competition scanner** ("אלוף האלופים", "ליגת האלופות") from event evidence — the scanner already knows how to claim spans. Reorder proposals so transfer-cycle evidence outranks `title_win` when both fire. Give subtitle-sourced events lower certainty (probable, never confirmed) and stop auto-`very_high` for non-confirmed title_win. Harden `finals_result`'s bare "גמר" similarly (require result/stage context).
2. **Break the LLM echo** (facts/merge). Tag enrichment-injected entities with provenance; `entity_derived` sport evidence must not count when the entity's resolution was itself derived from the LLM proposal. For `ambiguous_club` articles where the *only* sport evidence is the LLM, persist sport with abstaining entity treatment (family-mention, no `team:*` id) — visibility abstention beats a false push. Additionally, allow LLM "news" to challenge a *subtitle-derived* rules event in guardrail 4 (title-derived rules events keep priority).
3. **Evidence-coverage fixes** (small, parallel): add Israel Hayom `/sport/israeli-soccer/` + audit all category maps (walla is entirely unmapped — check whether its URLs carry categories); add transfer-market football vocabulary ("דמי מעבר", "עסקת העברה") to football context; add "על סף סיכום" to negotiation; taxonomy: Budućnost, the handful of relevant players, and register "הצהובים" as a **shared** alias of both Maccabi TLV entities so the existing ambiguity machinery handles it (`signal-taxonomy-change`).
4. **Product decision at the relevance layer** (`signal-relevance-change`, optional but recommended): give Guy a level-0 `sport:basketball` floor so under-resolved basketball lands at low_feed instead of vanishing (C9), and revisit whether `news` should get membership reach at a low tier. Keep the Deni profile untouched.

Explicitly *not* recommended now: changing pipeline order, replacing the LLM provider (worth evaluating separately — qwen2.5:3b plus a basketball-skewed few-shot prompt is a measurable liability), or any event-type taxonomy change.

---

## 9. Regression strategy (the 15 cases, at the right levels)

| Level | File(s) | Cases |
|---|---|---|
| Event-evidence unit | `test_event_evidence.py` | C1, C2-sib, C4, C5, C6, C7 as invalid-title_win; minimal pair "ניו יורק אלופת ה-NBA" (stays valid) vs "מתקרב לאלופת איטליה" (invalid); synthetic UCL headline; C9's "על סף סיכום"→negotiation |
| Classifier title+subtitle | `test_ingestion_classifier.py` / `test_quality_regressions.py` | C8 (football via subtitle), C11 (subtitle champion word harmless), C13 (Partizan + no false Maccabi), C14 (stays news), C15 (Hapoel JLM from subtitle), C5-walla (honest abstention) |
| Facts/merge | `test_article_facts.py` | C2/C3 as "LLM-only evidence must not lock cross-sport entity"; C9 as weighted-override-works; C10 as background-mention (once RC-4 addressed) |
| Source hints | `test_source_hints.py` | israeli-soccer → football |
| End-to-end feed decision | extend `TestGuyPositiveCasesQA`/`Negative` in `test_quality_regressions.py` | all 15 as real title+subtitle pairs run through classify→facts→`score_article_v2` for **both** profiles, asserting decision levels |

Key principle: **land the 15-case golden module first, with current-behavior expectations marked xfail for the 9 failures** — that pins the positives before any change and turns each fix into flipping an xfail.

---

## 10. Corpus replay / verification plan

The repo already has the needed tooling — no new infrastructure: `POST /api/classify/backfill` (re-classify persisted Hebrew-source articles), `GET /api/ingest/quality`, `GET /api/debug/feed/{user}`, the shadow service, and the `signal-real-data-qa` skill encodes the procedure. Concretely:

1. Snapshot the 327-article corpus: facts fields + per-profile decisions (guy, casual_deni_fan) to JSON.
2. Apply changes; run backfill twice (LLM enabled / `CLASSIFICATION_PROVIDER=disabled`) to measure LLM dependency.
3. Diff and review:
   - sport flips (each reviewed by hand — expect <20),
   - `sport_unknown` rate,
   - entity precision on flipped rows,
   - `title_win` count (**expect 17 → ~2**), `finals_result` count, full event distribution,
   - hidden↔visible transitions per profile,
   - Guy push count (expect 4 → 1 on the 15; corpus-wide pushes must all trace to explicit overrides on true facts),
   - Deni profile decisions (expect **zero** changes),
   - `docs/fixtures/profile_parity.json` unchanged.

---

## 11. Implementation sequence

1. **Stage 0 — regression pinning** (no behavior change): golden-15 module + corpus snapshot. Safe checkpoint.
2. **Stage 1 — RC-3 mapping fixes** (hints, keywords, taxonomy entries): lowest risk, independently verifiable, immediately removes the C3 class. Parallelizable with Stage 2.
3. **Stage 2 — RC-1 event semantics**: the highest-impact change; verify with corpus replay (title_win/finals distribution + positive-case protection).
4. **Stage 3 — RC-2 provenance fix** in facts/merge: independent of Stage 2 but subtler; do after it so replay diffs are attributable.
5. **Stage 4 — relevance-layer decisions** (Guy basketball floor, C9): only after facts are trustworthy, so the floor doesn't amplify noise.
6. **Stage 5 — optional**: RC-4 aboutness for competitions; LLM provider/prompt evaluation.

---

## 12. GitHub structure recommendation

One **epic: "Classification & Feed Reliability"** (label like `reliability`) — sized between a bug and a milestone — with six issues mirroring the stages. Not part of the User Platform milestone: separate concern, separate verification.

| # | Issue | Scope | Depends on | Blocking? |
|---|---|---|---|---|
| 1 | Golden-15 regression corpus + snapshot tooling | tests only | — | blocks all others (verification substrate) |
| 2 | Event-evidence assertion semantics (champion language, finals, ordering, subtitle certainty) | `event_evidence.py`, `classifier.py` | 1 | blocking (core) |
| 3 | Break LLM-echo circularity (enrichment provenance, facts weighting, G4 asymmetry) | `facts.py`, `merge.py`, `ingestion_service.py` | 1 | blocking (core), parallel with 2 |
| 4 | Source-hint + keyword + taxonomy coverage audit (israeli-soccer, walla, transfer vocab, Budućnost, "הצהובים") | `source_hints.py`, keyword sets, `taxonomy/` | 1 | parallelizable, small |
| 5 | Corpus replay QA gate + title_win/push metrics in run metrics | scripts/API | 2, 3, 4 | sign-off gate |
| 6 | Relevance follow-up: Guy `sport:basketball` floor + news-reach decision | seed profiles, engine | 5 | parallelizable, product decision |

Verification per issue: the named xfails flip + replay diff clean.

---

## 13. User Platform sequencing decision — **Option C: continue to a checkpoint**

Current state: Epic #48, PR 1/issue #49 (auth core) merged; #50–#55 open.

- **Continue now**: PR 2 (`/api/me/*` backend), PR 3 (frontend auth shell), PR 5 (admin gating). These touch `users`/`auth_sessions`/AppContext — zero file overlap with classification code, and pausing them creates rework risk for no benefit. Reliability work proceeds **in parallel** on a different subsystem.
- **Checkpoint before PR 4 (onboarding)**: PR 4 routes every *new* user through Calibration V2 → inference → event affinities. Calibration inference and feedback learning both key off event-type and scope semantics; onboarding users onto a feed that pushes ticket-sales articles as title wins both burns first impressions and lets the learning layer encode adjustments against false facts (learning attribution is trace-based). Gate PR 4 on the §14 criteria. PR 6/7 follow their existing dependency chain.
- **Not option A (full pause)**: the auth plumbing is genuinely independent, and the existing plan already marks PR 4 as a review checkpoint — this gate slots in naturally.

---

## 14. Go/no-go criteria (reliability considered "controlled")

1. All 15 cases encoded as tests at the levels in §9; 9 failures fixed, 6 positives green; the champion-language minimal pair both passing.
2. Corpus replay clean: `title_win` rows reduced to genuinely-true instances (manual audit of the residue); `finals_result` bucket audited; no positive-case or `profile_parity.json` drift; **zero** decision changes for `casual_deni_fan`.
3. Push discipline restored end-to-end: every push in replay traces to an explicit override **on facts a human confirms** — for these 15, exactly one push (C11).
4. Invariant made auditable: no persisted cross-sport club entity whose sport evidence is solely LLM-derived (expressible as a trace query / run metric).
5. Source-hint coverage measured per source; `/sport/israeli-soccer/` verified live.
6. The C2/C8 pair (same story, two vendors) classifies identically.

---

## Appendix: verified reproductions

- `_detect_event_evidence` on C1's subtitle → `title_win, valid, confirmed` (via `"זכו" ⊂ "לזכות"` + "באליפות").
- C4 title, C5-ynet subtitle, C2-sib subtitle → all `title_win, valid, confirmed`.
- Synthetic "ריאל מדריד תארח את ליברפול בליגת האלופות" → `title_win`, importance `very_high`, sport `unknown`.
- C11 full `classify()` with hint → `basketball / signing / Maccabi Tel Aviv Basketball / Israeli Basketball League` (subtitle "האלופה" never consulted).
- C9 title → `news` (negotiation phrase gap confirmed).
- Corpus event distribution: news 128, finals_result 62, signing 37, negotiation 24, match_result 23, **title_win 17** (15 of the 17 titles are visibly not title wins), others small.
- Offline `score_article_v2` replay for both profiles matches every screenshot decision (table in §3).
