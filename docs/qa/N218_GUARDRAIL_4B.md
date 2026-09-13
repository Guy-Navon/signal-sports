# Guardrail 4b — what it rejects, and the one gap worth fixing (#218)

Investigation triggered by a live ingestion on 2026-09-13 (+91 fresh articles),
during which dozens of `Guardrail 4b: LLM event_type X rejected` lines scrolled past.

## The finding

With the LLM now working (3% failure on the fresh cohort, down from 65%), the
event-type bottleneck **moved downstream**. It is no longer that the LLM fails —
it is that its proposals are rejected at merge:

| | fresh cohort |
|---|---:|
| LLM calls | 32 |
| proposal kept | 8 |
| **proposal overridden** | **24 (75%)** |

Dominant transitions: `match_result → news` x5, `analysis → news` x4,
`regular_season_result → news` x2.

This is the same mechanism behind #191's finding that 101 historical rows stored
`news` while the LLM had proposed something else, and it is the coupling flagged
in the review of #217.

## Hand-review: the guardrail is mostly RIGHT

Reading the overridden articles, most rejections are correct:

- `באנגליה החמיאו לדניאל פרץ` — LLM said `match_result`; it is about a signing. Correct.
- `הביקורות על סידני סוויני` — LLM said `analysis`; it is not sports at all. Correct.
- `נתוני המחזור הרביעי` — LLM said `match_result`; it is a preview quoting a past score. Correct.

**Guardrail 4b is doing its job and must not be loosened generally.** #60 built it
to stop false event assertions reaching the preference layer as truth.

## The one systematic gap

Three rejections were plainly wrong, and they share a shape:

- `מנצ'סטר יונייטד - מנצ'סטר סיטי 0:0 (מחצית 1)`
- `חי ממשחק ההכנה: אולימפיאקוס - מכבי תל אביב 35:35 (מחצית)`
- `דקה 36: מנ. יונייטד - מנ. סיטי 0:0`

`match_result` required `_RESULT_VERB` — `ניצח` / `הפסיד` / `beats`. **Hebrew
live-match headlines do not use a verb**; the house style is a bare scoreline. So
the LLM proposed `match_result` correctly and the guardrail rejected it for want of
a verb the genre never uses.

Corpus-wide: **19 titles carry a `TeamA - TeamB N:M` scoreline; 14 were stored as
`news`; 13 of those 14 also carry a live marker** (`חי`, `מחצית`, `דקה N`, `רבע N`).

## The fix, and the restraint in it

A live scoreline now satisfies `match_result` evidence — **but only score AND live
marker together**. The bare number proves nothing: a preview quotes a past
scoreline routinely (`מתרפקת על ה-0:5 מהמפגש הקודם`), which is exactly the false
assertion #60 exists to prevent. The live marker is what separates "this match is
being played" from "here is a number about a past one".

Implemented as one pattern with two lookaheads **inside** the result-verb group,
because `required_any` is AND-across-groups and OR-within-a-group. Adding it as a
separate group would have required verb AND score AND marker, silently breaking
every ordinary result headline. A test pins that structure.

## Measured impact: correctness, not recall

A targeted correction would move **21 stored rows** `news → match_result` and
produce **zero decision flips for either profile** — these are mostly football
(Guy's football scope is level -1 with no `match_result` rule) or basketball
without a matching scope.

**No corpus correction was applied.** There is no decision benefit today, and the
corpus is replay evidence. The fix applies to new ingestion, which is where a
truthful event type will matter — including if live-match coverage ever becomes a
product surface.

## Left alone deliberately

The `analysis` and `interview` rejections were reviewed and mostly look correct
(the LLM reaches for `analysis` on ordinary reporting). Two were arguable. That is
not enough evidence to touch either rule, and event-evidence changes need evidence.
