"""Fetch-only source probe: can THIS machine read the news sources? (T3, #268)

    python scripts/source_probe.py                    # the five Hebrew sources
    python scripts/source_probe.py --source walla_sport --source ynet_sport
    python scripts/source_probe.py --json             # machine-readable report

For a new host before the cutover (docs/HOSTING_PLAN.md section 14: "HTTP 200
alone doesn't count"). For each source it runs the SAME adapter ingestion uses,
plus a plain diagnostic request to each endpoint, and judges the CONTENT:

- items were parsed (>= --min-items), most carry a publication date, and the
  newest is younger than --max-age-hours;
- titles are in the source's language (Hebrew letters for Hebrew sources);
- item links point at the source's own site.

It never opens the database (no inserts, no reads), never changes source
enablement, never classifies or calls an LLM. Enablement shown is the static
config only; the live DB overrides (Sport5 on, ONE off on the PC) are not read.
Exit code: 0 when every probed source is "ok", 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.adapters.factory import build_adapter  # noqa: E402
from app.ingestion.config import RSS_SOURCES, RSSSourceConfig  # noqa: E402

HEBREW_SOURCES = ("walla_sport", "israel_hayom_sport", "ynet_sport", "one_sport", "sport5_sport")
_HEBREW = re.compile(r"[֐-׿]")
_USER_AGENT = "SignalSportsSourceProbe/1.0 (+https://github.com/Guy-Navon/signal-sports)"


@dataclass
class EndpointCheck:
    url: str
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    bytes: Optional[int] = None
    elapsed_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class SourceReport:
    source_id: str
    display_name: str
    source_type: str
    enabled_in_config: bool
    verdict: str = "error"
    problems: list[str] = field(default_factory=list)
    items: int = 0
    with_date: int = 0
    newest_age_hours: Optional[float] = None
    oldest_age_hours: Optional[float] = None
    in_language: Optional[int] = None
    off_site_links: int = 0
    fetch_seconds: Optional[float] = None
    adapter_errors: list[str] = field(default_factory=list)
    endpoints: list[EndpointCheck] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)


def _site(host: Optional[str]) -> str:
    """walla.co.il from rss.walla.co.il; one.co.il from www.one.co.il."""
    if not host:
        return ""
    labels = host.lower().split(".")
    keep = 3 if host.lower().endswith((".co.il", ".org.il", ".net.il")) else 2
    return ".".join(labels[-keep:])


def diagnose_endpoint(url: str, timeout: float = 10.0) -> EndpointCheck:
    """One plain GET, to name the failure: DNS, connect, TLS, HTTP status."""
    import httpx

    check = EndpointCheck(url=url)
    started = time.perf_counter()
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True,
                             headers={"User-Agent": _USER_AGENT})
        check.http_status = response.status_code
        check.content_type = response.headers.get("content-type", "").split(";")[0] or None
        check.bytes = len(response.content)
    except Exception as exc:  # noqa: BLE001 - every failure is a finding
        check.error = f"{type(exc).__name__}: {str(exc)[:160]}"
    check.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return check


class _Capture(logging.Handler):
    """Collects the adapters' error log lines: they log failures and return []."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage()[:240])


