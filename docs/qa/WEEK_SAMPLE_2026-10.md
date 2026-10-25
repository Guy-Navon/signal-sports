# Seven-day blind sample for #256 (2026-10-25)

A fresh rating base for the Israeli-basketball recall work (#256 → #259, and #345). The goal is
to stop re-measuring the same few known articles. Built by
[`backend/scripts/build_week_sample.py`](../../backend/scripts/build_week_sample.py), seed
`20261025`. **The id lists in the JSON files are the authority**: a re-run would read today's
sitemaps, which change.

- Random sample: [`week_sample_2026-10.json`](week_sample_2026-10.json), 105 articles
- Focused #345 set: [`focused_345_2026-10.json`](focused_345_2026-10.json), 30 articles
- Ratings go to `week_sample_2026-10_ratings.json` and `focused_345_2026-10_ratings.json`
  (separate files, separate metrics)

## Days and coverage (Israel time)

The worker did not run from 2026-10-15 20:46 to 2026-10-25 04:55. The corpus has no ingest
timestamp; ingest time is inferred from `ingestion_runs`, which have no run in that gap.

| Day | Origin | Unique candidates (by source) | Sampled (by source) |
|---|---|---|---|
| 10-12 | corpus (worker 24 h) | 147 | IH 5, Ynet 5, Walla 5 |
| 10-13 | corpus (24 h) | 145 | Walla 10, Ynet 3, IH 2 |
| 10-14 | corpus (24 h) | 120 (IH 40, Walla 60, Ynet 19, Sport5 1) | Walla 9, IH 6 |
| 10-19 | archive | 111 (Walla 72, IH 39) | Walla 11, IH 4 |
| 10-21 | archive | 116 (Walla 72, IH 44) | Walla 9, IH 6 |
| 10-22 | archive | 92 (Walla 55, IH 37) | Walla 8, IH 7 |
| 10-24 | archive + corpus | 106 (Walla, IH, Ynet, Sport5) | Walla 6, IH 6, Ynet 3 |

The three corpus days are the most recent days the worker covered 24 hours (10-11 to 10-14 are
the only such days). The four archive days are the ones the owner chose.

**Source mix is not the production mix on 10-19, 10-21 and 10-22.** Those days have no Ynet
and no Sport5. Ynet's news sitemap and Sport5's news sitemaps list only the last two days, and the
Wayback Machine holds no feed snapshot for the week. In production Ynet is about 15% of a day and
Sport5 about 5%. Walla and Israel Hayom volumes in the sitemaps (55–72 and 37–44 a day) match
what their feeds deliver.

## How an archive day is built

1. **Candidates.** Walla `sitemap/3/1-history.xml` (`/item/<id>` pages). Israel Hayom
   `sitemaps/website/*.xml`, filtered to `/sport/…/article/` as the source config filters.
   For 10-24, Ynet's news sitemap (`/sport/` only) and the corpus rows of that day are added, so
   articles the feed did deliver are not missed. A candidate's day is its sitemap `lastmod` in
   Israel time.
2. **Exclusions.** Every id in a `docs/qa/*.json` file is excluded (1,417 ids: all ratings, all
   samples, the bake-off report), plus the #345 and bake-off investigation rows. **0 candidates
   were excluded**: nothing from these days had been rated.
3. **Dedup.** Same URL means same id (`article_id_from_url`, as ingestion does). Same title under
   a second URL is skipped. Cross-source stories about the same event stay separate, as they do
   in production before clustering.
4. **Seeded order, then verification.** The day's candidates are shuffled with
   `seed:day`. Each sampled article's page is fetched, and it is kept only if its own published
   time falls on that day. Otherwise the next candidate is taken. 3 were replaced this way
   (published the day before; recorded in `meta.coverage`). An article published on a day and
   modified on a later one is missing from its day: a known, small bias of using `lastmod`.
5. **Text, from where the feed takes it.** Walla: the lead paragraph (`article_speakable`), which
   matches the RSS description exactly on a checked article. Israel Hayom: `description`, which
   matches its RSS subtitle. Ynet: `description`. Titles: `og:title` without the site suffix.
6. **Before the gate.** Every candidate is eligible, whatever the LLM gate would do. Items that
   ingestion would drop before storage (URL or language filters) are not candidates, because the
   corpus never stores them either.

83 requests went to the source sites, one a second. Nothing was written to the corpus or the
live feed; no notification can follow from this.

## Split, fixed before rating

Each day's 15, in seeded order: the first 10 are `dev` (analysis), the last 5 are `test` (the
final check). That is 70 / 35, with every day in both. **`test` is not looked at until a change is
defined.** The rating order is shuffled again, so neither day nor source nor split shows.

**Is 105 enough?** Not known yet. Census #2 had 138 wanted (feed or better) of 804 (17%). At that rate, 105
gives about 18 wanted articles, 12 in `dev`, and only a handful of Israeli-basketball misses. If
the ratings confirm that, the next step is a larger draw from the same days with the same rule,
not a looser rule.

## Focused #345 set (separate)

The rule, not a hand pick: unrated articles whose title or subtitle names a dual-sport Israeli
club alias (Maccabi TA, Hapoel TA, Hapoel Jerusalem, Hapoel Haifa, Hapoel Be'er Sheva; the aliases
come from the taxonomy's cross-sport pairs). 10 per stored sport (population: football 265,
basketball 207, unknown 62). It probes the guard in both directions: football Maccabi stories must
stay out of basketball. It says nothing about how often each case occurs, and its metrics are
reported apart from the random sample.

The 7 #345 rows keep their census #2 ratings and serve as regression cases. **Steinberg**
(`rss_3febdca22278e04ceb76`, a new world champion per its subtitle, rated feed) is not a basketball
miss. It is analysed separately, as a possible preference-matching question.

Ambiguous person names are not in the focused set yet. They depend on the candidate list that
the `dev` analysis produces.

## Rating

Same scale as the censuses (5 push, 4 high, 3 feed, 2 low, 1 hide). The page shows title,
subtitle, source, date and a link to the original, and nothing the engine decided:

```
cd backend
.venv\Scripts\python.exe scripts\rate_census.py serve --sample ..\docs\qa\week_sample_2026-10.json --ratings ..\docs\qa\week_sample_2026-10_ratings.json
.venv\Scripts\python.exe scripts\rate_census.py serve --sample ..\docs\qa\focused_345_2026-10.json --ratings ..\docs\qa\focused_345_2026-10_ratings.json
```

## Waits for the ratings

Everything that compares with the owner: misses, false shows, the ranked evidence list. The
counts of cues across the whole corpus (how often a name, a venue, a score pattern or a show name
appears, and next to what) do not depend on ratings and come first.
