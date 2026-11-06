"""#365: a failed RSS fetch must be a failure in the run record, not a quiet day.

The HTTP layer is faked at the urllib boundary and the real feedparser parses the
bytes, so these tests pin feedparser's actual outcomes (no `status` on a connection
error, a redirect status kept on a good response, `bozo` on a 200 with entries)
rather than a hand-built copy of them. Nothing here opens a socket.
"""

import json
import socket
import urllib.error
import uuid
from datetime import datetime, timezone
from email.message import Message
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.db.database import SessionLocal
from app.ingestion.adapters.base import SourceFetchError
from app.ingestion.adapters.factory import build_adapter
from app.ingestion.adapters.rss_adapter import RSSSourceAdapter

FEED_URLS = {
    "walla_sport": "https://rss.walla.co.il/feed/7",
    "israel_hayom_sport": "https://www.israelhayom.co.il/rss.xml",
    "ynet_sport": "https://www.ynet.co.il/Integration/StoryRss3.xml",
}
SECRET = "s3cret-feed-token"
URL_PREFIX = "https://example.test/sport/fixture-365-"


# ── Fake HTTP ─────────────────────────────────────────────────────────────────

class _Response:
    """The parts of a urllib response that feedparser reads."""

    def __init__(self, status: int, body: bytes, content_type: str | None = "application/rss+xml",
                 location: str | None = None):
        self.status = status
        self.code = status
        self.msg = "fake"
        self.url = "https://example.test/feed"
        self.headers = Message()
        if content_type:
            self.headers["content-type"] = content_type
        if location:
            self.headers["location"] = location
        self._body = body

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        pass

    def info(self) -> Message:
        return self.headers

    def geturl(self) -> str:
        return self.url


def _http(outcome_for):
    """Answer every feed request; ``outcome_for`` is one outcome or {url: outcome}."""

    def open_(request, *_args, **_kwargs):
        outcome = outcome_for
        if isinstance(outcome_for, dict):
            outcome = outcome_for[request.full_url]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return patch("urllib.request.OpenerDirector.open", side_effect=open_)


def _http_with_redirects(routes: dict):
    """Fake one layer lower, so urllib and feedparser's own handlers really run.

    `_http` replaces the opener, so it never sees feedparser overwrite `status` with
    the 3xx after following a redirect. This is the shape a dead target hides behind.
    """

    def https_open(request):
        return routes[request.full_url]

    return patch("urllib.request.HTTPSHandler.https_open", side_effect=https_open)


FEED = "https://example.test/feed"
MOVED = "https://example.test/moved"


def _redirect_to(target: _Response, status: int = 302) -> dict:
    return {FEED: _Response(status, b"", None, location=MOVED), MOVED: target}


def _rss(*titles_and_urls: tuple[str, str]) -> bytes:
    items = "".join(
        f"<item><title>{title}</title><link>{url}</link></item>"
        for title, url in titles_and_urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>feed</title>{items}</channel></rss>"
    ).encode("utf-8")


def _article(label: str) -> tuple[str, str]:
    return (f"מכבי תל אביב החתימה גארד חדש {label}", f"{URL_PREFIX}{label}-{uuid.uuid4().hex[:8]}")


REFUSED = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
HTML_403 = _Response(403, b"<html><body>Forbidden</body></html>", "text/html")
MALFORMED_WITH_ENTRIES = (
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
    b"<item><title>Tom &amp; Jerry & co</title><link>https://example.test/1</link></item>"
    b"<item><title>closing tags cut off</title><link>https://example.test/2</link></item>"
)


def _adapter() -> RSSSourceAdapter:
    return RSSSourceAdapter(
        source_id="walla_sport",
        feed_url="https://example.test/feed",
        source_display_name="Test",
        language="he",
    )


# ── The adapter: what is a failure, and what is not ───────────────────────────

