"""A fresh, blind, seven-day rating sample for #256 (docs/qa/WEEK_SAMPLE_2026-10.md).

15 random unique articles per day, drawn BEFORE the LLM gate from everything a day
published, minus every article already rated or used in an investigation. Each day's
15 are split by the same seed into 10 for analysis ("dev") and 5 for the final check
("test").

Days come from two places:

- ``--db-day``: the corpus, for days the worker covered 24 h. Read-only (``mode=ro``).
- ``--archive-day``: the sources' own public sitemaps, for days the worker missed.
  Walla (``sitemap/3/*-history.xml``), Israel Hayom (``sitemaps/website/*.xml``,
  ``/sport/`` only, as the source config filters) and, while still listed, Ynet's
  news sitemap (``/sport/`` only). A candidate's day is its sitemap ``lastmod`` (Israel
  time); each SAMPLED article's page is then fetched and kept only if its own
  published time falls on that day, otherwise the next candidate in the seeded
  order is taken. Title and subtitle are read where the RSS feed takes them: Walla's
  lead paragraph (``article_speakable``), Israel Hayom's and Ynet's
  ``description``. For an archive day the corpus rows of that day join the
  candidates, so articles the feed did deliver are not missed.

Nothing is written to the corpus or the live feed, and nothing is sent anywhere but
the source sites (one request per second). The output is a census-format sample
that ``scripts/rate_census.py serve`` reads; it carries no engine field.

    python scripts/build_week_sample.py --db-day 2026-10-12 --db-day 2026-10-13 \\
        --db-day 2026-10-14 --archive-day 2026-10-19 --archive-day 2026-10-21 \\
        --archive-day 2026-10-22 --archive-day 2026-10-24 \\
        --out ../docs/qa/week_sample_2026-10.json
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import random
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.ingestion.dedup import article_id_from_url  # noqa: E402

IL = ZoneInfo("Asia/Jerusalem")
PER_DAY = 15
DEV_PER_DAY = 10
SEED = 20261025
UA = "Mozilla/5.0 (compatible; signal-sports-sample/1.0)"
RSS_SOURCES = ("walla_sport", "israel_hayom_sport", "ynet_sport", "sport5_sport", "one_sport")
# Ids named in an investigation without being in a ratings file (#345, the bake-off).
INVESTIGATED = {
    "rss_375649c3d0de48af0673", "rss_3febdca22278e04ceb76", "rss_68fa0c75722c43c5cc65",
    "rss_92201d7c1e9c8c7b5e5b", "rss_9b49212690345a6153da", "rss_ced6e83efda59fa746ee",
    "rss_f47fc2b99dda8605455f", "rss_03b90c13915220ecab72",
}


def il_day(stamp: str) -> str:
    dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IL).date().isoformat()


def excluded_ids() -> tuple[set[str], dict[str, int]]:
    """Every id in a docs/qa ratings or sample file, plus the investigated ones."""
    ids: set[str] = set()
    per_file: dict[str, int] = {}
    for path in sorted(glob.glob(str(REPO / "docs" / "qa" / "*.json"))):
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        found = set(re.findall(r"rss_[0-9a-f]{20}", json.dumps(doc)))
        if found:
            per_file[Path(path).name] = len(found)
            ids |= found
    return ids | INVESTIGATED, per_file


# ── Sources ──────────────────────────────────────────────────────────────────

class Fetcher:
    def __init__(self, delay: float = 1.0):
        self.client = httpx.Client(timeout=20, headers={"User-Agent": UA}, follow_redirects=True)
        self.delay, self.requests = delay, 0

    def get(self, url: str) -> str:
        time.sleep(self.delay)
        self.requests += 1
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.text


def _urls_with_lastmod(xml: str) -> list[tuple[str, str]]:
    out = []
    for block in re.findall(r"<url>(.*?)</url>", xml, flags=re.S):
        loc = re.search(r"<loc>([^<]+)</loc>", block)
        lm = re.search(r"<lastmod>([^<]+)</lastmod>|<news:publication_date>([^<]+)</news:publication_date>", block)
        if loc and lm:
            out.append((html.unescape(loc.group(1).strip()), (lm.group(1) or lm.group(2)).strip()))
    return out


def archive_candidates(fetcher: Fetcher, days: set[str]) -> list[dict]:
    """(source, url, day) from the sitemaps, for the requested Israel days."""
    found: list[dict] = []
    walla = fetcher.get("https://sports.walla.co.il/sitemap/3/1-history.xml")
    for url, lm in _urls_with_lastmod(walla):
        if re.fullmatch(r"https://sports\.walla\.co\.il/item/\d+", url) and il_day(lm) in days:
            found.append({"source": "walla_sport", "url": url, "day": il_day(lm)})
    index = fetcher.get("https://www.israelhayom.co.il/sitemaps/sitemap.xml")
    first = min(days)
    for loc, lm in re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", index):
        if lm[:10] < first:
            continue  # a sitemap untouched since before the first day holds none of them
        for url, ulm in _urls_with_lastmod(fetcher.get(loc)):
            if "/sport/" in url and "/article/" in url and il_day(ulm) in days:
                found.append({"source": "israel_hayom_sport", "url": url, "day": il_day(ulm)})
    ynet = fetcher.get("https://www.ynet.co.il/iphone/json/api/20m/google_site_map/8-2-3-6-538-1208-550-544-4003")
    for url, pub in _urls_with_lastmod(ynet):
        if "/sport/" in url and "/article/" in url and il_day(pub) in days:
            found.append({"source": "ynet_sport", "url": url, "day": il_day(pub)})
    return found


def _meta(page: str, prop: str) -> str | None:
    m = re.search(rf'<meta[^>]+(?:property|name)="{re.escape(prop)}"[^>]+content="([^"]*)"', page)
    return html.unescape(html.unescape(m.group(1))).strip() if m else None


def read_article(fetcher: Fetcher, source: str, url: str) -> dict:
    page = fetcher.get(url)
    title = _meta(page, "og:title") or ""
    if source == "walla_sport":
        title = re.sub(r"\s*-\s*וואלה ספורט\s*$", "", title)
        lead = re.search(r'<p class="article_speakable">(.*?)</p>', page, flags=re.S)
        subtitle = html.unescape(re.sub(r"<[^>]+>", "", lead.group(1))).strip() if lead else _meta(page, "description")
        pub = re.search(r'"datePublished":\s*"([^"]+)"', page)
        published = pub.group(1) if pub else None
    else:
        if source == "israel_hayom_sport":
            title = re.sub(r"\s*\|\s*היום\s*$", "", title)
        subtitle = _meta(page, "description")
        published = _meta(page, "article:published_time")
    if not title or not published:
        raise ValueError("page has no title or published time")
    return {"title": title, "subtitle": subtitle, "published_at": published}


# ── Sampling ─────────────────────────────────────────────────────────────────

def db_rows(db: Path, days: set[str]) -> list[dict]:
    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    rows = []
    for aid, source, url, title, ttitle, subtitle, pub in conn.execute(
        "SELECT id, source, url, title, translated_title, subtitle, published_at FROM articles "
        "WHERE id GLOB 'rss_*' AND published_at >= '2026-10-01'"
    ):
        if source in RSS_SOURCES and il_day(pub) in days:
            rows.append({"id": aid, "source": source, "url": url, "title": ttitle or title,
                         "subtitle": subtitle, "published_at": pub, "day": il_day(pub), "origin": "corpus"})
    conn.close()
    return rows


def pick_day(day: str, candidates: list[dict], excluded: set[str], fetcher: Fetcher | None,
             log: dict) -> list[dict]:
    seen_ids, seen_titles, pool = set(), set(), []
    for c in sorted(candidates, key=lambda c: c["id"]):
        if c["id"] in seen_ids:
            continue
        seen_ids.add(c["id"])
        pool.append(c)
    log["unique_candidates"] = len(pool)
    log["excluded_already_rated_or_investigated"] = sum(1 for c in pool if c["id"] in excluded)
    pool = [c for c in pool if c["id"] not in excluded]
    random.Random(f"{SEED}:{day}").shuffle(pool)
    picked, log["rejected"] = [], []
    for c in pool:
        if len(picked) == PER_DAY:
            break
        if c["origin"] == "archive":
            try:
                c.update(read_article(fetcher, c["source"], c["url"]))
            except Exception as exc:  # recorded, never silent
                log["rejected"].append({"id": c["id"], "reason": f"fetch: {type(exc).__name__}"})
                continue
            if il_day(c["published_at"]) != day:
                log["rejected"].append({"id": c["id"], "reason": f"published {il_day(c['published_at'])}"})
                continue
        key = (c["title"] or "").strip()
        if key in seen_titles:  # the same article under a second URL
            log["rejected"].append({"id": c["id"], "reason": "duplicate title"})
            continue
        seen_titles.add(key)
        picked.append(c)
    log["sampled"] = len(picked)
    log["by_source"] = dict(Counter(c["source"] for c in picked))
    for i, c in enumerate(picked):
        c["split"] = "dev" if i < DEV_PER_DAY else "test"
    return picked


FOCUSED_PER_STRATUM = 10
FOCUSED_SPORTS = ("football", "basketball", "unknown")


def dual_club_aliases() -> list[str]:
    """Hebrew aliases shared by an Israeli club's football and basketball sides
    (the taxonomy's cross-sport pairs, not hand-written)."""
    from app.taxonomy.resolver import ENTITIES, _CROSS_SPORT_AMBIGUOUS_IDS
    aliases = set()
    for eid in _CROSS_SPORT_AMBIGUOUS_IDS:
        e = ENTITIES[eid]
        if e.guarded:
            continue  # European multi-sport clubs: a different question
        aliases |= {a for a in e.aliases if any("֐" <= ch <= "׿" for ch in a)}
    return sorted(aliases, key=len, reverse=True)


def focused_set(db: Path, excluded: set[str]) -> dict:
    """#345 edge cases: unrated articles naming a dual-sport Israeli club, 10 per
    stored sport (football / basketball / unknown). It probes the guard in both
    directions and estimates nothing about prevalence."""
    aliases = dual_club_aliases()
    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    strata: dict[str, list[dict]] = {s: [] for s in FOCUSED_SPORTS}
    for aid, source, url, title, ttitle, subtitle, pub, sport in conn.execute(
        "SELECT id, source, url, title, translated_title, subtitle, published_at, sport "
        "FROM articles WHERE id GLOB 'rss_*' ORDER BY id"
    ):
        text = f"{ttitle or title} {subtitle or ''}"
        if aid in excluded or sport not in strata or not any(a in text for a in aliases):
            continue
        strata[sport].append({"id": aid, "title": ttitle or title, "subtitle": subtitle,
                              "source": source, "published_at": pub, "url": url,
                              "focus_stratum": f"dual_club/{sport}"})
    conn.close()
    items, sizes = [], {}
    for sport, rows in strata.items():
        random.Random(f"{SEED}:focused:{sport}").shuffle(rows)
        sizes[sport] = len(rows)
        items += rows[:FOCUSED_PER_STRATUM]
    random.Random(f"{SEED}:focused").shuffle(items)
    return {"meta": {"generated_at": datetime.now(timezone.utc).isoformat(), "seed": SEED,
                     "rule": "unrated articles whose title or subtitle names a dual-sport Israeli club "
                             "alias; 10 per stored sport",
                     "aliases": aliases, "population_by_stored_sport": sizes,
                     "regression_rows": sorted(INVESTIGATED - {"rss_03b90c13915220ecab72"}),
                     "scope": "Focused #345 edge cases, reported separately from the random sample."},
            "profiles": {"guy": {"strata": {"census": {"population": len(items), "sampled": len(items),
                                                        "weight": 1.0}}, "items": items}}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-day", action="append", default=[])
    ap.add_argument("--archive-day", action="append", default=[])
    ap.add_argument("--db", type=Path, default=BACKEND / "data" / "signal_sports.db")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--focused", action="store_true",
                    help="write the #345 focused set to --out instead (no network); the week "
                         "sample in docs/qa is excluded like every other rated or sampled id")
    args = ap.parse_args()

    excluded, per_file = excluded_ids()
    if args.focused:
        doc = focused_set(args.db, excluded)
        args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(doc["meta"]["population_by_stored_sport"]), "items",
              len(doc["profiles"]["guy"]["items"]))
        return
    days = sorted(set(args.db_day) | set(args.archive_day))
    corpus = db_rows(args.db, set(days))
    fetcher = Fetcher() if args.archive_day else None
    archive = archive_candidates(fetcher, set(args.archive_day)) if fetcher else []
    for a in archive:
        a.update({"id": article_id_from_url(a["url"]), "origin": "archive"})

    items, coverage = [], {}
    for day in days:
        cands = [c for c in corpus if c["day"] == day]
        if day in args.archive_day:
            cands += [a for a in archive if a["day"] == day]
        log = {"mode": "archive" if day in args.archive_day else "corpus",
               "candidates_by_source": dict(Counter(c["source"] for c in cands))}
        items += pick_day(day, cands, excluded, fetcher, log)
        coverage[day] = log

    keep = ("id", "title", "subtitle", "source", "published_at", "url", "day", "split", "origin")
    items = [{k: it.get(k) for k in keep} for it in items]
    random.Random(SEED).shuffle(items)  # rating order carries no day or source signal
    doc = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed": SEED, "per_day": PER_DAY, "dev_per_day": DEV_PER_DAY,
            "db_days": sorted(args.db_day), "archive_days": sorted(args.archive_day),
            "excluded_ids_total": len(excluded), "excluded_ids_by_file": per_file,
            "source_requests": fetcher.requests if fetcher else 0,
            "coverage": coverage,
            "scope": "Blind rating sample for #256: 15 random unique articles per Israel day, "
                     "before the LLM gate. No engine field.",
        },
        "profiles": {"guy": {"strata": {"census": {"population": len(items), "sampled": len(items),
                                                    "weight": 1.0}}, "items": items}},
    }
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({d: {k: v for k, v in c.items() if k != "rejected"} | {"rejected": len(c["rejected"])}
                      for d, c in coverage.items()}, ensure_ascii=False, indent=1))
    print("items", len(items), "requests", doc["meta"]["source_requests"])


if __name__ == "__main__":
    main()
