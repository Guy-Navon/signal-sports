"""
Development helper: probe candidate Hebrew RSS feed URLs.

Usage:
    .venv/Scripts/python.exe scripts/probe_hebrew_rss.py

Does NOT write to the database. Prints feed title, entry count,
and the first 5 article titles for each candidate URL.
"""

import sys
import feedparser

CANDIDATES = [
    # Walla — sports category feeds
    ("walla_sport",         "https://rss.walla.co.il/feed/6"),
    ("walla_sport_alt",     "https://rss.walla.co.il/feed/22"),
    ("walla_sport_alt2",    "https://rss.walla.co.il/?w=/6"),
    # Walla basketball
    ("walla_basketball",    "https://rss.walla.co.il/feed/9"),
    ("walla_basketball2",   "https://rss.walla.co.il/feed/41"),
    # Ynet sport
    ("ynet_sport",          "https://www.ynet.co.il/Integration/StoryRss2.xml?id=185"),
    ("ynet_sport_alt",      "https://www.ynet.co.il/Integration/StoryRss2.xml"),
    ("ynet_sport_alt2",     "https://www.ynet.co.il/home/0,7340,L-4697,00.html"),
    # Maariv sport
    ("maariv_sport",        "https://www.maariv.co.il/rss/sport"),
    # sport1
    ("sport1",              "https://www.sport1.co.il/rss/rss.xml"),
    ("sport1_basketball",   "https://www.sport1.co.il/rss/basketball.xml"),
    # ONE
    ("one_sport",           "https://www.one.co.il/rss.aspx"),
]


def probe(source_id: str, url: str) -> None:
    print(f"\n{'='*60}")
    print(f"Source: {source_id}")
    print(f"URL:    {url}")
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            print(f"  ERROR: bozo={feed.bozo}  bozo_exception={getattr(feed, 'bozo_exception', '?')}")
            return
        title = getattr(feed.feed, "title", "<no feed title>")
        lang = getattr(feed.feed, "language", "<no lang>")
        enc = sys.stdout.encoding
        title_safe = title.encode(enc, errors="replace").decode(enc)
        print(f"  Feed title: {title_safe}")
        print(f"  Language:   {lang}")
        print(f"  Entries:    {len(feed.entries)}")
        for i, entry in enumerate(feed.entries[:5]):
            et = getattr(entry, "title", "<no title>")
            el = getattr(entry, "link", "<no link>")
            # Encode safely for Windows console
            et_safe = et.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding)
            print(f"  [{i+1}] {et_safe}")
            print(f"       {el}")
    except Exception as exc:
        print(f"  EXCEPTION: {exc}")


def main() -> None:
    print("Probing Hebrew RSS candidates...")
    for source_id, url in CANDIDATES:
        probe(source_id, url)
    print("\nDone.")


if __name__ == "__main__":
    main()
