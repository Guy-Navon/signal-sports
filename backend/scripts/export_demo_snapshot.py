"""Export the public demo snapshot (#458): the live consumer feed of profile
``guy`` as static JSON for the read-only demo on Firebase Hosting.

Usage (from the main checkout, the live worker may keep running):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\export_demo_snapshot.py --out frontend\\dist-demo\\demo-data

Options:
    --out DIR        where feed.json, results.json and meta.json are written (required)
    --db PATH        SQLite database to read. Default: the sqlite DATABASE_URL
                     (from the environment or backend/.env, relative paths taken
                     from backend/ like the API does), else backend/data/signal_sports.db
    --env-file PATH  settings file loaded like app.main does (override=False).
                     Default: backend/.env
    --allow-empty    write an empty feed instead of exiting 3

The database is opened read-only and never modified, and no usage is recorded.
Exit codes: 0 written; 1 export failed; 2 usage error; 3 the feed is empty
(on the live corpus: the worker stopped and nothing is inside the freshness
window). On 1 and 3 nothing is written, the previous files stay as they were,
and the publish script must not deploy.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _load_env_file(env_file: pathlib.Path) -> None:
    """Same contract as app.main._load_dotenv: shell values win (override=False)."""
    if not env_file.exists():
        return
    from dotenv import load_dotenv

    load_dotenv(env_file, override=False)


def _resolve_db(explicit: pathlib.Path | None) -> pathlib.Path:
    if explicit is not None:
        return explicit.resolve()
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        path = pathlib.Path(url[len("sqlite:///"):])
        return (path if path.is_absolute() else BACKEND / path).resolve()
    return (BACKEND / "data" / "signal_sports.db").resolve()


def build_results_snapshot(db_path: pathlib.Path) -> dict:
    """The demo profile's results, upcoming games and available stored details.

    Use the exporter's read-only engine: no sync, provider requests or writes.
    Keep the API wire shape so the demo uses the product's result normalizer.
    """
    from sqlalchemy.orm import sessionmaker

    from fastapi import HTTPException

    from app.api.routes_results import get_detail_for_user, get_results_for_user
    from app.ops.demo_snapshot import DEMO_USER_ID, readonly_engine
    from app.results.settings import results_enabled
    from app.results.status import FINAL, SCHEDULED

    if not results_enabled():
        return {"has_preferences": False, "games": [], "team_games": [], "followed_team_ids": [], "details": {}}

    engine = readonly_engine(db_path)
    try:
        with sessionmaker(bind=engine, autoflush=False)() as session:
            response = get_results_for_user(user_id=DEMO_USER_ID, session=session, limit=200)
            payload = response.model_dump(mode="json")
            games = [_public_game(game) for game in payload["games"] if game["status"] in (FINAL, SCHEDULED)]
            team_games = [_public_game(game) for game in payload.get("team_games", []) if game["status"] == FINAL]
            details = {}
            for game in [*games, *team_games]:
                if game["status"] != FINAL or not game["detail_available"]:
                    game["detail_available"] = False
                    continue
                if game["id"] in details:
                    continue
                try:
                    detail = get_detail_for_user(DEMO_USER_ID, game["id"], session)
                except HTTPException as exc:
                    if exc.status_code != 404:
                        raise
                    game["detail_available"] = False
                    continue
                details[game["id"]] = _public_detail(detail.model_dump(mode="json"))
            session.rollback()
    finally:
        engine.dispose()
    return {"has_preferences": bool(payload.get("has_preferences")), "games": games,
            "team_games": team_games, "followed_team_ids": payload.get("followed_team_ids", []), "details": details}


# Public sports data only. New API fields stay private until explicitly added.
_PUBLIC_GAME_FIELDS = ("id", "competition_id", "competition_he", "competition_en", "sport",
                       "season", "stage", "status", "start_time", "local_date", "winner",
                       "relevance_reason", "venue", "attendance")
_PUBLIC_SIDE_FIELDS = ("id", "name", "name_provider", "score", "is_winner", "rank")
_PUBLIC_PLAYER_FIELDS = ("side", "name", "entity_id", "source_player_id", "minutes")
_PUBLIC_PLAYER_STATS = (
    "points", "Points", "PTS", "rebounds", "TotalRebounds", "REB", "assists", "Assistances", "AST",
    "plus_minus", "Plusminus", "+/-", "starter", "IsStarter", "FG", "3PT", "FT",
    "fg2_made", "fg2_missed", "fg3_made", "fg3_missed", "ft_made", "ft_missed",
    "FieldGoalsMade2", "FieldGoalsAttempted2", "FieldGoalsMade3", "FieldGoalsAttempted3",
    "FreeThrowsMade", "FreeThrowsAttempted", "goals", "yellow_cards", "red_cards",
)
_PUBLIC_TEAM_STATS = (
    "rank", "bench_points", "benchPoints", "pts_in_the_paint", "pointsInPaint",
    "biggest_lead", "largestLead", "lead_changes", "leadChanges", "fastBreakPoints",
    "pts_from_turnovers", "turnoverPoints", "second_chance_pts",
)


def _pick(data: dict, fields: tuple) -> dict:
    return {key: data[key] for key in fields if key in data}


def _public_player(player: dict) -> dict:
    return {**_pick(player, _PUBLIC_PLAYER_FIELDS),
            "stats": _pick(player.get("stats") or {}, _PUBLIC_PLAYER_STATS)}


def _public_game(game: dict) -> dict:
    public = _pick(game, _PUBLIC_GAME_FIELDS)
    for side in ("home", "away"):
        public[side] = _pick(game.get(side) or {}, _PUBLIC_SIDE_FIELDS)
    public["leaders"] = [_pick(leader, ("side", "name", "entity_id", "stat", "value"))
                         for leader in game.get("leaders", [])]
    public["chosen_player_lines"] = [_public_player(player) for player in game.get("chosen_player_lines", [])]
    public["detail_available"] = bool(game.get("detail_available"))
    return public


def _public_detail(detail: dict) -> dict:
    team_stats = {}
    for side in ("home", "away"):
        raw = (detail.get("team_stats") or {}).get(side) or {}
        stats = _pick(raw, _PUBLIC_TEAM_STATS)
        for key in ("quarters", "quarter_scores"):
            periods = raw.get(key)
            if isinstance(periods, list):
                stats[key] = [value if type(value) in (int, float, str) else None for value in periods]
            elif isinstance(periods, dict):
                stats[key] = {name: value for name, value in periods.items()
                              if name.lower().startswith(("q", "ot")) and name[-1:].isdigit()
                              and type(value) in (int, float, str)}
        team_stats[side] = stats
    return {**_pick(detail, ("game_id", "venue", "attendance")),
            "players": [_public_player(player) for player in detail.get("players", [])],
            "team_stats": team_stats}


def export_demo_snapshot(db_path: pathlib.Path, out_dir: pathlib.Path, *, allow_empty: bool = False) -> dict:
    """Stage all three files before replacing the previous public snapshot.

    A feed/results read or serialization failure leaves every published file
    untouched. Rename only complete files on the same filesystem, meta last.
    """
    from app.ops.demo_snapshot import export_snapshot

    out_dir = pathlib.Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".demo-snapshot-", dir=out_dir.parent) as temporary:
        stage = pathlib.Path(temporary)
        meta = export_snapshot(db_path, stage, allow_empty=allow_empty)
        results = build_results_snapshot(db_path)
        (stage / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in ("feed.json", "results.json", "meta.json"):
            os.replace(stage / name, out_dir / name)
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--db", type=pathlib.Path)
    parser.add_argument("--env-file", type=pathlib.Path, default=BACKEND / ".env")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args(argv)

    _load_env_file(args.env_file)
    db_path = _resolve_db(args.db)

    # DEPLOY_ENV=dev must not open the production corpus (#265), here as anywhere.
    from app.core.deploy_mode import UnsafeDeployConfig, assert_database_allowed

    try:
        assert_database_allowed(f"sqlite:///{db_path}")
    except UnsafeDeployConfig as exc:
        print(f"EXPORT FAILED: {exc}", file=sys.stderr)
        return 1
    # app.db.database builds a module-level engine from DATABASE_URL at import.
    # The exporter never uses it, but point it at a read-only URI anyway, so an
    # unexpected use fails loudly instead of creating or writing a file.
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_uri()}?mode=ro&uri=true"

    from app.ops.demo_snapshot import EmptyFeedError, ExportError

    try:
        meta = export_demo_snapshot(db_path, args.out, allow_empty=args.allow_empty)
    except EmptyFeedError as exc:
        print(f"EXPORT SKIPPED: {exc}", file=sys.stderr)
        return 3
    except ExportError as exc:
        print(f"EXPORT FAILED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — any failure must stop the publish
        print(f"EXPORT FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    feed_bytes = (args.out / "feed.json").stat().st_size
    results_bytes = (args.out / "results.json").stat().st_size
    print(f"demo snapshot written to {args.out.resolve()}: {meta['item_count']} items, "
          f"feed.json {feed_bytes} bytes, results.json {results_bytes} bytes, "
          f"last cycle {meta['last_successful_cycle_at']}, "
          f"generated {meta['generated_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