class TestFetchFailuresRaise:
    @pytest.mark.parametrize(
        "outcome, reason",
        [
            pytest.param(REFUSED, "URLError", id="connection-refused"),
            pytest.param(socket.gaierror(11001, "getaddrinfo failed"), "gaierror", id="dns-while-reading"),
            pytest.param(TimeoutError("read timed out"), "TimeoutError", id="read-timeout"),
            pytest.param(HTML_403, "http_403", id="403-html-page"),
            pytest.param(_Response(404, b"", None), "http_404", id="404-empty-body-not-bozo"),
            pytest.param(_Response(503, b"<html><p>unavailable", "text/html"), "http_503", id="503"),
            pytest.param(_Response(403, _rss(("t", "https://example.test/x"))), "http_403", id="403-with-entries"),
            pytest.param(_Response(503, _rss(("t", "https://example.test/x"))), "http_503", id="503-with-entries"),
            pytest.param(_Response(302, b"", None), "not_a_feed", id="redirect-status-empty-body"),
            pytest.param(
                _Response(200, b"<!doctype html><html><body><p>captive portal<br></body></html>", "text/html"),
                "SAXParseException",
                id="200-html-error-page",
            ),
            pytest.param(
                _Response(200, b"<html><body>hi</body></html>", "text/html"),
                "NonXMLContentType",
                id="200-well-formed-html",
            ),
            pytest.param(
                _Response(200, b'<?xml version="1.0"?><rss><channel><title>t', "application/rss+xml"),
                "SAXParseException",
                id="200-truncated-xml-no-entries",
            ),
        ],
    )
    def test_failed_fetch_raises_a_named_reason(self, outcome, reason):
        with _http(outcome), pytest.raises(SourceFetchError) as raised:
            _adapter().fetch()
        assert str(raised.value) == reason

    def test_exception_from_feedparser_itself_raises(self):
        with patch("feedparser.parse", side_effect=ValueError("boom")), \
                pytest.raises(SourceFetchError) as raised:
            _adapter().fetch()
        assert str(raised.value) == "ValueError"
        assert isinstance(raised.value.__cause__, ValueError)

    def test_failure_restores_the_socket_timeout(self):
        before = socket.getdefaulttimeout()
        with _http(REFUSED), pytest.raises(SourceFetchError):
            _adapter().fetch()
        assert socket.getdefaulttimeout() == before


NON_FEED_XML = b'<?xml version="1.0"?><error><message>gone</message></error>'


class TestNoFeedInTheResponse:
    """Not `bozo`, no entries and no feed version: a valid empty feed has a version."""

    @pytest.mark.parametrize(
        "routes",
        [
            pytest.param(_redirect_to(_Response(404, b"", None)), id="302-to-404-empty"),
            pytest.param(_redirect_to(_Response(503, b"", None)), id="302-to-503-empty"),
            pytest.param(_redirect_to(_Response(404, NON_FEED_XML, "application/xml")), id="302-to-404-xml"),
            pytest.param(_redirect_to(_Response(410, b"", None), status=301), id="301-to-410-empty"),
            pytest.param({FEED: _Response(302, b"", None)}, id="302-without-location"),
            pytest.param({FEED: _Response(200, b"")}, id="200-empty-body"),
            pytest.param({FEED: _Response(200, NON_FEED_XML, "application/xml")}, id="200-non-feed-xml"),
            pytest.param({FEED: _Response(204, b"", None)}, id="204"),
        ],
    )
    def test_raises(self, routes):
        with _http_with_redirects(routes), pytest.raises(SourceFetchError) as raised:
            _adapter().fetch()
        assert str(raised.value) == "not_a_feed"


class TestValidEmptyFeeds:
    @pytest.mark.parametrize(
        "body",
        [
            pytest.param(_rss(), id="rss-2.0"),
            pytest.param(b"<rss><channel><title>t</title></channel></rss>", id="rss-no-version-attribute"),
            pytest.param(b'<rss version="0.91"><channel><title>t</title></channel></rss>', id="rss-0.91"),
            pytest.param(
                b'<feed xmlns="http://www.w3.org/2005/Atom"><title>t</title></feed>',
                id="atom-1.0",
            ),
            pytest.param(
                b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
                b'xmlns="http://purl.org/rss/1.0/"><channel><title>t</title></channel></rdf:RDF>',
                id="rdf",
            ),
        ],
    )
    def test_stays_an_empty_success(self, body):
        with _http_with_redirects({FEED: _Response(200, body)}):
            assert _adapter().fetch() == []

    def test_behind_a_redirect_stays_an_empty_success(self):
        with _http_with_redirects(_redirect_to(_Response(200, _rss()))):
            assert _adapter().fetch() == []

    def test_real_304_response_stays_an_empty_success(self):
        with _http_with_redirects({FEED: _Response(304, b"", None)}):
            assert _adapter().fetch() == []

    def test_feed_with_entries_behind_a_redirect_still_ingests(self):
        target = _Response(200, _rss(("title", "https://example.test/article")))
        with _http_with_redirects(_redirect_to(target)):
            items = _adapter().fetch()
        assert [i.url for i in items] == ["https://example.test/article"]


