"""Read-only probe of the ONE Sport source, before the owner decides on it (#258).

    python scripts/one_sport_probe.py --db <COPY of signal_sports.db>
    python scripts/one_sport_probe.py --db <copy> --json > one_probe.json
    python scripts/one_sport_probe.py --save-raw <dir>     # keep the raw JSON responses
    python scripts/one_sport_probe.py --replay <dir> --now <probe time>   # re-analyse, no network

It builds `OneSportAdapter` from `config.py` and calls the real `fetch()`: one GET per
category endpoint (six requests), with the adapter's own headers and User-Agent. Each
response is recorded on its way into the adapter, so the per-endpoint report comes from
the same bytes the adapter parsed, without a second request.

Per endpoint it reports the HTTP status, raw item count, parsed items, skipped video
items, items missing a field, the age span and sample titles. For the whole fetch it
reports the URL shapes, the basketball share (by endpoint category, by URL hint and by
the deterministic classifier), an items-per-day estimate and how many fetched items the
LLM gate would send to the LLM.

With `--db` it also reads a corpus copy, opened `mode=ro`: how many fetched URLs are
already stored (the URL dedup ingestion uses), how many fetched items have a likely
same-story article from another source (a title-token heuristic, not the clusterer),
and the recent LLM call rate and latency of the enabled Hebrew sources.

It never writes to any database, never changes source enablement, never calls an LLM
and never imports the app's database module. Pass a COPY of the live database, never
the live file. Exit code: 0 when every endpoint answered 200 and items were parsed.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, TextIO
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.classification.gating import should_call_llm_for_article  # noqa: E402
from app.classification.source_hints import extract_source_sport_hint  # noqa: E402
from app.clustering.tokens import is_generic, tokenize  # noqa: E402
from app.ingestion.adapters import one_adapter  # noqa: E402
from app.ingestion.adapters.base import RawSourceItem  # noqa: E402
from app.ingestion.adapters.factory import build_adapter  # noqa: E402
from app.ingestion.classifier import classify  # noqa: E402
from app.ingestion.config import RSSSourceConfig, get_source_config  # noqa: E402

SOURCE_ID = "one_sport"
BASKETBALL_CATEGORY_IDS = frozenset({"2", "5"})
HEBREW_BROAD_SOURCES = ("walla_sport", "israel_hayom_sport", "ynet_sport", "sport5_sport")
_HEBREW = re.compile(r"[֐-׿]")
_CATEGORY_ID = re.compile(r"/Category/(\d+)", re.IGNORECASE)
_URL_WITH_CATEGORY = re.compile(r"/article/\d{2}-\d{2}/\d+,", re.IGNORECASE)
_URL_GENERIC = re.compile(r"/article/\d+\.html", re.IGNORECASE)


@dataclass
class Exchange:
    """One recorded request/response, as the adapter saw it."""
    url: str
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    bytes: Optional[int] = None
    elapsed_ms: Optional[float] = None
    error: Optional[str] = None
    payload: Any = None


@dataclass
class EndpointReport:
    url: str
    category_id: Optional[str]
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    bytes: Optional[int] = None
    elapsed_ms: Optional[float] = None
    error: Optional[str] = None
    raw_items: int = 0
    parsed_items: int = 0
    skipped_video: int = 0
    missing_url: int = 0
    missing_title: int = 0
    missing_date: int = 0
    missing_subtitle: int = 0
    hebrew_titles: int = 0
    newest_age_hours: Optional[float] = None
    oldest_age_hours: Optional[float] = None
    per_day_rate: Optional[float] = None
    samples: list[dict] = field(default_factory=list)


# ── Fetch: the real adapter, with every response recorded ────────────────────

def recorded_fetch(cfg: RSSSourceConfig) -> tuple[list[RawSourceItem], list[Exchange]]:
    """Run the real `fetch()` once and keep each HTTP exchange it made."""
    import httpx

    exchanges: list[Exchange] = []

    def recording_get(url, **kwargs):
        exchange = Exchange(url=str(url))
        exchanges.append(exchange)
        started = time.perf_counter()
        try:
            response = httpx.get(url, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a failure is a finding; the adapter logs it too
            exchange.error = f"{type(exc).__name__}: {str(exc)[:160]}"
            raise
        finally:
            exchange.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        exchange.http_status = response.status_code
        exchange.content_type = response.headers.get("content-type", "").split(";")[0] or None
        exchange.bytes = len(response.content)
        try:
            exchange.payload = response.json()
        except ValueError as exc:
            exchange.error = f"not JSON: {exc}"
        return response

    return _fetch_through(cfg, recording_get), exchanges


class _SavedResponse:
    """A saved JSON payload, served back the way httpx would (replay mode)."""

    def __init__(self, path: Path) -> None:
        self.content = path.read_bytes()
        self.status_code = 200
        self.headers = {"content-type": "application/json"}

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self) -> None:
        return None


def replayed_fetch(cfg: RSSSourceConfig, raw_dir: Path) -> tuple[list[RawSourceItem], list[Exchange]]:
    """The same fetch(), fed from responses an earlier run saved with --save-raw. No network."""
    exchanges: list[Exchange] = []

    def replay_get(url, **kwargs):
        exchange = Exchange(url=str(url))
        exchanges.append(exchange)
        path = raw_dir / _raw_name(str(url))
        if not path.is_file():
            exchange.error = f"no saved response {path.name}"
            raise FileNotFoundError(path)
        response = _SavedResponse(path)
        exchange.http_status, exchange.content_type = 200, "application/json"
        exchange.bytes = len(response.content)
        exchange.payload = response.json()
        if not isinstance(exchange.payload, dict):
            exchange.error = f"saved response {path.name} is not a JSON object"
        return response

    return _fetch_through(cfg, replay_get), exchanges


def _fetch_through(cfg: RSSSourceConfig, get) -> list[RawSourceItem]:
    adapter = build_adapter(cfg)
    with mock.patch.object(one_adapter, "httpx", SimpleNamespace(get=get)):
        return adapter.fetch()


def _raw_name(url: str) -> str:
    match = _CATEGORY_ID.search(url)
    return f"one_category_{match.group(1) if match else 'unknown'}.json"


# ── Analysis (pure: no network, no database) ─────────────────────────────────

def _age_hours(published: Optional[datetime], now: datetime) -> Optional[float]:
    if published is None:
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return round((now - published).total_seconds() / 3600, 2)


def answered(exchange: Exchange) -> bool:
    """A 2xx response with no transport or decoding error: the only bodies fetch() parses."""
    return exchange.error is None and exchange.http_status is not None and 200 <= exchange.http_status < 300


def endpoint_report(exchange: Exchange, now: datetime, samples: int = 3) -> EndpointReport:
    """What the adapter's own parser makes of one recorded response.

    Error responses are not analysed (fetch() discards them). A 2xx body whose JSON
    shape the parser cannot read is reported as an endpoint error, never raised:
    an API change is exactly what this probe must surface.
    """
    match = _CATEGORY_ID.search(exchange.url)
    base = EndpointReport(
        url=exchange.url, category_id=match.group(1) if match else None,
        http_status=exchange.http_status, content_type=exchange.content_type,
        bytes=exchange.bytes, elapsed_ms=exchange.elapsed_ms, error=exchange.error,
    )
    if not answered(exchange):
        return base
    if not isinstance(exchange.payload, dict):
        base.error = f"unexpected JSON shape: top level is {type(exchange.payload).__name__}"
        return base
    try:
        return _analysed(replace(base), exchange.payload, now, samples)
    except Exception as exc:  # noqa: BLE001 - a changed shape is a finding, not a crash
        base.error = f"parse failed (changed JSON shape?): {type(exc).__name__}: {str(exc)[:160]}"
        return base


def _analysed(report: EndpointReport, payload: dict, now: datetime, samples: int) -> EndpointReport:
    adapter = one_adapter.OneSportAdapter(SOURCE_ID, (), "https://www.one.co.il/")
    raw = list(adapter._iter_article_items(payload))
    report.raw_items = len(raw)
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("IsVideo") is True:
            report.skipped_video += 1
            continue
        if one_adapter._article_url(item, adapter.base_url) is None:
            report.missing_url += 1
        if not one_adapter._article_title(item):
            report.missing_title += 1
        if one_adapter._parse_one_datetime(item.get("Date")) is None:
            report.missing_date += 1
        if not one_adapter._article_subtitle(item):
            report.missing_subtitle += 1

    parsed = adapter._parse_payload(payload, set())
    report.parsed_items = len(parsed)
    report.hebrew_titles = sum(1 for p in parsed if _HEBREW.search(p.title))
    ages = [a for a in (_age_hours(p.published_at, now) for p in parsed) if a is not None]
    if ages:
        report.newest_age_hours, report.oldest_age_hours = min(ages), max(ages)
        if report.oldest_age_hours > 0:
            # A list holds the newest N items: N per (age of the oldest) is its rate.
            report.per_day_rate = round(len(ages) / report.oldest_age_hours * 24, 1)
    report.samples = [
        {"title": p.title[:100], "published_at": p.published_at.isoformat() if p.published_at else None,
         "url": p.url}
        for p in parsed[:samples]
    ]
    return report


def url_shape(url: str) -> str:
    if "vole.one.co.il/item/" in url:
        return "vole_item"
    if _URL_WITH_CATEGORY.search(url):
        return "article_with_category"
    if _URL_GENERIC.search(url):
        return "article_generic"
    return "other"


def first_endpoint_by_url(exchanges: list[Exchange]) -> dict[str, Optional[str]]:
    """url -> category id of the first endpoint that carried it (fetch() keeps the first)."""
    adapter = one_adapter.OneSportAdapter(SOURCE_ID, (), "https://www.one.co.il/")
    owner: dict[str, Optional[str]] = {}
    for exchange in exchanges:
        if not answered(exchange) or not isinstance(exchange.payload, dict):
            continue
        match = _CATEGORY_ID.search(exchange.url)
        try:
            parsed = adapter._parse_payload(exchange.payload, set())
        except Exception:  # noqa: BLE001 - endpoint_report records the shape error
            continue
        for item in parsed:
            owner.setdefault(item.url, match.group(1) if match else None)
    return owner


def items_per_day(items: list[RawSourceItem], endpoints: list[EndpointReport], now: datetime) -> dict:
    """Items dated within the last 24 h, and the summed per-endpoint publishing rate.

    Each endpoint returns only its newest items, so items / (age of the oldest) is that
    list's rate. The sum double-counts items listed in two categories, so it is scaled
    by the share fetch() keeps after cross-endpoint dedup. Night hours lower it.
    """
    ages = [a for a in (_age_hours(i.published_at, now) for i in items) if a is not None]
    rates = [e.per_day_rate for e in endpoints if e.per_day_rate is not None]
    parsed = sum(e.parsed_items for e in endpoints)
    estimate: dict = {"dated_items": len(ages),
                      "published_last_24h": sum(1 for a in ages if 0 <= a <= 24)}
    if rates and parsed:
        estimate["estimated_per_day"] = round(sum(rates) * len(items) / parsed)
    return estimate


def gate_estimate(cfg: RSSSourceConfig, items: list[RawSourceItem]) -> dict:
    """Deterministic classification + the production LLM gate (gating on), per item."""
    reasons: Counter = Counter()
    sports: Counter = Counter()
    calls = 0
    for item in items:
        hint = extract_source_sport_hint(cfg.source_id, item.url)
        rules = classify(item.title, source_id=cfg.source_id, language=cfg.language,
                         url=item.url, subtitle=item.summary, source_sport_hint=hint)
        sports[rules.sport] += 1
        gate = should_call_llm_for_article(
            source_id=cfg.source_id, title=item.title, subtitle=item.summary,
            rules_result=rules, source_sport_hint=hint, gating_enabled_override=True,
        )
        reasons[gate.reason] += 1
        calls += int(gate.should_call_llm)
    return {"items": len(items), "would_call_llm": calls,
            "gate_reasons": dict(reasons.most_common()), "rules_sport": dict(sports.most_common())}


# ── Corpus copy (read-only) ──────────────────────────────────────────────────

def open_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise SystemExit(f"--db {db_path} does not exist")
    return sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)


def _parse_stored(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _story_tokens(title: str) -> set[str]:
    return {t for t in tokenize(title) if not is_generic(t)}


def corpus_report(conn: sqlite3.Connection, items: list[RawSourceItem], now: datetime,
                  owner: Optional[dict[str, Optional[str]]] = None,
                  *, window_hours: float = 36.0, min_shared: int = 2, examples: int = 6) -> dict:
    report: dict = {}
    urls = [i.url for i in items]
    stored = {row[0]: row[1] for row in conn.execute(
        f"SELECT url, source FROM articles WHERE url IN ({','.join('?' * len(urls))})", urls)} if urls else {}
    report["fetched"] = len(urls)
    report["already_in_corpus_by_url"] = len(stored)
    report["would_be_new"] = len(urls) - len(stored)
    report["one_rows_in_corpus"] = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE source = ?", (SOURCE_ID,)).fetchone()[0]
    overrides = dict(conn.execute("SELECT source_id, enabled FROM source_overrides").fetchall())
    report["source_overrides"] = {k: bool(v) for k, v in overrides.items()}
    last_run = conn.execute(
        "SELECT MAX(started_at) FROM ingestion_runs WHERE source_id = ?", (SOURCE_ID,)).fetchone()[0]
    report["last_one_ingestion_run"] = last_run
    latest = _parse_stored(conn.execute("SELECT MAX(started_at) FROM ingestion_runs").fetchone()[0])
    report["corpus_last_ingestion_run"] = latest.isoformat() if latest else None

    # Likely cross-source overlap: another source's article, published near the ONE
    # item, sharing >= min_shared non-generic title tokens. A heuristic, not the clusterer.
    dated = [i.published_at for i in items if i.published_at is not None]
    since = ((min(dated) if dated else now) - timedelta(hours=window_hours)).isoformat()
    others = []
    for source, title, published in conn.execute(
            "SELECT source, title, published_at FROM articles WHERE source != ? AND published_at >= ?",
            (SOURCE_ID, since)):
        when = _parse_stored(published)
        if when is not None:
            others.append((source, title, when, _story_tokens(title)))
    owner = owner or {}
    matched = comparable = 0
    by_source: Counter = Counter()
    by_category: dict[str, list[int]] = {}
    found: list[dict] = []
    for item in items:
        # Only items the corpus could already hold: published before its last run.
        if item.published_at is None or (latest is not None and item.published_at > latest):
            continue
        comparable += 1
        tally = by_category.setdefault(str(owner.get(item.url)), [0, 0])
        tally[1] += 1
        mine = _story_tokens(item.title)
        best = None
        for source, title, when, tokens in others:
            if abs((when - item.published_at).total_seconds()) > window_hours * 3600:
                continue
            shared = mine & tokens
            if len(shared) >= min_shared and (best is None or len(shared) > len(best[2])):
                best = (source, title, shared)
        if best is not None:
            matched += 1
            tally[0] += 1
            by_source[best[0]] += 1
            if len(found) < examples:
                found.append({"one": item.title[:90], "other_source": best[0],
                              "other": best[1][:90], "shared": sorted(best[2])})
    report["cross_source_overlap"] = {
        "method": f">= {min_shared} shared non-generic title tokens within +-{window_hours:g} h",
        "comparable_items": comparable, "with_likely_match": matched,
        "matched_by_category": {k: f"{v[0]}/{v[1]}" for k, v in by_category.items()},
        "best_match_source": dict(by_source.most_common()), "examples": found,
    }

    # The recent LLM call rate and latency of the enabled Hebrew sources (#31 metrics).
    week_start = now - timedelta(days=7)
    week_ago = week_start.isoformat()
    # The copy's data ends at its last run, which can be well before `now`.
    window_end = min(now, latest) if latest is not None else now
    window_days = max((window_end - week_start).total_seconds() / 86400, 0.0)
    new_articles = attempts = 0
    latency_weighted = 0.0
    for (metrics,) in conn.execute(
            f"SELECT metrics FROM ingestion_runs WHERE started_at >= ? AND metrics IS NOT NULL "
            f"AND source_id IN ({','.join('?' * len(HEBREW_BROAD_SOURCES))})",
            (week_ago, *HEBREW_BROAD_SOURCES)):
        try:
            data = json.loads(metrics)
        except ValueError:
            continue
        new_articles += data.get("new_articles") or 0
        n = data.get("llm_attempts") or 0
        attempts += n
        if n and data.get("llm_avg_ms"):
            latency_weighted += data["llm_avg_ms"] * n
    report["hebrew_sources_last_7d"] = {
        "new_articles": new_articles, "window_days": round(window_days, 2),
        "new_articles_per_day": round(new_articles / window_days) if window_days else None,
        "llm_attempts": attempts,
        "llm_call_rate": round(attempts / new_articles, 3) if new_articles else None,
        "llm_avg_ms": round(latency_weighted / attempts) if attempts else None,
    }
    return report


# ── Report ───────────────────────────────────────────────────────────────────

def build_report(cfg: RSSSourceConfig, items: list[RawSourceItem], exchanges: list[Exchange],
                 now: datetime, conn: Optional[sqlite3.Connection] = None) -> dict:
    endpoints = [endpoint_report(e, now) for e in exchanges]
    owner = first_endpoint_by_url(exchanges)
    from_basketball_endpoints = sum(1 for i in items if owner.get(i.url) in BASKETBALL_CATEGORY_IDS)
    hinted = Counter(extract_source_sport_hint(cfg.source_id, i.url) or "none" for i in items)
    report = {
        "probed_at": now.isoformat(),
        "source_id": cfg.source_id,
        "enabled_in_config": cfg.enabled,
        "requests": len(exchanges),
        "endpoints": [asdict(e) for e in endpoints],
        "fetch": {
            "items": len(items),
            "unique_urls": len({i.url for i in items}),
            "cross_endpoint_duplicates": sum(e.parsed_items for e in endpoints) - len(items),
            "hebrew_titles": sum(1 for i in items if _HEBREW.search(i.title)),
            "with_subtitle": sum(1 for i in items if i.summary),
            "url_shapes": dict(Counter(url_shape(i.url) for i in items).most_common()),
            "basketball_by_endpoint": from_basketball_endpoints,
            "url_sport_hint": dict(hinted.most_common()),
            "per_day": items_per_day(items, endpoints, now),
        },
        "gate": gate_estimate(cfg, items),
    }
    if conn is not None:
        report["corpus"] = corpus_report(conn, items, now, owner)
    return report


def healthy(report: dict) -> bool:
    return bool(report["endpoints"]) and report["fetch"]["items"] > 0 and all(
        e["http_status"] == 200 and not e["error"] for e in report["endpoints"])


def _print_human(report: dict, out: TextIO) -> None:
    def emit(*parts) -> None:
        print(*parts, file=out)

    f = report["fetch"]
    emit(f"ONE probe {report['probed_at']}  ({report['requests']} requests, "
         f"{'enabled' if report['enabled_in_config'] else 'disabled'} in config.py)")
    for e in report["endpoints"]:
        status = e["error"] or f"HTTP {e['http_status']} {e['content_type']} {e['bytes']} B"
        emit(f"  cat {e['category_id']:>4}: {status} {e['elapsed_ms']} ms | raw {e['raw_items']}, "
             f"parsed {e['parsed_items']}, video {e['skipped_video']}, missing url/title/date/sub "
             f"{e['missing_url']}/{e['missing_title']}/{e['missing_date']}/{e['missing_subtitle']}, "
             f"age {e['newest_age_hours']}-{e['oldest_age_hours']} h, ~{e['per_day_rate']}/day")
        for s in e["samples"]:
            emit(f"      {s['published_at']}  {s['title']}  {s['url']}")
    emit(f"  fetch(): {f['items']} items ({f['cross_endpoint_duplicates']} cross-endpoint dups dropped), "
         f"{f['hebrew_titles']} Hebrew, {f['with_subtitle']} with subtitle")
    emit(f"  url shapes: {f['url_shapes']}  url hints: {f['url_sport_hint']}")
    emit(f"  basketball: {f['basketball_by_endpoint']}/{f['items']} from categories 2/5; "
         f"rules sport {report['gate']['rules_sport']}")
    emit(f"  per day: {f['per_day']}")
    g = report["gate"]
    emit(f"  LLM gate: {g['would_call_llm']}/{g['items']} would call the LLM; {g['gate_reasons']}")
    c = report.get("corpus")
    if c:
        emit(f"  corpus: {c['already_in_corpus_by_url']}/{c['fetched']} already stored by URL, "
             f"{c['would_be_new']} new; one_sport rows {c['one_rows_in_corpus']}; "
             f"last one_sport run {c['last_one_ingestion_run']}; overrides {c['source_overrides']}")
        o = c["cross_source_overlap"]
        emit(f"  likely cross-source overlap ({o['method']}), items published before the corpus's "
             f"last run {c['corpus_last_ingestion_run']}: {o['with_likely_match']}/{o['comparable_items']} "
             f"{o['best_match_source']}; by category {o['matched_by_category']}")
        for ex in o["examples"]:
            emit(f"      ONE: {ex['one']}\n        ~ {ex['other_source']}: {ex['other']}  {ex['shared']}")
        emit(f"  Hebrew sources, last 7 days: {c['hebrew_sources_last_7d']}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, help="a COPY of signal_sports.db, opened read-only")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--save-raw", type=Path, help="write each raw JSON response here")
    parser.add_argument("--replay", type=Path, help="no network: re-analyse responses saved by --save-raw "
                                                    "(a saved response reports HTTP 200; an endpoint that failed live has none and stays failed)")
    parser.add_argument("--now", help="ISO time to measure ages from (default: now; use the probe time with --replay)")
    args = parser.parse_args(argv)

    cfg = get_source_config(SOURCE_ID)
    if cfg is None:
        raise SystemExit("one_sport is not configured")
    conn = open_readonly(args.db) if args.db else None
    now = _parse_stored(args.now) if args.now else datetime.now(tz=timezone.utc)
    if now is None:
        raise SystemExit(f"--now {args.now!r} is not an ISO time")
    if args.replay:
        items, exchanges = replayed_fetch(cfg, args.replay)
    else:
        items, exchanges = recorded_fetch(cfg)
    if args.save_raw:
        args.save_raw.mkdir(parents=True, exist_ok=True)
        for e in exchanges:
            # Only bodies the adapter would parse: a failed endpoint has no saved
            # response, so --replay reports it as failed instead of as a 200.
            if answered(e):
                (args.save_raw / _raw_name(e.url)).write_text(
                    json.dumps(e.payload, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        report = build_report(cfg, items, exchanges, now, conn)
    finally:
        if conn is not None:
            conn.close()
    # Hebrew titles: a redirected stdout on Windows gets the ANSI codepage (cp1252),
    # so write UTF-8 explicitly, as the other corpus scripts do.
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2), file=out)
    else:
        _print_human(report, out)
    out.flush()
    out.detach()  # leave sys.stdout usable for the caller
    return 0 if healthy(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