def probe_source(cfg: RSSSourceConfig, *, min_items: int, max_age_hours: float,
                 now: Optional[datetime] = None, diagnose: bool = True) -> SourceReport:
    now = now or datetime.now(tz=timezone.utc)
    report = SourceReport(cfg.source_id, cfg.display_name, cfg.source_type, cfg.enabled)
    endpoints = list(cfg.category_urls) if cfg.source_type == "html_scrape" else [cfg.feed_url]
    if diagnose:
        report.endpoints = [diagnose_endpoint(url) for url in endpoints]

    # Capture the adapters' warnings/errors instead of printing them: set the
    # level explicitly (a quiet root logger would otherwise drop them) and stop
    # propagation for the duration of the fetch.
    capture = _Capture()
    adapters_logger = logging.getLogger("app.ingestion.adapters")
    saved = (adapters_logger.level, adapters_logger.propagate)
    adapters_logger.setLevel(logging.WARNING)
    adapters_logger.propagate = False
    adapters_logger.addHandler(capture)
    started = time.perf_counter()
    try:
        items = build_adapter(cfg).fetch()
    except Exception as exc:  # noqa: BLE001
        items = []
        capture.messages.append(f"{type(exc).__name__}: {str(exc)[:200]}")
    finally:
        adapters_logger.removeHandler(capture)
        adapters_logger.setLevel(saved[0])
        adapters_logger.propagate = saved[1]
    report.fetch_seconds = round(time.perf_counter() - started, 2)
    report.adapter_errors = capture.messages

    report.items = len(items)
    ages = []
    for item in items:
        if item.published_at is not None:
            published = item.published_at
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            ages.append((now - published).total_seconds() / 3600)
    report.with_date = len(ages)
    if ages:
        report.newest_age_hours = round(min(ages), 2)
        report.oldest_age_hours = round(max(ages), 2)
    if cfg.language == "he":
        report.in_language = sum(1 for item in items if _HEBREW.search(item.title or ""))
    home = _site(urlparse(cfg.feed_url).hostname)
    report.off_site_links = sum(1 for item in items if _site(urlparse(item.url).hostname) != home)
    report.examples = [
        {"title": (item.title or "")[:90],
         "published_at": item.published_at.isoformat() if item.published_at else None,
         "url": item.url}
        for item in items[:3]
    ]

    problems = report.problems
    for check in report.endpoints:
        if check.error:
            problems.append(f"{check.url}: {check.error}")
        elif check.http_status is not None and check.http_status >= 400:
            problems.append(f"{check.url}: HTTP {check.http_status}")
    if report.items < min_items:
        problems.append(f"only {report.items} items parsed (need {min_items})")
    elif report.with_date < max(1, report.items // 2):
        problems.append(f"only {report.with_date}/{report.items} items carry a date")
    elif report.newest_age_hours is not None and report.newest_age_hours > max_age_hours:
        problems.append(f"newest item is {report.newest_age_hours:.1f} h old (limit {max_age_hours} h)")
    if report.items and report.in_language is not None and report.in_language < report.items / 2:
        problems.append(f"only {report.in_language}/{report.items} titles are in Hebrew")
    if report.items and report.off_site_links > report.items / 2:
        problems.append(f"{report.off_site_links}/{report.items} links leave {home}")

    if not problems:
        report.verdict = "ok"
    elif report.items == 0:
        report.verdict = "error" if (report.adapter_errors or any(
            c.error or (c.http_status or 0) >= 400 for c in report.endpoints)) else "empty"
    else:
        report.verdict = "degraded"
    return report


def select_sources(ids: list[str], include_english: bool) -> list[RSSSourceConfig]:
    by_id = {cfg.source_id: cfg for cfg in RSS_SOURCES}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise SystemExit(f"unknown source id(s): {', '.join(unknown)}; known: {', '.join(by_id)}")
    if ids:
        return [by_id[i] for i in ids]
    wanted = list(HEBREW_SOURCES) + ([c.source_id for c in RSS_SOURCES if c.language == "en"]
                                     if include_english else [])
    return [by_id[i] for i in wanted if i in by_id]


def _print_human(reports: list[SourceReport]) -> None:
    for r in reports:
        print(f"[{r.verdict.upper():8}] {r.source_id} ({r.source_type}, "
              f"{'enabled' if r.enabled_in_config else 'disabled'} in config): "
              f"{r.items} items, {r.with_date} dated, newest "
              f"{'-' if r.newest_age_hours is None else f'{r.newest_age_hours:.1f} h'} old, "
              f"fetch {r.fetch_seconds}s")
        for check in r.endpoints:
            detail = check.error or f"HTTP {check.http_status} {check.content_type} {check.bytes} B"
            print(f"    endpoint {check.url} -> {detail} ({check.elapsed_ms} ms)")
        for problem in r.problems:
            print(f"    problem: {problem}")
        for message in r.adapter_errors[:3]:
            print(f"    adapter: {message}")
        for example in r.examples:
            print(f"    e.g. {example['published_at']}  {example['title']}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", action="append", default=[], help="probe only this source id (repeatable)")
    parser.add_argument("--include-english", action="store_true", help="also probe the English pilots")
    parser.add_argument("--min-items", type=int, default=1)
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--no-diagnose", action="store_true", help="skip the extra plain GET per endpoint")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    reports = [
        probe_source(cfg, min_items=args.min_items, max_age_hours=args.max_age_hours,
                     diagnose=not args.no_diagnose)
        for cfg in select_sources(args.source, args.include_english)
    ]
    if args.json:
        print(json.dumps({
            "probed_at": datetime.now(tz=timezone.utc).isoformat(),
            "sources": [asdict(r) for r in reports],
        }, ensure_ascii=False, indent=2))
    else:
        _print_human(reports)
    return 0 if reports and all(r.verdict == "ok" for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
