"""Reclassify a COPY of the corpus with the FULL pipeline (#113). Never the live corpus.

Replicates the production path (rules -> LLM -> merge_with_guardrails -> league/sport
compat), so the "after" facts are comparable to the "before" facts, which were also
LLM-derived. A deterministic-only pass would NOT be comparable: it would flip every
LLM-classified article for reasons unrelated to the change under test.

    python scripts/reclassify_copy.py --db data/qa_after_113.db
"""
import argparse, io, json, os, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")   # same provider config as production


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    db = Path(args.db).resolve()

    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
    from app.db.corpus_protection import is_protected_corpus_db
    if is_protected_corpus_db():
        raise SystemExit(f"REFUSED: {db} is the protected live corpus. Use a copy.")

    from app.classification.merge import merge_with_guardrails, normalize_league_sport_compatibility
    from app.classification.service import get_llm_provider
    from app.classification.source_hints import extract_source_sport_hint
    from app.classification.validation import LLM_MIN_CONFIDENCE
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.ingestion.classifier import classify, _has_football_maccabi_context

    provider = get_llm_provider()
    s = SessionLocal()
    rows = s.query(ArticleRow).all()
    changed, log = Counter(), []

    for a in rows:
        hint = extract_source_sport_hint(a.source or "", a.url or "")
        sub = a.subtitle
        rules = classify(a.title or "", source_id=a.source or "", language=a.language or "he",
                         url=a.url or "", subtitle=sub, source_sport_hint=hint)
        llm_raw = provider.classify_title(a.title or "", a.language or "he", subtitle=sub) \
            if provider.can_classify else None

        if llm_raw is None or llm_raw.confidence < LLM_MIN_CONFIDENCE:
            final = rules
        else:
            final, _ = merge_with_guardrails(
                llm_raw, rules, (a.title or "").lower(),
                football_maccabi_detected=_has_football_maccabi_context((a.title or "").lower()),
                source_sport_hint=hint,
                subtitle_lower=sub.lower() if sub else None,
            )
        final = normalize_league_sport_compatibility(final)

        before, after = (a.sport, a.event_type), (final.sport, final.event_type)
        if before != after:
            changed[(before, after)] += 1
            log.append({"id": a.id, "source": a.source, "title": a.title,
                        "before": list(before), "after": list(after)})
        a.sport, a.event_type, a.event_certainty = final.sport, final.event_type, final.event_certainty
        a.league, a.importance, a.confidence = final.league, final.importance, final.confidence
        a.tags, a.entities = final.tags, final.entities
    s.commit()
    s.close()

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print(f"reclassified {len(rows)} on {db.name}; (sport,event) changed: {len(log)}", file=out)
    for (b, a_), n in changed.most_common(15):
        print(f"  {b} -> {a_} : {n}", file=out)
    out.flush()
    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(log, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
