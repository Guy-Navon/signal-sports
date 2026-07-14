"""Apply ONLY the #113 corrections to a COPY, on top of the existing stored facts.

This isolates the effect of #113 exactly. A full reclassification would ALSO re-roll every
LLM verdict, changing many articles for reasons unrelated to the change under test — that
"after" would not be comparable to a "before" that was itself LLM-derived.

Applies, in order:
  1. unsupported domain (MMA/UFC/boxing)      -> sport = unknown          [guardrail 0]
  2. committed sport vocabulary contradicts   -> sport = proven sport     [guardrail 1b]
  3. stored event_type no longer has evidence -> recompute via rules      [event blockers]

Refuses the protected live corpus.
"""
import argparse, io, json, os, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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

    from app.classification.event_evidence import validate_event_evidence
    from app.classification.source_hints import extract_source_sport_hint
    from app.classification.sport_guards import committed_sport, is_unsupported_sport
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.ingestion.classifier import classify

    s = SessionLocal()
    log, kinds = [], Counter()
    for a in s.query(ArticleRow).all():
        text = f"{(a.title or '').lower()} {(a.subtitle or '').lower()}"
        before = (a.sport, a.event_type)
        sport, event = a.sport, a.event_type
        why = []

        if is_unsupported_sport(text):
            if sport != "unknown":
                sport, why = "unknown", why + ["guardrail0_unsupported_domain"]
        else:
            proven = committed_sport(text)
            if proven is not None and proven != sport:
                sport, why = proven, why + ["guardrail1b_committed_vocabulary"]

        if event and event != "news":
            ev = validate_event_evidence(event, text, source="rules", sport=sport)
            if not ev.valid:
                hint = extract_source_sport_hint(a.source or "", a.url or "")
                r = classify(a.title or "", source_id=a.source or "",
                             language=a.language or "he", url=a.url or "",
                             subtitle=a.subtitle, source_sport_hint=hint)
                if r.event_type != event:
                    event, why = r.event_type, why + ["event_evidence_blocked"]

        if (sport, event) != before:
            a.sport, a.event_type = sport, event
            for w in why:
                kinds[w] += 1
            log.append({"id": a.id, "source": a.source, "title": a.title,
                        "before": list(before), "after": [sport, event], "why": why})
    s.commit()
    s.close()

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print(f"#113 corrections applied to {db.name}: {len(log)} articles changed", file=out)
    for k, n in kinds.most_common():
        print(f"  {k}: {n}", file=out)
    for e in log:
        print(f"  [{e['source']:20}] {e['before']} -> {e['after']}  {e['title'][:58]}", file=out)
    out.flush()
    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(log, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