class TestNonFailuresStayQuiet:
    def test_healthy_empty_feed_is_an_empty_success(self):
        with _http(_Response(200, _rss())):
            assert _adapter().fetch() == []

    def test_slightly_malformed_feed_with_entries_still_ingests(self):
        with _http(_Response(200, MALFORMED_WITH_ENTRIES)):
            items = _adapter().fetch()
        assert [i.url for i in items] == ["https://example.test/1", "https://example.test/2"]

    def test_redirect_status_with_entries_is_not_a_failure(self):
        # feedparser keeps the 301 of a followed redirect as `status`.
        with _http(_Response(301, _rss(("title", "https://example.test/moved")))):
            items = _adapter().fetch()
        assert [i.url for i in items] == ["https://example.test/moved"]

    def test_not_modified_is_an_empty_success(self):
        # The adapter sends no conditional headers, so a 304 can only come from a
        # middlebox; it still means "nothing new", never "the source is down".
        with _http(_Response(304, b"")):
            assert _adapter().fetch() == []

    def test_result_without_a_status_is_not_a_failure(self):
        # feedparser sets `status` only when it spoke HTTP; parse the bytes directly.
        import feedparser
        parsed = feedparser.parse(_rss(("title", "https://example.test/nostatus")))
        assert "status" not in parsed
        with patch("feedparser.parse", return_value=parsed):
            items = _adapter().fetch()
        assert [i.url for i in items] == ["https://example.test/nostatus"]


# ── The pipeline: persisted run record, cycle, health ─────────────────────────

@pytest.fixture
def clean_runs(_application):
    """A free lease and no cycles; removes what the test wrote, for later tests."""
    started = datetime.now(tz=timezone.utc).isoformat()

    def reset(session):
        session.execute(text("DELETE FROM scheduler_cycles"))
        session.execute(text("UPDATE scheduler_lease SET active_cycle_id=NULL, "
                             "heartbeat_at=NULL, owner=NULL WHERE id=1"))
        session.commit()

    with SessionLocal() as session:
        reset(session)
    yield
    with SessionLocal() as session:
        reset(session)
        session.execute(text("DELETE FROM ingestion_runs WHERE started_at >= :t"), {"t": started})
        session.execute(text("DELETE FROM articles WHERE url LIKE :p"), {"p": f"{URL_PREFIX}%"})
        session.commit()


def _latest_run(source_id: str):
    with SessionLocal() as session:
        return session.execute(text(
            "SELECT status, fetched_count, inserted_count, failed_count, error_message, "
            "skipped_duplicate_count FROM ingestion_runs WHERE source_id = :s "
            "ORDER BY started_at DESC LIMIT 1"
        ), {"s": source_id}).one()


def _latest_cycle():
    with SessionLocal() as session:
        row = session.execute(text(
            "SELECT id, status, error_summary, source_results FROM scheduler_cycles "
            "ORDER BY requested_at DESC LIMIT 1"
        )).one()
    results = row[3]
    return row[0], row[1], row[2], json.loads(results) if isinstance(results, str) else results


def _source_health(admin_client, source_id: str) -> dict:
    health = admin_client.get("/api/ingest/source-health").json()
    return next(h for h in health if h["source_id"] == source_id)


def _run_rss_sources(admin_client, outcomes: dict):
    """Run all enabled sources: real RSS adapters, and no scrape-adapter network."""

    class _Empty:
        def fetch(self):
            return []

    def build(cfg):
        return build_adapter(cfg) if cfg.source_type == "rss" else _Empty()

    with patch("app.ingestion.ingestion_service.build_adapter", side_effect=build), _http(outcomes):
        return admin_client.post("/api/ingest/run")


