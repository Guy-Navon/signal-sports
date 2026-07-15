"""#124 — integrated pair / component evaluation over a frozen snapshot. READ-ONLY.

Runs the REAL `cluster_articles()` — hard gates, claim compatibility (#142),
intra-source stage (#123), lexical tiers, validated-anchor tier (#141+#137),
coherence — over the full snapshot, then scores:

  PAIR level       must-merge recovery / must-not-merge rejection / material-update
                   preservation, with the EXACT reason for every accepted and
                   rejected truth edge.
  COMPONENT level  purity against the adjudicated duplicate groups, false bridges,
                   material-update contamination, source-uniqueness (tier-I aware).
  PRODUCT level    the named Milestone 6 outcomes (Madar signing / Hankins /
                   Otooru / Storonski / Madar farewell / Noskova / Diarra).

The ranked-feed level (before/after on the real Guy feed) is a separate step —
it needs the feed service and profiles, not just the matcher.

Usage: python scripts/feed_dedup_eval_124.py <snapshot-db-with-anchors>
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clustering.config import DEFAULT_CONFIG as CFG                    # noqa: E402
from app.clustering.contract import ClusterInput                          # noqa: E402
from app.clustering.service import cluster_articles                       # noqa: E402

OUT = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def p(*a):
    print(*a, file=OUT)


def load(db_path: str) -> list[ClusterInput]:
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = c.execute(
        "select id,source,title,coalesce(subtitle,''),published_at,sport,event_type,"
        "event_certainty,entity_ids,primary_competition,story_anchors "
        "from articles where id like 'rss_%'"
    )
    out = []
    for r in rows:
        anchors = r[10]
        if isinstance(anchors, str):
            anchors = json.loads(anchors)
        out.append(ClusterInput(
            id=r[0], source=r[1], title=r[2], subtitle=r[3],
            published_at=datetime.fromisoformat(r[4].replace("Z", "+00:00")),
            sport=r[5], event_type=r[6], event_certainty=r[7],
            entity_ids=tuple(json.loads(r[8] or "[]")), primary_competition=r[9],
            story_anchors=tuple(anchors or ()),
        ))
    return out


def truth():
    groups = {}
    with (FIX / "feed_dedup_cases.json").open(encoding="utf-8") as fh:
        for g in json.load(fh)["duplicate_groups"]:
            groups[g["id"]] = {a["id"] for a in g["articles"]}
    with (FIX / "clustering_adversarial.json").open(encoding="utf-8") as fh:
        adv = json.load(fh)
    for g in adv["true_duplicates_from_sweep"]:
        groups[g["id"]] = {a["id"] for a in g["articles"]}

    # The two fixture files independently adjudicated overlapping views of the same
    # story (dup_storonski vs tp_storonski_chris_jones_replacement). Purity must be
    # judged against the UNION of overlapping truth groups — one story, one card.
    merged = True
    while merged:
        merged = False
        for ga, gb in combinations(list(groups), 2):
            if ga in groups and gb in groups and groups[ga] & groups[gb]:
                groups[f"{ga}+{gb}"] = groups.pop(ga) | groups.pop(gb)
                merged = True
                break

    must_not = [(n["id"], sorted(a["id"] for a in n["articles"]))
                for n in adv["must_not_merge"]]
    material = [(m["id"], sorted(a["id"] for a in m["articles"]))
                for m in adv["material_update_same_thread"]]
    return groups, must_not, material


def main():
    db = sys.argv[1]
    arts = load(db)
    by_id = {a.id: a for a in arts}
    groups, must_not, material = truth()

    result = cluster_articles(arts, CFG, collect_rejections=True)
    edge_set = {frozenset((e.article_a, e.article_b)): e for e in result.edges}
    rej = {frozenset((r.article_a, r.article_b)): r for r in result.rejections}
    comp_of = {}
    for c in result.clusters:
        for m in c.member_ids:
            comp_of[m] = c

    p("#" * 100)
    p("#124 — INTEGRATED PAIR / COMPONENT EVALUATION (real cluster_articles pipeline)")
    p("#" * 100)
    p(f"corpus: {len(arts)} articles | clusters: {len(result.clusters)} "
      f"| edges: {len(result.edges)} | excluded (in-play/state): {len(result.excluded_ids)}")
    tier_counts = {}
    for e in result.edges:
        tier_counts[e.tier] = tier_counts.get(e.tier, 0) + 1
    p(f"edges by tier: {dict(sorted(tier_counts.items()))}")

    # ── PAIR LEVEL ────────────────────────────────────────────────────────────
    p("\n" + "=" * 100)
    p("PAIR LEVEL — every truth pair, with its exact outcome")
    p("=" * 100)
    mm_hit = mm_tot = 0
    for gid, members in sorted(groups.items()):
        present = [m for m in members if m in by_id]
        for x, y in combinations(sorted(present), 2):
            k = frozenset((x, y))
            same = comp_of.get(x) is not None and comp_of.get(x) is comp_of.get(y)
            mm_tot += 1
            mm_hit += bool(same)
            if same:
                e = edge_set.get(k)
                via = f"edge tier {e.tier}" if e else "transitive (coherent)"
                p(f"  MERGED   {gid:<28} {x[:14]}~{y[:14]}  via {via}")
            else:
                r = rej.get(k)
                why = f"{r.reason} ({r.detail})" if r else "no edge, no recorded near-miss"
                p(f"  MISSED   {gid:<28} {x[:14]}~{y[:14]}  {why}")

    p("")
    over = 0
    for nid, ids in must_not:
        if len(ids) < 2 or any(i not in by_id for i in ids):
            continue
        x, y = ids[0], ids[1]
        same = comp_of.get(x) is not None and comp_of.get(x) is comp_of.get(y)
        over += bool(same)
        status = "!!! OVER-MERGED" if same else "kept apart"
        p(f"  {status:<16} {nid:<40} {x[:14]}~{y[:14]}")

    mat_ok = 0
    for mid, ids in material:
        if any(i not in by_id for i in ids):
            continue
        x, y = ids[0], ids[1]
        same = comp_of.get(x) is not None and comp_of.get(x) is comp_of.get(y)
        mat_ok += (not same)
        status = "!!! COLLAPSED" if same else "both visible"
        p(f"  {status:<16} {mid:<40} {x[:14]}~{y[:14]}")

    # ── COMPONENT LEVEL ───────────────────────────────────────────────────────
    p("\n" + "=" * 100)
    p("COMPONENT LEVEL — purity, bridges, material-update contamination")
    p("=" * 100)
    impure = 0
    for c in result.clusters:
        members = set(c.member_ids)
        touching = [gid for gid, g in groups.items() if members & g]
        pure = len(touching) <= 1 and (not touching or members <= groups[touching[0]])
        if not pure:
            impure += 1
            p(f"  !!! IMPURE {c.anchor_id}: members={sorted(members)} touches={touching}")
    material_ids = {i for _, ids in material for i in ids}
    contaminated = [c for c in result.clusters if set(c.member_ids) & material_ids]
    for c in contaminated:
        p(f"  !!! MATERIAL-UPDATE ARTICLE IN COMPONENT {c.anchor_id}: {sorted(c.member_ids)}")

    p(f"\n  components: {len(result.clusters)} | impure: {impure} "
      f"| material-update contamination: {len(contaminated)}")

    # ── PRODUCT OUTCOMES ─────────────────────────────────────────────────────
    p("\n" + "=" * 100)
    p("NAMED PRODUCT OUTCOMES")
    p("=" * 100)

    def one_component(gid):
        g = [m for m in groups.get(gid, ()) if m in by_id]
        if not g:
            return f"{gid}: NOT IN CORPUS"
        comps = {id(comp_of[m]) if comp_of.get(m) else f"solo:{m}" for m in g}
        n = len(comps)
        return f"{gid}: {len(g)} articles -> {n} card(s) {'OK' if n == 1 else '!!! EXPECTED 1'}"

    for gid in sorted(groups):
        p("  " + one_component(gid))

    p("\n" + "=" * 100)
    p("SUMMARY")
    p("=" * 100)
    p(f"  must-merge pairs recovered : {mm_hit}/{mm_tot}")
    p(f"  must-not-merge violated    : {over}")
    p(f"  material updates preserved : {mat_ok}/{len(material)}")
    p(f"  impure components          : {impure}")
    p(f"  material contamination     : {len(contaminated)}")
    OUT.flush()


if __name__ == "__main__":
    main()
