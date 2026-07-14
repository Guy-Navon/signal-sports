# #122 / #132 — Pairwise Diagnostic and Mechanism Analysis

**Analysis only. No threshold was changed. No code was modified. All measurements read-only against the 257-article live corpus (2026-07-14).**

Requested before any matcher implementation. The headline result:

> **Both issues, as written, are aimed at the wrong things — and one of them is currently a no-op.**
> The real defect is that the matcher has **no story-identifying signal**. The token that *names the subject of the story* is invisible to every channel we have.

---

## 1. Pairwise diagnostic — the five duplicate groups

Hard gates (cross-source, event-state, in-play, time window, cross-sport) are enforced throughout. `J` = Jaccard (production metric), `C` = containment `|A∩B| / min(|A|,|B|)`, `disc` = discriminative shared tokens under the production DF model.

### `dup_madar_signing_push` — signing, 3 articles, all PUSH

DF universes: corpus **257** · production window (±48h) **257** · event-scoped (±24h) **215**

| # | source | published | tokens | title |
|---|---|---|---|---|
| 1 | ynet | 07-12 06:46 | 37 | ים מדר חתם במכבי ת"א: "מבטיח לתת את הכל" |
| 2 | sport5 | 07-12 08:55 | 25 | היקר בתולדותיה: ים מדר חתם רשמית במכבי ת"א |
| 3 | walla | 07-12 09:33 | 16 | מכבי ת"א הציגה את ים מדר: "פותח פרק חדש" |

| pair | Δt | tier | \|A\| | \|B\| | ∩ | ∪ | **J** | floor | **C** | rejection | disc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1~2 | 2.2h | A | 37 | 25 | 5 | 57 | **0.09** | 0.30 | 0.20 | `below_threshold` | — |
| 1~3 | 2.8h | A | 37 | 16 | 5 | 48 | **0.10** | 0.30 | 0.31 | `below_threshold` | `פרק` |
| 2~3 | 0.6h | A | 25 | 16 | 5 | 36 | **0.14** | 0.30 | 0.31 | `below_threshold` | `יאללה` |

Tokens shared by **all** members (non-generic): `מדר`, `המעבר`.

| token | df corpus | df ±48h | df ±24h | discriminative? |
|---|---|---|---|---|
| `מדר` | 13 | 13 | **13** | ❌ **False** |
| `המעבר` | 12 | 12 | 11 | ❌ False |

### `dup_hankins_release` — release, 4 articles

| # | source | published | tokens | title |
|---|---|---|---|---|
| 1 | israel_hayom | 07-13 06:35 | **40** | בדרך לרכש כפול: מכבי תל אביב נפרדה מאחד משחקניה |
| 2 | ynet | 07-13 07:07 | 22 | מכבי ת"א נפרדה מזאק הנקינס: "שותף חשוב לדאבל" |
| 3 | sport5 | 07-13 08:39 | **13** | לאחר עונה אחת: מכבי ת"א נפרדה מהנקינס |
| 4 | walla | 07-13 09:34 | 23 | מכבי תל אביב נפרדה מזאק הנקינס: "שותף חשוב בדאבל" |

| pair | Δt | tier | \|A\| | \|B\| | ∩ | ∪ | **J** | floor | **C** | rejection | disc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1~2 | 0.5h | A | 40 | 22 | 6 | 56 | 0.11 | 0.30 | 0.27 | `below_threshold` | `הנקינס`, `נפרדה`, `שהצטרף` |
| 1~3 | 2.1h | A | 40 | 13 | 3 | 50 | **0.06** | 0.30 | 0.23 | `below_threshold` | `נפרדה` |
| 1~4 | 3.0h | A | 40 | 23 | 6 | 57 | 0.11 | 0.30 | 0.26 | `below_threshold` | `הנקינס`, `נפרדה` |
| 2~3 | 1.5h | A | 22 | 13 | 4 | 31 | 0.13 | 0.30 | 0.31 | `below_threshold` | `חלק`, `נפרדה` |
| 2~4 | 2.4h | A | 22 | 23 | 9 | 36 | **0.25** | 0.30 | **0.41** | `below_threshold` | `דצמבר`, `הנקינס`, `חשוב`, `מזאק`, `נפרדה`, `שותף` |
| 3~4 | 0.9h | A | 13 | 23 | 3 | 33 | 0.09 | 0.30 | 0.23 | `below_threshold` | `נפרדה` |

