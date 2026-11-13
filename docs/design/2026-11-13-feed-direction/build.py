"""Fill the approved feed-direction mock (2026-11-13, #461) with real data.

Reference mock only, not product code. Reads, never writes:
  - frontend/dist-demo/demo-data/feed.json and meta.json (the public demo snapshot,
    written by scripts/demo-publish.ps1),
  - backend/app/taxonomy/entities.py (Hebrew team names for the results strip),
  - backend/data/signal_sports.db, opened read-only, for real final results.

Writes two files into OUT_DIR (keep it outside the repository: the output holds a
snapshot of the owner's feed and must not be committed):
  - feed-direction.html          the page without a document skeleton (as published
                                 as a claude.ai artifact)
  - feed-direction.preview.html  the same page with a doctype, for a local browser

Usage (from anywhere):
  python docs/design/2026-11-13-feed-direction/build.py OUT_DIR [--root REPO] [--no-results]

--root defaults to the repository that contains this script. Point it at another
checkout when the data lives there (a git worktree has no snapshot or database).
--no-results builds without the database; the results strip is then left out.
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "feed-direction.template.html"

# A hand-written sample, not a feed record: it exists only so the lead block (which
# appears only when the feed has a push) can be reviewed when the snapshot has none.
# The template's toggle adds or removes it.
SAMPLE_PUSH = dict(
    t='לקראת הדרבי: מכבי ת"א חתמה על הסכם חסות חדש',
    s="קניון MYMALL בלימסול יעניק חסות לצהובים במשחקי הבית ביורוליג בקפריסין.",
    d="push",
    src="ONE ספורט",
    u="https://www.one.co.il/",
    p=None,  # set to one hour before the snapshot time
    r="עדכון דחוף — חתימה · מכבי תל אביב (כדורסל) ברשימת המעקב שלך",
    n=1,
    m=[],
    lg="EuroLeague",
)

RESULTS_SQL = (
    "select competition_id, start_time, home_team_name, away_team_name, home_team_id,"
    " away_team_id, home_score, away_score from game_results"
    " where status='final' and home_score is not null and start_time<=?"
    " order by start_time desc limit 10"
)


def fail(message):
    sys.exit(f"build.py: {message}")


def need(path, hint):
    if not path.is_file():
        fail(f"missing input {path}\n  {hint}")
    return path


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")


def feed_items(feed):
    items = []
    for entry in feed:
        article = entry["article"]
        cluster = entry.get("cluster") or {}
        members = []
        for member in cluster.get("members", []):
            name = member["source_display_name"]
            if name not in members:
                members.append(name)
        items.append(
            dict(
                t=article.get("translated_title") or article["title"],
                s=article.get("subtitle") or "",
                d=entry["decision"],
                src=article["source_display_name"],
                u=article["url"],
                p=cluster.get("sort_at") or article["published_at"],
                r=entry.get("reason_he") or "",
                n=cluster.get("source_count") or 1,
                m=members,
                lg=article.get("league"),
            )
        )
    return items


def final_results(db_path, entities_path, until):
    source = entities_path.read_text(encoding="utf-8")
    hebrew = dict(re.findall(r'_team\(\s*"(team:[^"]+)",\s*"[^"]+",\s*"([^"]+)"', source))
    uri = db_path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute(RESULTS_SQL, (until,)).fetchall()
    except sqlite3.Error as exc:
        fail(f"could not read game_results from {db_path}: {exc}")
    finally:
        con.close()
    return [
        {
            "c": r[0],
            "t": r[1],
            "h": hebrew.get(r[4], r[2]),
            "a": hebrew.get(r[5], r[3]),
            "hs": r[6],
            "as": r[7],
        }
        for r in rows
    ]


def main():
    parser = argparse.ArgumentParser(description="Build the 2026-11-13 feed-direction mock.")
    parser.add_argument("out_dir", type=Path, help="output folder, outside the repository")
    parser.add_argument("--root", type=Path, default=HERE.parents[2], help="repository root holding the data")
    parser.add_argument("--no-results", action="store_true", help="skip the database; no results strip")
    args = parser.parse_args()

    root = args.root.resolve()
    demo = root / "frontend" / "dist-demo" / "demo-data"
    snapshot_hint = "build the demo snapshot first (scripts/demo-publish.ps1), or pass --root"
    feed = load_json(need(demo / "feed.json", snapshot_hint))
    meta = load_json(need(demo / "meta.json", snapshot_hint))
    template = need(TEMPLATE, "the template must sit next to this script").read_text(encoding="utf-8")
    if "/*DATA*/" not in template:
        fail(f"{TEMPLATE} has no /*DATA*/ placeholder")

    now = meta.get("generated_at")
    if not now:
        fail(f"{demo / 'meta.json'} has no generated_at")

    games = []
    if not args.no_results:
        db = need(root / "backend" / "data" / "signal_sports.db", "pass --no-results to build without it")
        entities = need(root / "backend" / "app" / "taxonomy" / "entities.py", "wrong --root?")
        games = final_results(db, entities, now)

    sample = dict(SAMPLE_PUSH, p=(datetime.fromisoformat(now) - timedelta(hours=1)).isoformat())
    items = feed_items(feed)
    data = json.dumps(dict(now=now, lastPush=sample, items=items, games=games), ensure_ascii=False)
    page = template.replace("/*DATA*/", data.replace("</", "<\\/"))

    out = args.out_dir.resolve()
    if out == root or root in out.parents:
        fail(f"{out} is inside the repository; the output holds feed data and must stay outside")
    out.mkdir(parents=True, exist_ok=True)
    (out / "feed-direction.html").write_text(page, encoding="utf-8")
    head = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    (out / "feed-direction.preview.html").write_text(head + page, encoding="utf-8")
    print(f"{len(items)} stories, {len(games)} results -> {out}")


if __name__ == "__main__":
    main()