class TestDeadSourceIsVisible:
    @pytest.mark.parametrize(
        "outcome, reason",
        [
            pytest.param(REFUSED, "URLError", id="connection-refused"),
            pytest.param(HTML_403, "http_403", id="403"),
            pytest.param(_Response(200, b"<rss><channel><title>t", "application/rss+xml"),
                         "SAXParseException", id="bozo-no-entries"),
        ],
    )
    def test_failure_reaches_every_record(self, admin_client, clean_runs, outcome, reason):
        with _http(outcome):
            response = admin_client.post("/api/ingest/run?source_id=walla_sport")

        message = f"Fetch error for walla_sport: {reason}"

        # The API answer the owner sees after a manual run.
        assert response.status_code == 200
        assert response.json()["status"] == "error"
        source = response.json()["sources"][0]
        assert (source["fetched"], source["inserted"], source["failed"]) == (0, 0, 1)
        assert source["errors"] == [message]

        # The persisted per-source run: what the pilot report (#252) will read.
        run = _latest_run("walla_sport")
        assert run.status == "error"
        assert (run.fetched_count, run.inserted_count, run.failed_count) == (0, 0, 1)
        assert run.error_message == message

        # The persisted cycle, and the health output built from it.
        cycle_id, status, summary, results = _latest_cycle()
        assert status == "failed"
        assert summary == message
        assert results[0]["errors"] == [message]

        health = admin_client.get("/api/scheduler/health").json()
        assert health["last_attempted_cycle"]["id"] == cycle_id
        assert health["consecutive_failures"] == 1
        assert health["ingestion_degraded"] is True
        assert [s["source_id"] for s in health["last_source_failures"]] == ["walla_sport"]

        card = _source_health(admin_client, "walla_sport")
        assert card["freshness"] == "error"
        assert card["last_status"] == "error"
        assert card["consecutive_failures"] >= 1
        assert card["last_failed_count"] == 1
        assert card["last_error_message"] == message

    def test_dead_target_behind_a_redirect_is_a_failure(self, admin_client, clean_runs):
        walla = FEED_URLS["walla_sport"]
        routes = {
            walla: _Response(302, b"", None, location=MOVED),
            MOVED: _Response(404, b"", None),
        }
        with _http_with_redirects(routes):
            response = admin_client.post("/api/ingest/run?source_id=walla_sport")

        message = "Fetch error for walla_sport: not_a_feed"
        assert response.json()["sources"][0]["errors"] == [message]
        run = _latest_run("walla_sport")
        assert (run.status, run.failed_count, run.error_message) == ("error", 1, message)
        assert _latest_cycle()[1] == "failed"

    def test_exception_text_with_a_url_secret_is_not_persisted(self, admin_client, clean_runs):
        leak = OSError(f"could not reach https://user:{SECRET}@feeds.example.test/rss?key={SECRET}")
        with patch("feedparser.parse", side_effect=leak):
            response = admin_client.post("/api/ingest/run?source_id=walla_sport")

        assert SECRET not in response.text
        assert SECRET not in (_latest_run("walla_sport").error_message or "")
        _, _, summary, results = _latest_cycle()
        assert SECRET not in (summary or "")
        assert SECRET not in json.dumps(results)
        assert SECRET not in admin_client.get("/api/scheduler/health").text
        assert SECRET not in admin_client.get("/api/ingest/source-health").text

    def test_dead_cycle_does_not_count_as_a_success(self, admin_client, clean_runs):
        with _http(_Response(200, _rss())):
            admin_client.post("/api/ingest/run?source_id=walla_sport")
        healthy_cycle = _latest_cycle()[0]

        with _http(REFUSED):
            admin_client.post("/api/ingest/run?source_id=walla_sport")

        health = admin_client.get("/api/scheduler/health").json()
        assert health["last_successful_cycle"]["id"] == healthy_cycle