`הנקינס` (df=3) and `נפרדה` (df=5) **are** discriminative. The evidence is fine. Pair 2~4 is a near-verbatim headline match and still fails at J=0.25.

### `dup_otooru_extension` — signing, 3 articles

| pair | Δt | tier | ∩ | **J** | **C** | rejection | disc |
|---|---|---|---|---|---|---|---|
| 1~2 | 1.6h | A | **2** | 0.05 | 0.13 | `below_threshold` | `אוטורו` |
| 1~3 | 2.8h | A | 7 | 0.17 | 0.29 | `below_threshold` | `אוטורו`, `לשלוש`, `נוספות` |
| 2~3 | 1.1h | A | **2** | 0.05 | 0.13 | `below_threshold` | `אוטורו` |

Two outlets reporting the same contract extension share **2 tokens**.

### `dup_storonski` — negotiation/signing, 3 articles

Tokens shared by **all** members: **`[]` — empty.**

| pair | Δt | **J** | rejection |
|---|---|---|---|
| 1~2 | 0.9h | 0.04 | `below_threshold` |
| 1~3 | 1.5h | 0.08 | **`event_state_incompatible` (negotiation/signing)** |
| 2~3 | 0.6h | 0.07 | **`event_state_incompatible` (negotiation/signing)** |

The player's name is **spelled two different ways**: `סטורנסקי` (ynet, walla) vs `סטרונסקי` (sport5). And the three sources **disagree about the event state**.

### `dup_madar_farewell` — 3 articles

| pair | Δt | tier | **J** | floor | **C** | rejection | disc |
|---|---|---|---|---|---|---|---|
| 1~2 | 1.9h | A | **0.31** | 0.30 | **0.59** | **`event_state_incompatible` (signing/news)** | 8 tokens |
| 1~3 | 2.7h | C | 0.14 | 0.35 | 0.25 | **`event_state_incompatible` (signing/news)** | 4 tokens |
| 2~3 | 0.9h | C | 0.14 | 0.35 | 0.29 | `below_threshold` | `מורם`, `נפרד`, `עוזב` |

Pair 1~2 **passes every similarity and evidence bar** (J=0.31 ≥ 0.30, C=0.59, 8 discriminative tokens) and is rejected **only** because ynet called it `signing` and sport5 called it `news`.

---

## 2. Finding 1 — #122's leading hypothesis is REFUTED

> *"A saga token is common across weeks yet rare within the neighbourhood where the merge decision is made."*

**Measured: false.**

`df(מדר)` = **13** in the corpus, **13** in the production ±48h window, **13** in a ±24h window.

The Madar saga is **not spread over weeks**. All 13 articles fall inside ~25 hours (07-11 20:05 → 07-12 20:58). The saga *is* the story's own news cycle, compressed into a single day. **No temporal scoping, decay, or recency weighting can separate them** — there is no time axis along which they differ.

Any fix built on time-scoped DF is dead on arrival.

## 3. Finding 2 — #122's fix is currently a NO-OP

Gate order is: … → **7. Jaccard floor** → **8. discriminative evidence**.

All three Madar pairs are rejected at step **7**. They never reach the evidence gate. So the DF failure is **masked**.

Proof — raising `max_story_coverage` (the *forbidden* version of the fix), Jaccard floor kept:

| `max_story_coverage` | true pairs merged | over-merges |
|---|---|---|
| 6 (current) | **15/31** | 0 |
| 13 | **15/31** | 0 |
| 20 | **15/31** | 0 |

**Identical.** Even deliberately breaking the rule changes nothing.

**Consequence for the issue plan:** #122 and #132 are **not co-equal siblings**. The similarity failure is the **binding constraint** on Madar, Hankins *and* Otooru. #122's fix is unobservable until a similarity change lands, and must not be credited or judged on its own.

## 4. Finding 3 — bag-of-words similarity is the wrong instrument

True near-duplicates from different Israeli outlets score **J = 0.04–0.31**. That is squarely inside the noise band. Two outlets reporting the same signing share **2–5 tokens**, because each writes a genuinely different sentence and adds its own angle (`היקר בתולדותיה`, `הצהרת כוונות`, `ללא סעיף יציאה`, `נחשף ב-ynet`).

