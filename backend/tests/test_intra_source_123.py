"""#123 — intra-source near-republish dedup: a dedicated stage, NOT blanket
same-source clustering.

The cross-source hard gate is untouched (byte-identical behaviour is asserted
below). The new stage collapses ONE thing: the same newsroom republishing the
same story (Noskova). Every same-source hazard the gate was built for — live
updates, rumour → confirmation, different-angle pieces — is locked as a
negative here, with the REAL corpus traps, not synthetic strawmen.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.clustering.config import DEFAULT_CONFIG as CFG
from app.clustering.contract import ClusterInput
from app.clustering.coherence import select_representative
from app.clustering.intra_source import TIER_INTRA_SOURCE, IntraRejection, intra_source_match
from app.clustering.service import cluster_articles
from app.clustering.tokens import DocumentFrequency, tokenize

FIXTURES = Path(__file__).parent / "fixtures"
BASE = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


def _load_noskova() -> list[ClusterInput]:
    with (FIXTURES / "feed_dedup_cases.json").open(encoding="utf-8") as fh:
        group = next(
            g for g in json.load(fh)["duplicate_groups"]
            if g["id"] == "dup_noskova_same_source"
        )
    return [
        ClusterInput(
            id=a["id"], source=a["source"], title=a["title"],
            subtitle=a.get("subtitle") or "",
            published_at=datetime.fromisoformat(a["published_at"]),
            sport=a["sport"], event_type=a["event_type"],
            event_certainty=a.get("event_certainty"),
            entity_ids=tuple(a.get("entity_ids") or ()),
            primary_competition=a.get("primary_competition"),
        )
        for a in group["articles"]
    ]


def _art(_id, title, subtitle="", source="ynet_sport", event="signing",
         hours=0.0, sport="basketball", certainty="probable", ents=(), comp=None):
    return ClusterInput(
        id=_id, source=source, title=title, subtitle=subtitle,
        published_at=BASE + timedelta(hours=hours), sport=sport,
        event_type=event, event_certainty=certainty,
        entity_ids=tuple(ents), primary_competition=comp,
    )


def _pair(a, b, extra=()):
    """Run intra_source_match with a DF window of the pair plus optional filler."""
    toks = {x.id: tokenize(f"{x.title} {x.subtitle}".strip()) for x in (a, b, *extra)}
    df = DocumentFrequency.over(toks.values())
    return intra_source_match(
        a, b, tokenize(a.title), tokenize(b.title), toks[a.id], toks[b.id], df, CFG,
    )


# ══════════════════════════════════════════════════════════════════════════════
# The frozen positive: dup_noskova_same_source collapses to ONE cluster
# ══════════════════════════════════════════════════════════════════════════════

class TestNoskovaCollapses:
    def test_the_pair_matches_under_the_intra_source_contract(self):
        a, b = _load_noskova()
        edge, rejection = _pair(a, b)
        assert rejection is None
        assert edge is not None
        assert edge.tier == TIER_INTRA_SOURCE, "audit: a republish edge is marked tier I"

    def test_cluster_articles_produces_one_cluster(self):
        result = cluster_articles(_load_noskova(), CFG)
        assert len(result.clusters) == 1
        assert len(result.clusters[0].member_ids) == 2

    def test_canonical_selection_is_the_documented_ladder(self):
        """Survivor = §9.1 ladder: fact completeness → certainty → recency → id.

        Both Noskova tellings carry equal facts and certainty, so the NEWER one
        survives — a republish supersedes its earlier telling. The alternate
        remains listed under the card (collapse machinery), never deleted.
        """
        members = _load_noskova()
        rep = select_representative(members)
        newest = max(members, key=lambda m: m.published_at)
        assert rep.id == newest.id

    def test_canonical_selection_is_deterministic_under_reordering(self):
        members = _load_noskova()
        assert select_representative(members).id == \
            select_representative(list(reversed(members))).id


# ══════════════════════════════════════════════════════════════════════════════
# Required negatives — live updates and different angles must NOT merge
# ══════════════════════════════════════════════════════════════════════════════

class TestLiveUpdatesDoNotMerge:
    def test_half_time_then_full_time_never_reaches_the_stage(self):
        """A live-blog pair: the מחצית snapshot is excluded from candidacy
        entirely (is_in_play), so no intra-source rule ever sees it."""
        half = _art("ht", "מחצית: מכבי תל אביב מובילה 40:52 על ריאל מדריד",
                    event="match_result", hours=0.0)
        full = _art("ft", "מכבי תל אביב ניצחה 80:95 את ריאל מדריד",
                    event="match_result", hours=1.5)
        result = cluster_articles([half, full], CFG)
        assert result.clusters == []
        assert "ht" in result.excluded_ids

    def test_rumour_then_confirmation_is_two_states(self):
        rumour = _art("r1", "דיווח: מדר בדרך למכבי תל אביב", event="rumor", hours=0.0)
        signed = _art("s1", "רשמי: מדר חתם במכבי תל אביב", event="signing", hours=2.0)
        edge, rejection = _pair(rumour, signed)
        assert edge is None
        assert rejection.reason == IntraRejection.EVENT_STATE_INCOMPATIBLE

    def test_news_state_is_excluded_outright(self):
        a = _art("n1", "ים מדר נפרד מהפועל תל אביב", event="news", hours=0.0)
        b = _art("n2", "כך ים מדר נפרד מהפועל תל אביב", event="news", hours=1.0)
        edge, rejection = _pair(a, b)
        assert edge is None
        assert rejection.reason == IntraRejection.NEWS_STATE


class TestDifferentAnglesAreNotSwallowed:
    """The REAL same-source traps from the frozen corpus — each shares enough
    vocabulary to fool a naive rule, and each must stay separate."""

    def test_two_matches_under_the_same_highlights_template(self):
        # The worst negative in the corpus: identical template, DIFFERENT GAMES.
        a = _art("hl1", "צפו בתקציר: ארגנטינה ניצחה 1:3 את שווייץ - ועלתה לחצי גמר המונדיאל",
                 source="sport5_sport", event="finals_result", sport="football", hours=0.0)
        b = _art("hl2", "צפו בתקציר: אנגליה בחצי גמר המונדיאל אחרי 1:2 בהארכה מול נורבגיה",
                 source="sport5_sport", event="finals_result", sport="football", hours=4.0)
        edge, rejection = _pair(a, b)
        assert edge is None
        assert rejection.reason == IntraRejection.BELOW_TITLE_SIMILARITY

    def test_event_report_vs_reaction_piece(self):
        # McGregor: the result report and a quote/reaction piece share the
        # subject but are different angles — the title bar keeps them apart.
        a = _art("mg1", "אחרי 5 שנים: הקאמבק של קונור מקגרגור הסתיים בסיוט - תוך דקה",
                 subtitle="אחרי היעדרות של חמש שנים מה-UFC, הלוחם האירי חזר לזירה מול מקס הולוואי",
                 source="israel_hayom_sport", event="injury", sport="unknown", hours=0.0)
        b = _art("mg2", '"קונור מקגרגור לא יצר קשר עין, משהו היה לא בסדר"',
                 subtitle="הקאמבק של הלוחם האירי ל-UFC הסתיים בנוקאאוט מהיר מול מקס הולוואי",
                 source="israel_hayom_sport", event="injury", sport="unknown", hours=1.4)
        edge, rejection = _pair(a, b)
        assert edge is None
        assert rejection.reason == IntraRejection.BELOW_TITLE_SIMILARITY

    def test_a_followup_outside_the_tight_window_is_rejected_on_time(self):
        a = _art("t1", "לינדה נוסקובה זכתה בטורניר ווימבלדון",
                 event="grand_slam_winner", sport="tennis", hours=0.0)
        b = _art("t2", "לינדה נוסקובה זכתה בטורניר ווימבלדון",
                 event="grand_slam_winner", sport="tennis", hours=9.0)
        edge, rejection = _pair(a, b)
        assert edge is None
        assert rejection.reason == IntraRejection.OUTSIDE_TIME_WINDOW

    def test_similarity_alone_is_never_sufficient(self):
        # Titles clear both bars but share NO discriminative token (template +
        # generic vocabulary only) → no edge. Filler articles make the shared
        # tokens common in the window.
        filler = [
            _art(f"f{i}", "רשמית: השחקן חתם חוזה חדש לעונה הבאה בקבוצה",
                 source=f"src{i}", hours=float(i)) for i in range(8)
        ]
        a = _art("s1", "רשמית: השחקן חתם חוזה חדש לעונה הבאה", hours=0.0)
        b = _art("s2", "רשמית: השחקן חתם חוזה חדש לעונה", hours=1.0)
        edge, rejection = _pair(a, b, extra=filler)
        assert edge is None
        assert rejection.reason == IntraRejection.NO_DISCRIMINATIVE_EVIDENCE


# ══════════════════════════════════════════════════════════════════════════════
# Cross-source behaviour is byte-identical
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossSourceGateUntouched:
    def test_cross_source_pairs_never_route_to_the_intra_stage(self):
        """Two sources, same story → a NORMAL cross-source edge (tier A/B/C),
        never tier I."""
        a = _art("x1", "זאק הנקינס שוחרר ממכבי תל אביב", source="ynet_sport",
                 event="release", ents=("team:maccabi_tlv_bb",), hours=0.0)
        b = _art("x2", "מכבי תל אביב שחררה את זאק הנקינס", source="walla_sport",
                 event="release", ents=("team:maccabi_tlv_bb",), hours=1.0)
        result = cluster_articles([a, b], CFG)
        assert len(result.clusters) == 1
        assert all(e.tier != TIER_INTRA_SOURCE for e in result.edges)

    def test_intra_source_match_refuses_cross_source_pairs(self):
        a = _art("x1", "לינדה נוסקובה זכתה בווימבלדון", source="ynet_sport",
                 event="grand_slam_winner", sport="tennis", hours=0.0)
        b = _art("x2", "לינדה נוסקובה זכתה בווימבלדון", source="walla_sport",
                 event="grand_slam_winner", sport="tennis", hours=1.0)
        edge, rejection = _pair(a, b)
        assert edge is None
        assert rejection.reason == IntraRejection.DIFFERENT_SOURCE