class TestHealthyEmptyFeedIsSuccess:
    def test_empty_feed_is_ok_everywhere(self, admin_client, clean_runs):
        with _http(_Response(200, _rss())):
            response = admin_client.post("/api/ingest/run?source_id=walla_sport")

        assert response.json()["status"] == "ok"
        source = response.json()["sources"][0]
        assert (source["fetched"], source["failed"], source["errors"]) == (0, 0, [])

        run = _latest_run("walla_sport")
        assert run.status == "ok"
        assert (run.fetched_count, run.failed_count, run.error_message) == (0, 0, None)

        assert _latest_cycle()[1] == "succeeded"
        health = admin_client.get("/api/scheduler/health").json()
        assert health["consecutive_failures"] == 0
        assert health["last_source_failures"] == []
        assert _source_health(admin_client, "walla_sport")["last_status"] == "ok"


class TestPartialFailure:
    def test_one_dead_source_does_not_stop_the_others(self, admin_client, clean_runs):
        title, url = _article("ynet")
        response = _run_rss_sources(admin_client, {
            FEED_URLS["walla_sport"]: REFUSED,
            FEED_URLS["israel_hayom_sport"]: HTML_403,
            FEED_URLS["ynet_sport"]: _Response(200, _rss((title, url))),
        })

        sources = {s["source_id"]: s for s in response.json()["sources"]}
        assert sources["walla_sport"]["errors"] == ["Fetch error for walla_sport: URLError"]
        assert sources["israel_hayom_sport"]["errors"] == ["Fetch error for israel_hayom_sport: http_403"]
        assert (sources["ynet_sport"]["inserted"], sources["ynet_sport"]["errors"]) == (1, [])

        assert _latest_run("walla_sport").status == "error"
        assert _latest_run("israel_hayom_sport").status == "error"
        assert _latest_run("ynet_sport").status == "ok"

        assert _latest_cycle()[1] == "succeeded_with_warnings"
        health = admin_client.get("/api/scheduler/health").json()
        assert health["consecutive_failures"] == 0
        assert {s["source_id"] for s in health["last_source_failures"]} == {
            "walla_sport", "israel_hayom_sport",
        }

    def test_every_rss_source_dead_fails_the_cycle(self, admin_client, clean_runs):
        _run_rss_sources(admin_client, {url: REFUSED for url in FEED_URLS.values()})
        assert _latest_cycle()[1] == "failed"


class TestMalformedFeedThroughThePipeline:
    def test_bozo_feed_with_entries_ingests_and_stays_ok(self, admin_client, clean_runs):
        title, url = _article("bozo")
        body = (
            '<?xml version="1.0"?><rss version="2.0"><channel><title>t & co</title>'
            f"<item><title>{title}</title><link>{url}</link></item>"
        ).encode("utf-8")
        with _http(_Response(200, body)):
            response = admin_client.post("/api/ingest/run?source_id=walla_sport")

        source = response.json()["sources"][0]
        assert (source["fetched"], source["inserted"], source["failed"], source["errors"]) == (1, 1, 0, [])
        assert _latest_run("walla_sport").status == "ok"
        assert _latest_cycle()[1] == "succeeded"


class TestRecoveryAfterAFailure:
    def test_next_good_fetch_loses_nothing_and_duplicates_nothing(self, admin_client, clean_runs):
        first, second = _article("one"), _article("two")
        good = _Response(200, _rss(first, second))

        with _http(_Response(200, _rss(first))):
            admin_client.post("/api/ingest/run?source_id=walla_sport")
        with _http(REFUSED):
            admin_client.post("/api/ingest/run?source_id=walla_sport")

        # The article published during the outage arrives; the old one is not re-added.
        with _http(good):
            recovered = admin_client.post("/api/ingest/run?source_id=walla_sport").json()["sources"][0]
        assert (recovered["inserted"], recovered["skipped_duplicate"], recovered["errors"]) == (1, 1, [])

        with _http(good):
            repeat = admin_client.post("/api/ingest/run?source_id=walla_sport").json()["sources"][0]
        assert (repeat["inserted"], repeat["skipped_duplicate"]) == (0, 2)

        with SessionLocal() as session:
            stored = session.execute(
                text("SELECT COUNT(*) FROM articles WHERE url IN (:a, :b)"),
                {"a": first[1], "b": second[1]},
            ).scalar()
        assert stored == 2
        assert admin_client.get("/api/scheduler/health").json()["consecutive_failures"] == 0