Jaccard additionally divides by the **union**, so it punishes length divergence (#132): israel_hayom's 40-token article — whose subtitle appends an *unrelated story* — caps at `13/40 = 0.32` against sport5's 13 tokens even on a perfect subset.

**No threshold on this metric separates signal from noise**, because the true positives *are* in the noise band.

## 5. Finding 4 — the DF model conflates *rare* with *story-identifying*

Evidence-primary (Tier A, ≥1 discriminative shared token, no Jaccard floor) scores **27/31** on fixtures with **zero** fixture over-merges — and is a **disaster** on the real corpus: **21 new merges over 2,922 eligible pairs**, carried by:

| "discriminative" token | what it actually is | damage |
|---|---|---|
| `לשלוש`, `נוספות` | *"for three more [years]"* — contract-extension **template** | merges **Bryant's** extension with **Otooru's** |
| `סיכם` | *"agreed"* — **template** | merges two different players' agreements |
| `דולר` | **"dollar"** | merges Madar's signing with an unrelated EuroLeague star |
| `איטודיס` | **the coach's name** | merges unrelated club stories |
| `יאללה`, `פרק` | **"yalla"**, **"chapter"** | right answer, absurd evidence |

The model is **exactly backwards on the cases that matter**:

- `מדר` — the token that literally **names the subject** — is **not** discriminative (df=13).
- `יאללה` **is** (df=2).

The **Jaccard floor has been silently doing the precision work all along.** That is why the baseline has 0 over-merges but only 15/31 recall. Removing it exposes how weak the evidence model is.

> ⚠️ Note the trap: the fixture corpus has only **4** must-not-cluster pairs surviving the hard gates. Evidence-primary scores **zero over-merges** there. It takes **2,922 real pairs** to see that it is catastrophic. **The fixture negatives are far too thin to certify any mechanism.** This is exactly the caution recorded on #126.

## 6. Finding 5 — the story-identifying signal is missing from *every* channel

Every **correct** merge in the corpus shares a **name**. The one over-merge shares only a **template**:

| C | disc evidence | verdict |
|---|---|---|
| 0.47 | `יבנה` | ✅ murdered ex-player (walla ~ sport5) |
| 0.41 | `הנקינס`, `מזאק` | ✅ Hankins |
| 0.36 | `רקנאטי`, `שטילמן` | ✅ ownership row |
| 0.35 | `בראיינט` | ✅ Bryant extension |
| 0.32 | `אנדרדה` | ✅ plea-deal ruling |
| **0.31** | **`במו`, `בשיחות`** | ❌ **OVER-MERGE** — Wheeler↔Eilat + Holon↔two players |
| 0.31 | `פרק` / `יאללה` | ✅ Madar — right answer, **no name in the evidence** |

So: **can we use the resolved entity set instead of a lexical proxy?**

**No — the taxonomy cannot see these people.**

| | |
|---|---|
| corpus articles | 257 |
| articles with **any** player entity | **3 (1%)** |
| every player entity resolved, corpus-wide | `player:lebron_james` (2), `player:deni_avdija` (1) |

**Not one Israeli-league player resolves.** Not Madar, not Hankins, not Otooru, not Storonski. The only entity these articles carry is the **team** (`team:maccabi_tlv_bb`) — far too coarse, since *every* Maccabi story shares it. That coarseness is precisely what puts these pairs in Tier A and what lets formulaic templates over-merge.

**The person at the centre of the story is invisible to the df model *and* to the taxonomy.**

## 7. Candidate mechanisms — measured effect

Fixture recall is over 31 eligible true-duplicate pairs. Over-merges are measured **corpus-wide** (2,922 eligible pairs), which is the only measurement that has proven able to falsify anything.

| mechanism | fixture recall | corpus over-merges | verdict |
|---|---|---|---|
| **M0** baseline (Jaccard + DF evidence) | 15/31 | **0** | precise, blind |
| **M1** containment ≥ 0.30 (evidence unchanged) | 21/31 | **1** | ⚠️ Wheeler/Holon template |
| **M1** containment ≥ 0.35 | 18/31 | **0** | ✅ safe, but loses **all Madar** and 2 of 3 Hankins pairs |
| **M2** evidence-primary, ≥1 disc token, no Jaccard | 27/31 | **21** | ❌ **catastrophic** |
| **M2** evidence-primary, ≥2 disc tokens | 19/31 | **8** | ❌ still bad |
| **M4** raise `max_story_coverage` (#122's fix) | **15/31** | 0 | ⛔ **NO-OP** |
| **M5** containment ≥ 0.30 **+ state-scoped DF** | 21/31 | **1** | ⭐ same merges as M1, but **for the right reasons** |

### State-scoped DF — the one genuinely new mechanism

Compute DF **within the candidate set the gates already define** (same event state + same window), not over raw time. This is *not* a temporal cliff — it reuses gates that already exist.

`מדר` has df=13 because it identifies a **topic** spanning several *distinct stories* (farewell, signing, shirt number, fixture). The gates already separate those. Within the "signing articles in this window" universe:

| token | df raw | **df state-scoped** | discriminative? |
|---|---|---|---|
| `מדר` | 13 ❌ | **4** | ✅ **True** |
| `חתם` ("signed") | 17 ❌ | 8 | ❌ False *(correctly — it is a template word)* |
| `אוטורו` | 4 ✅ | 3 | ✅ True |

Under M5 the Madar pairs merge carrying **`מדר`** as evidence — the right answer for the **right reason** — instead of `יאללה`.

**But state-scoped DF does not kill the formulaic over-merge.** `במו` / `בשיחות` are *also* state-scoped-rare. The Wheeler/Holon merge survives every mechanism above.

## 8. Negative cases that could become over-merges

Concrete, from the real corpus. Any proposed fix must be tested against these, not just against the 7 fixture groups.

1. **The formulaic negotiation template** (⚠️ *survives every mechanism tested*)
   `מצפון לדרום? ארון ווילר במו"מ עם אילת` ~ `כולל שם מוכר מליגת העל: הפועל חולון במו"מ עם שני שחקנים`
   C=0.31, shared evidence = `במו`, `בשיחות`. **Two different negotiations, different clubs, different players.** This is the `fp_formulaic_template` class, and containment lets it through.

2. **The contract-extension template**
   Bryant's extension ~ Otooru's extension, on `לשלוש` + `נוספות` ("for three more"). Same club, same week, **different players**.

3. **The coach as a bridge** — `איטודיס` links unrelated Hapoel stories.

4. **Money vocabulary** — `דולר` links Madar's signing to an unrelated EuroLeague star.

5. **Short-inside-long** — containment is asymmetric by construction (`C ≥ J` always). A terse headline whose tokens are a subset of a long article scores C=1.0. Needs its own floor, argued from the FP corpus — **not inherited from Jaccard's**.

## 9. Conclusions and recommended restructuring

1. **#122's stated hypothesis (time-scoped DF) is refuted.** Replace it. The saga is compressed into 25 hours; there is no time axis to exploit.
2. **#122's fix is currently a no-op** and cannot be judged until a similarity change lands. It must not be credited with any merge on its own.
3. **The binding constraint is similarity** (#132), on Madar, Hankins *and* Otooru.
4. **Containment alone is not sufficient** and buys one real over-merge at the floor where Madar becomes reachable.
5. **State-scoped DF is the correct form of #122's idea** and should replace its current hypothesis. It restores `מדר` as evidence without any threshold change, and correctly *keeps* `חתם` non-discriminative.
6. **The missing primitive is a person/proper-noun signal.** Every correct merge shares a name; every dangerous over-merge shares only a template. Neither the df model nor the taxonomy (1% player coverage) can currently see the person at the centre of the story. **This is a new, unfiled root cause and is likely the highest-value fix in the milestone.**
7. **Two further root causes are exposed and unfiled:**
   - **Transliteration variance** — `סטורנסקי` vs `סטרונסקי` gives Storonski **zero** shared tokens. No similarity metric or DF scheme repairs that.
   - **Cross-source event-state disagreement** — Madar-farewell pair 1~2 passes *every* similarity and evidence bar (J=0.31, C=0.59, 8 discriminative tokens) and is rejected **solely** because ynet said `signing` and sport5 said `news`. Same for two Storonski pairs (`negotiation` vs `signing`). This is a **classification-consistency** defect in the #113 family, not a clustering defect.
8. **The fixture negative corpus (4 eligible pairs) cannot certify any mechanism.** Corpus-wide pair enumeration (2,922 pairs) must be part of #124's metrics and #126's activation gate.
