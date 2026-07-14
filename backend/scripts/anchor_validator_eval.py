"""#141 — evaluate the three anchor-validation approaches. READ-ONLY. No winner pre-selected.

All three consume the SAME persisted candidate records, produced once by
`generate_candidates()`. None of them sees a bare string: every candidate carries its token
offsets, field origin, surrounding context, grammatical pattern and inferred role.
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
import time
from datetime import datetime
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clustering.anchor_contract import ABSTAINED, REJECTED  # noqa: E402
from app.clustering.anchor_validators import (  # noqa: E402
    HybridValidator, LexicalFrequencyValidator, LocalModelValidator, TaxonomyValidator,
)
from app.clustering.anchors import build_name_lexicon, generate_candidates  # noqa: E402
from app.clustering.candidate_scope import candidate_population  # noqa: E402
from app.clustering.config import DEFAULT_CONFIG as CFG  # noqa: E402
from app.clustering.contract import ClusterInput  # noqa: E402
from app.clustering.event_states import (  # noqa: E402
    is_clusterable_state, is_in_play, states_compatible, within_time_window,
)
from app.clustering.matcher import sports_hard_reject  # noqa: E402

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def p(*a):
    print(*a, file=OUT)


# ── ADJUDICATED ANCHOR SPANS — hand-labelled, never auto-derived ─────────────
# Ground truth is a human verdict. Storonski is why: automated candidate generation may
# surface review targets; it may NEVER assign ground truth.
MUST_ACCEPT = {
    "מדר", "הנקינס", "אוטורו", "סטורנסקי", "סטרונסקי", "בראיינט", "דיארה",
    "נוסקובה", "מוחובה", "ווילר", "איטודיס", "חלאילי", "סינר",
}
MUST_REJECT = {
    "אדום", "שיא", "הכל", "יאללה", "דולר", "פרק", "נשאר", "חדש", "גדול",
    "מורם", "ראש", "חשוב", "בשיחות", "במו", "קלה", "דצמבר", "אמצע", "בלבד",
}


def load(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    return [
        ClusterInput(
            id=r[0], source=r[1], title=r[2], subtitle=r[3] or "",
            published_at=datetime.fromisoformat(r[4].replace("Z", "+00:00")),
            sport=r[5], event_type=r[6], event_certainty=r[7],
            entity_ids=tuple(json.loads(r[8] or "[]")), primary_competition=r[9],
        )
        for r in c.execute(
            "select id,source,title,coalesce(subtitle,''),published_at,sport,event_type,"
            "event_certainty,entity_ids,primary_competition from articles where id like 'rss_%'"
        )
    ]


def hard_ok(a, b):
    return (a.source != b.source
            and is_clusterable_state(a.event_type) and is_clusterable_state(b.event_type)
            and states_compatible(a.event_type, b.event_type)
            and not is_in_play(a.title, a.subtitle) and not is_in_play(b.title, b.subtitle)
            and within_time_window(a.published_at, b.published_at, a.event_type, CFG)
            and not sports_hard_reject(a, b))


def truth_pairs():
    t = {}
    with (FIX / "feed_dedup_cases.json").open(encoding="utf-8") as fh:
        for g in json.load(fh)["duplicate_groups"]:
            for x, y in combinations(sorted(a["id"] for a in g["articles"]), 2):
                t[(x, y)] = "must_merge"
    with (FIX / "clustering_adversarial.json").open(encoding="utf-8") as fh:
        adv = json.load(fh)
    for g in adv["true_duplicates_from_sweep"]:
        for x, y in combinations(sorted(a["id"] for a in g["articles"]), 2):
            t[(x, y)] = "must_merge"
    for n in adv["must_not_merge"]:
        i = sorted(a["id"] for a in n["articles"])
        t[(i[0], i[1])] = "must_not_merge"
    for m in adv["material_update_same_thread"]:
        i = sorted(a["id"] for a in m["articles"])
        t[(i[0], i[1])] = "material_update"
    return t


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else "data/signal_sports.db"
    arts = load(db)
    by_id = {a.id: a for a in arts}
    truth = truth_pairs()

    lex_cache = {}

    def lex_for(a):
        k = f"{a.event_type}|{a.published_at.isoformat()}"
        if k not in lex_cache:
            lex_cache[k] = build_name_lexicon(candidate_population(a, arts, CFG))
        return lex_cache[k]

    t0 = time.perf_counter()
    CANDS = {a.id: generate_candidates(a.title, a.subtitle, lex_for(a), a.id, "pop")
             for a in arts}
    gen_ms = (time.perf_counter() - t0) * 1000
    total = sum(len(v) for v in CANDS.values())

    p("#" * 100)
    p("#141 — ANCHOR VALIDATOR EVALUATION. No winner pre-selected.")
    p("#" * 100)
    p(f"corpus: {len(arts)} articles | candidate records: {total} "
      f"| generation {gen_ms:.0f} ms ({gen_ms/len(arts):.1f} ms/article)")

    validators = [
        ("V0 taxonomy (baseline)", TaxonomyValidator()),
        ("V1 lexical frequency", LexicalFrequencyValidator()),
        ("V2 local model", LocalModelValidator()),
        ("V3 hybrid", HybridValidator()),
    ]

    p("\n" + "=" * 100)
    p("AVAILABILITY + FAIL-CLOSED")
    p("=" * 100)
    for name, v in validators:
        p(f"  {name:<26} available={str(v.available()):<6} version={v.validator_version}")

    results = {}
    for name, v in validators:
        model_bound = isinstance(v, LocalModelValidator)
        scope = ({i for pr in truth for i in pr} if model_bound else set(CANDS))
        t0 = time.perf_counter()
        dec = {}
        for aid in scope:
            for c in CANDS.get(aid, ()):
                dec[c.span_id()] = (c, v.validate(c))
        results[name] = (v, dec, time.perf_counter() - t0, scope)

    p("\n" + "=" * 100)
    p("SPAN LEVEL — precision / recall on ADJUDICATED spans (hand-labelled)")
    p("=" * 100)
    p(f"{'validator':<26} {'prec':>6} {'recall':>7} {'abstain':>8} {'TP':>4} {'FP':>4} {'FN':>4}"
      f" | verdict on אדום / שיא / הכל")
    for name, (v, dec, el, scope) in results.items():
        tp = fp = fn = ab = 0
        killers = {"אדום": "-", "שיא": "-", "הכל": "-"}
        judged = 0
        for c, d in dec.values():
            toks = set(c.normalized.split())
            g_acc = bool(toks & MUST_ACCEPT) and not (toks & MUST_REJECT)
            g_rej = bool(toks & MUST_REJECT)
            if not (g_acc or g_rej):
                continue
            judged += 1
            if c.normalized in killers:
                killers[c.normalized] = d.decision
            if d.decision == ABSTAINED:
                ab += 1
                if g_acc:
                    fn += 1
            elif d.is_accepted:
                tp += 1 if g_acc else 0
                fp += 1 if g_rej else 0
            elif d.decision == REJECTED and g_acc:
                fn += 1
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        ks = "  ".join(f"{k}={killers[k]}" for k in ("אדום", "שיא", "הכל"))
        p(f"{name:<26} {prec:>6.2f} {rec:>7.2f} {ab/judged if judged else 0:>8.0%} "
          f"{tp:>4} {fp:>4} {fn:>4} | {ks}")

    p("\n" + "=" * 100)
    p("PAIR + COMPONENT LEVEL  (primary metric: validated-anchor PRECISION, then purity)")
    p("=" * 100)
    ELIG = [(a, b) for a, b in combinations(arts, 2) if hard_ok(a, b)]
    with (FIX / "feed_dedup_cases.json").open(encoding="utf-8") as fh:
        TRUE_GROUPS = {g["id"]: {a["id"] for a in g["articles"]}
                       for g in json.load(fh)["duplicate_groups"]}

    p(f"{'validator':<26} {'must_merge':>11} {'over':>5} {'mat-upd':>8} {'edges':>7} "
      f"{'impure':>7} {'latency/article':>16}")
    for name, (v, dec, el, scope) in results.items():
        def keys(aid):
            out = set()
            for c in CANDS.get(aid, ()):
                d = dec.get(c.span_id())
                if d and d[1].is_accepted and c.role in ("subject", "quoted", "unknown"):
                    out.add(d[1].normalized_anchor or c.normalized)
            return out

        K = {aid: keys(aid) for aid in scope}

        def edge(a, b):
            return bool(K.get(a.id, set()) & K.get(b.id, set()))

        mm = om = mu = 0
        for (x, y), verdict in truth.items():
            if x not in by_id or y not in by_id or not hard_ok(by_id[x], by_id[y]):
                continue
            if edge(by_id[x], by_id[y]):
                mm += verdict == "must_merge"
                om += verdict == "must_not_merge"
                mu += verdict == "material_update"
        tot_mm = sum(1 for (x, y), vd in truth.items() if vd == "must_merge"
                     and x in by_id and y in by_id and hard_ok(by_id[x], by_id[y]))

        if scope == set(CANDS):
            edges = [(a, b) for a, b in ELIG if edge(a, b)]
            par = {a.id: a.id for a in arts}

            def find(z):
                while par[z] != z:
                    par[z] = par[par[z]]
                    z = par[z]
                return z

            for a, b in edges:
                ra, rb = find(a.id), find(b.id)
                if ra != rb:
                    par[ra] = rb
            comps = {}
            for a in arts:
                comps.setdefault(find(a.id), []).append(a.id)
            impure = 0
            for c in [g for g in comps.values() if len(g) > 1]:
                cs = set(c)
                own = [g for g, m in TRUE_GROUPS.items() if cs & m]
                if not (len(own) <= 1 and (not own or cs <= TRUE_GROUPS[own[0]])):
                    impure += 1
            estr, istr = f"{len(edges):>7}", f"{impure:>7}"
        else:
            estr = istr = "(scoped)"

        p(f"{name:<26} {mm:>6}/{tot_mm:<4} {om:>5} {mu:>8} {estr:>7} {istr:>7} "
          f"{el/max(len(scope),1)*1000:>13.1f} ms")

    p("\n" + "=" * 100)
    p("OPERATIONAL")
    p("=" * 100)
    v2 = dict(validators)["V2 local model"]
    v3 = dict(validators)["V3 hybrid"]
    p(f"  candidate records / article   : {total/len(arts):.1f}")
    p(f"  V2 model calls made           : {v2.calls}")
    p(f"  V2 calls for a FULL pass      : ~{total} (one per candidate)")
    p(f"  V3 escalations to the model   : {v3.escalations}  "
      f"(the deterministic resource decided everything else)")
    p("\n  DETERMINISM — same candidate, 3 runs:")
    probe = next(c for cs in CANDS.values() for c in cs if c.normalized == "מדר")
    for name, v in validators:
        if not v.available():
            p(f"    {name:<26} UNAVAILABLE -> fails closed (abstains)")
            continue
        runs = [v.validate(probe).decision for _ in range(3)]
        p(f"    {name:<26} {runs}  "
          f"{'STABLE' if len(set(runs)) == 1 else '*** UNSTABLE ***'}")
    OUT.flush()


if __name__ == "__main__":
    main()
