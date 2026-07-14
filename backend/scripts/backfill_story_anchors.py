"""Guarded re-enrichment of validated story anchors (#141).

A validator upgrade must refresh stored anchors WITHOUT re-ingesting articles. This script
re-runs the enrichment stage over stored rows and writes `story_anchors` +
`anchor_validator_version`.

  * DRY RUN BY DEFAULT. `--apply` is required to write; the protected live corpus (#106)
    additionally requires `--i-know-this-is-the-live-corpus`.
  * The candidate population for each article is the bounded window the hard gates define
    (same shape as candidate-scoped DF, #135) — anchors are corroborated against exactly the
    peers pair-evaluation will compare against.
  * Validation runs ONCE here. Pair clustering then reads `story_anchors` only — never a model
    or analyzer per pair.
  * A row is skipped when its stored `anchor_validator_version` already matches the current
    validator, so re-runs are cheap and idempotent (unless `--force`).

Validator is selected with `--validator {taxonomy,lexical,hybrid}` (default: lexical — the
deterministic offline resource; hybrid additionally needs a reachable local model).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _validator(name: str):
    from app.clustering.anchor_validators import (
        HybridValidator, LexicalFrequencyValidator, TaxonomyValidator,
    )
    return {"taxonomy": TaxonomyValidator, "lexical": LexicalFrequencyValidator,
            "hybrid": HybridValidator}[name]()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/signal_sports.db")
    ap.add_argument("--validator", choices=["taxonomy", "lexical", "hybrid"],
                    default="lexical")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="re-enrich even rows already at the current validator version")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

    from app.db.corpus_protection import is_protected_corpus_db
    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        raise SystemExit(
            f"REFUSED: {db} is the protected live corpus (#106).\n"
            "Re-run with --i-know-this-is-the-live-corpus to write to it."
        )

    from app.clustering.anchor_enrichment import enrich_article_anchors
    from app.clustering.config import DEFAULT_CONFIG as CFG
    from app.clustering.contract import ClusterInput
    from app.clustering.event_states import (
        is_clusterable_state, is_in_play, states_compatible, within_time_window,
    )
    from app.clustering.matcher import sports_hard_reject
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    validator = _validator(args.validator)
    version = validator.validator_version

    print(f"db: {db}", file=out)
    print(f"validator: {validator.validator_id} @ {version}  "
          f"(available={validator.available()})", file=out)
    if not validator.available():
        raise SystemExit("validator resource unavailable — refusing to write abstentions "
                         "over existing anchors")

    s = SessionLocal()
    rows = s.query(ArticleRow).filter(ArticleRow.id.like("rss_%")).all()

    def to_input(r):
        return ClusterInput(
            id=r.id, source=r.source, title=r.title, subtitle=r.subtitle or "",
            published_at=datetime.fromisoformat(r.published_at.replace("Z", "+00:00")),
            sport=r.sport, event_type=r.event_type, event_certainty=r.event_certainty,
            entity_ids=tuple(r.entity_ids or ()), primary_competition=r.primary_competition,
        )

    inputs = [to_input(r) for r in rows]

    def population(anchor):
        return [a for a in inputs
                if is_clusterable_state(a.event_type)
                and states_compatible(a.event_type, anchor.event_type)
                and not is_in_play(a.title, a.subtitle)
                and within_time_window(a.published_at, anchor.published_at,
                                       anchor.event_type, CFG)
                and not sports_hard_reject(a, anchor)]

    by_id = {a.id: a for a in inputs}
    changed = skipped = 0
    for r in rows:
        if not args.force and r.anchor_validator_version == version:
            skipped += 1
            continue
        anchor = by_id[r.id]
        pop = population(anchor) if is_clusterable_state(anchor.event_type) else None
        stored, _ = enrich_article_anchors(
            r.title, r.subtitle or "", validator, article_id=r.id, population=pop)
        payload = [sa.to_json() for sa in stored]
        if args.apply:
            r.story_anchors = payload
            r.anchor_validator_version = version
        changed += 1

    accepted_total = 0
    if args.apply:
        s.commit()
    # recompute for reporting even in dry-run
    for r in rows:
        anchor = by_id[r.id]
        pop = population(anchor) if is_clusterable_state(anchor.event_type) else None
        stored, _ = enrich_article_anchors(
            r.title, r.subtitle or "", validator, article_id=r.id, population=pop)
        accepted_total += len(stored)
    s.close()

    mode = "APPLIED" if args.apply else "DRY RUN — nothing written"
    print(f"\n{mode}: {changed} rows re-enriched, {skipped} already current", file=out)
    print(f"accepted anchors across corpus: {accepted_total} "
          f"({accepted_total/max(len(rows),1):.1f}/article)", file=out)
    out.flush()


if __name__ == "__main__":
    main()
