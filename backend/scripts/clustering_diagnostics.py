"""Shared diagnostic harness for #135 and #136. READ-ONLY. Changes no threshold, no default.

The coordination rule: both issues run against the SAME adjudicated pair corpus and emit the
SAME record format, so they can be compared individually AND in combination — and so neither
quietly absorbs the other.

  #135 asks: can evidence frequency identify useful tokens inside a VALID candidate population?
  #136 asks: can we build the missing primitive that separates named story identity from
             arbitrary rarity?

Neither earns activation credit here. Only #124 / #126 can grant that.

Usage:  python scripts/clustering_diagnostics.py [--db data/signal_sports.db]
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clustering.anchors import (  # noqa: E402
    build_name_lexicon, generate_anchor_candidates, shared_anchor_candidates,
    shared_anchors,
)
from app.clustering.candidate_scope import scoped_evidence  # noqa: E402
from app.clustering.config import DEFAULT_CONFIG as CFG  # noqa: E402
from app.clustering.contract import ClusterInput  # noqa: E402
from app.clustering.event_states import (  # noqa: E402
    is_clusterable_state, is_in_play, states_compatible, within_time_window,
)
from app.clustering.matcher import (  # noqa: E402
    _tier_thresholds, select_tier, sports_hard_reject,
)
from app.clustering.tokens import DocumentFrequency, jaccard, tokenize  # noqa: E402

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def p(*a):
    print(*a, file=OUT)


def load_corpus(db: str) -> list[ClusterInput]:
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
            "event_certainty,entity_ids,primary_competition from articles "
            "where id like 'rss_%'"
        )
    ]


def hard_gates_ok(a: ClusterInput, b: ClusterInput) -> bool:
    return (
        a.source != b.source
        and is_clusterable_state(a.event_type) and is_clusterable_state(b.event_type)
        and states_compatible(a.event_type, b.event_type)
        and not is_in_play(a.title, a.subtitle) and not is_in_play(b.title, b.subtitle)
        and within_time_window(a.published_at, b.published_at, a.event_type, CFG)
        and not sports_hard_reject(a, b)
    )


def adjudicated_pairs() -> dict[tuple[str, str], tuple[str, str]]:
    """(id_a, id_b) -> (verdict, case_id). The SHARED ground truth for both issues."""
    truth: dict[tuple[str, str], tuple[str, str]] = {}

    with (FIX / "feed_dedup_cases.json").open(encoding="utf-8") as fh:
        fd = json.load(fh)
    for g in fd["duplicate_groups"]:
        ids = [a["id"] for a in g["articles"]]
        for x, y in combinations(sorted(ids), 2):
            truth[(x, y)] = ("must_merge", g["id"])

    with (FIX / "clustering_adversarial.json").open(encoding="utf-8") as fh:
        adv = json.load(fh)
    for g in adv["true_duplicates_from_sweep"]:
        ids = [a["id"] for a in g["articles"]]
        for x, y in combinations(sorted(ids), 2):
            truth[(x, y)] = ("must_merge", g["id"])
    for n in adv["must_not_merge"]:
        ids = sorted(a["id"] for a in n["articles"])
        truth[(ids[0], ids[1])] = ("must_not_merge", n["id"])
    for m in adv["material_update_same_thread"]:
        ids = sorted(a["id"] for a in m["articles"])
        truth[(ids[0], ids[1])] = ("material_update", m["id"])
    return truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/signal_sports.db")
    args = ap.parse_args()

    arts = load_corpus(args.db)
    by_id = {a.id: a for a in arts}
    TOK = {a.id: tokenize(f"{a.title} {a.subtitle}") for a in arts}
    # The lexicon is corroborated by the CANDIDATE POPULATION, exactly as #135 scopes DF.
    # (A corpus-wide lexicon was measured first, as the worst case: it admits ordinary Hebrew
    #  words — אדום/שיא/הכל — and produces 3 over-merges. Scoping is the contract, not a
    #  convenience.)
    from app.clustering.candidate_scope import candidate_population
    _lex_cache: dict = {}

    def lex_for(a):
        k = f"{a.event_type}|{a.published_at.isoformat()}"
        if k not in _lex_cache:
            _lex_cache[k] = build_name_lexicon(candidate_population(a, arts, CFG))
        return _lex_cache[k]

    ANC = {a.id: generate_anchor_candidates(a.title, a.subtitle, lex_for(a)) for a in arts}
    DF_GLOBAL = DocumentFrequency.over(TOK.values())
    truth = adjudicated_pairs()

    p("#" * 100)
    p("#135 / #136 SHARED DIAGNOSTIC — read-only, no threshold changed, no default changed")
    p("#" * 100)
    p(f"corpus: {len(arts)} articles   adjudicated pairs: {len(truth)}")

    # ── #135: token status changes ───────────────────────────────────────────
    p("\n" + "=" * 100)
    p("#135 — TOKEN STATUS: global DF vs candidate-scoped DF")
    p("=" * 100)
    p(f"{'token':<12} {'df_global':>9} {'disc?':>6} | {'df_scoped':>9} {'pop':>5} {'disc?':>6} "
      f" | change              what it is")
    scope_cache: dict[str, object] = {}

    def scoped_for(a: ClusterInput):
        k = f"{a.event_type}|{a.published_at.isoformat()}"
        if k not in scope_cache:
            scope_cache[k] = scoped_evidence(a, arts, CFG, TOK)
        return scope_cache[k]

    PROBES = [
        ("מדר", "THE STORY'S SUBJECT (Yam Madar)", "ים מדר חתם"),
        ("הנקינס", "a subject (Hankins)", "נפרדה מזאק הנקינס"),
        ("אוטורו", "a subject (Otooru)", "דן אוטורו האריך"),
        ("חתם", "ACTION TEMPLATE ('signed')", "ים מדר חתם"),
        ("סיכם", "ACTION TEMPLATE ('agreed')", "סטרונסקי סיכם"),
        ("דולר", "money vocabulary ('dollar')", "ים מדר חתם"),
        ("יאללה", "an interjection ('yalla')", "הציגה את ים מדר"),
        ("פרק", "a filler noun ('chapter')", "הציגה את ים מדר"),
        ("לשלוש", "contract template ('for three')", "בראיינט האריך"),
        ("במו", "negotiation template", "ווילר במו"),
    ]
    for tok, what, probe_title in PROBES:
        host = next((a for a in arts if probe_title in f"{a.title} {a.subtitle}"
                     and tok in TOK[a.id]), None)
        if host is None:
            host = next((a for a in arts if tok in TOK[a.id]), None)
        if host is None:
            continue
        se = scoped_for(host)
        g_df, g_d = DF_GLOBAL.df(tok), DF_GLOBAL.is_discriminative(tok, CFG)
        s_df, s_d = se.df.df(tok), se.df.is_discriminative(tok, CFG)
        if not g_d and s_d:
            chg = "RESTORED  ✅"
        elif g_d and not s_d:
            chg = "SUPPRESSED"
        elif g_d and s_d:
            chg = "still disc ⚠️"
        else:
            chg = "still non-disc"
        p(f"{tok:<12} {g_df:>9} {str(g_d):>6} | {s_df:>9} {se.population_size:>5} "
          f"{str(s_d):>6}  | {chg:<19} {what}")

    # ── #136: anchors on the adjudicated corpus ──────────────────────────────
    p("\n" + "=" * 100)
    p("#136 — ANCHORS on every adjudicated pair")
    p("=" * 100)
    p(f"{'verdict':<16} {'case':<38} {'shared anchors'}")
    for (x, y), (verdict, case) in sorted(truth.items(), key=lambda kv: kv[1][0]):
        if x not in by_id or y not in by_id:
            continue
        sa = shared_anchor_candidates(ANC[x], ANC[y])   # CANDIDATE level = the recall ceiling
        mark = {"must_merge": "✅" if sa else "❌ NO ANCHOR",
                "must_not_merge": "❌ ANCHOR!" if sa else "✅",
                "material_update": "(shares)" if sa else "(none)"}[verdict]
        p(f"{verdict:<16} {case:<38} {mark:<12} {[s.replace('name:','') for s in sa]}")

    # ── Combined: pair-level over the FULL corpus ────────────────────────────
    p("\n" + "=" * 100)
    p("PAIR LEVEL — full corpus, hard gates enforced")
    p("=" * 100)
    ELIG = [(a, b) for a, b in combinations(arts, 2) if hard_gates_ok(a, b)]
    p(f"eligible cross-source pairs: {len(ELIG)}")

    def baseline(a, b):
        A, B = TOK[a.id], TOK[b.id]
        jm, mr = _tier_thresholds(select_tier(a, b), CFG)
        return jaccard(A, B) >= jm and len(DF_GLOBAL.discriminative_shared(A, B, CFG)) >= mr

    def m135(a, b):
        """#135 alone: candidate-scoped DF evidence, Jaccard floor kept."""
        A, B = TOK[a.id], TOK[b.id]
        jm, mr = _tier_thresholds(select_tier(a, b), CFG)
        se = scoped_for(a)
        return jaccard(A, B) >= jm and len(se.df.discriminative_shared(A, B, CFG)) >= mr

    def m136_validated(a, b):
        """#136 AS IT WILL SHIP: only VALIDATED anchors are merge evidence. With no Hebrew
        validator yet, this abstains — which is the correct, safe behavior."""
        return bool(shared_anchors(ANC[a.id], ANC[b.id]))

    def m136_no_jaccard(a, b):
        """CANDIDATE level — the RECALL CEILING a validator would have to work with.
        NOT shippable: this is what leaks אדום / שיא / הכל."""
        return bool(shared_anchor_candidates(ANC[a.id], ANC[b.id]))

    def combined(a, b):
        """#135 + #136: a shared anchor AND candidate-scoped discriminative evidence.
        No Jaccard floor — the crutch is what we are trying to remove."""
        if not shared_anchor_candidates(ANC[a.id], ANC[b.id]):
            return False
        A, B = TOK[a.id], TOK[b.id]
        _, mr = _tier_thresholds(select_tier(a, b), CFG)
        se = scoped_for(a)
        return len(se.df.discriminative_shared(A, B, CFG)) >= mr

    p(f"\n{'mechanism':<34} {'must_merge':>11} {'must_not':>9} {'mat_upd':>8} "
      f"{'corpus edges':>13}")
    for name, fn in (
        ("M0 baseline (production)", baseline),
        ("#135 candidate-scoped DF", m135),
        ("#136 VALIDATED anchors (ships)", m136_validated),
        ("#136 candidates (recall ceiling)", m136_no_jaccard),
        ("#135 + #136 candidates", combined),
    ):
        tp = fpn = mu = 0
        for (x, y), (verdict, _c) in truth.items():
            if x not in by_id or y not in by_id:
                continue
            a, b = by_id[x], by_id[y]
            if not hard_gates_ok(a, b):
                continue
            got = fn(a, b)
            if verdict == "must_merge" and got:
                tp += 1
            if verdict == "must_not_merge" and got:
                fpn += 1
            if verdict == "material_update" and got:
                mu += 1
        total_mm = sum(1 for (x, y), (v, _) in truth.items()
                       if v == "must_merge" and x in by_id and y in by_id
                       and hard_gates_ok(by_id[x], by_id[y]))
        edges = sum(1 for a, b in ELIG if fn(a, b))
        p(f"{name:<34} {tp:>6}/{total_mm:<4} {fpn:>9} {mu:>8} {edges:>13}")

    p("\n  must_not > 0  = OVER-MERGE (fails D6)")
    p("  mat_upd   > 0  = collapsed a MATERIAL UPDATE (fails the product policy)")

    # ── Component level ──────────────────────────────────────────────────────
    p("\n" + "=" * 100)
    p("COMPONENT LEVEL — connected components (purity is the KPI, not pair recall)")
    p("=" * 100)

    def components(fn):
        parent = {a.id: a.id for a in arts}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b in ELIG:
            if fn(a, b):
                ra, rb = find(a.id), find(b.id)
                if ra != rb:
                    parent[ra] = rb
        groups: dict[str, list[str]] = {}
        for a in arts:
            groups.setdefault(find(a.id), []).append(a.id)
        return [g for g in groups.values() if len(g) > 1]

    with (FIX / "feed_dedup_cases.json").open(encoding="utf-8") as fh:
        FD = json.load(fh)
    TRUE_GROUPS = {g["id"]: {a["id"] for a in g["articles"]}
                   for g in FD["duplicate_groups"]}

    for name, fn in (("M0 baseline", baseline), ("#135 + #136 combined", combined)):
        comps = components(fn)
        p(f"\n── {name}: {len(comps)} components ──")
        impure = 0
        for c in comps:
            cs = set(c)
            owners = [gid for gid, members in TRUE_GROUPS.items() if cs & members]
            pure = len(owners) <= 1 and (not owners or cs <= TRUE_GROUPS[owners[0]])
            if not pure:
                impure += 1
            tag = "PURE " if pure else "IMPURE"
            label = owners[0] if len(owners) == 1 else (owners or ["(unknown story)"])[0]
            p(f"   [{tag}] n={len(c)}  {label}")
            for aid in sorted(c, key=lambda i: by_id[i].published_at):
                p(f"        [{by_id[aid].source:18}] {by_id[aid].title[:58]}")
        p(f"   → impure components: {impure}")

    OUT.flush()


if __name__ == "__main__":
    main()
