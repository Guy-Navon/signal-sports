"""#142 — claim compatibility: a shared anchor is not a duplicate event.

The deterministic v1 rule: an OUTCOME REVERSAL asserted in exactly one TITLE of
a pair makes the pair a material update — never a duplicate edge — no matter
how strong the token or anchor evidence. Diarra is the frozen proof; the
conditional guard and the title-only restriction are corpus-audited (the
Hankins must-merge member carries an incidental subtitle negation about a
different player and must NOT be blocked).
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.clustering.claims import claims_compatible, title_claims_reversal
from app.clustering.config import DEFAULT_CONFIG as CFG
from app.clustering.contract import ClusterInput
from app.clustering.matcher import Rejection, match_pair
from app.clustering.service import cluster_articles
from app.clustering.tokens import DocumentFrequency, tokenize

FIXTURES = Path(__file__).parent / "fixtures"
BASE = datetime(2026, 7, 12, 4, 0, tzinfo=timezone.utc)


def _load_diarra() -> list[ClusterInput]:
    with (FIXTURES / "clustering_adversarial.json").open(encoding="utf-8") as fh:
        entry = next(
            m for m in json.load(fh)["material_update_same_thread"]
            if m["id"] == "material_update_diarra_hapoel"
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
        for a in entry["articles"]
    ]


def _art(_id, title, subtitle="", source="walla_sport", event="negotiation",
         hours=0.0, sport="football", ents=()):
    return ClusterInput(
        id=_id, source=source, title=title, subtitle=subtitle,
        published_at=BASE + timedelta(hours=hours), sport=sport,
        event_type=event, event_certainty="probable", entity_ids=tuple(ents),
    )


def _match(a, b):
    toks = {x.id: tokenize(f"{x.title} {x.subtitle}".strip()) for x in (a, b)}
    df = DocumentFrequency.over(toks.values())
    return match_pair(a, b, toks[a.id], toks[b.id], df, CFG)


# ══════════════════════════════════════════════════════════════════════════════
# Title reversal detection
# ══════════════════════════════════════════════════════════════════════════════

class TestTitleReversalDetection:
    def test_diarra_walla_title_is_a_reversal(self):
        assert title_claims_reversal(
            "הפור נפל? דיווח: טיימוקו דיארה לא יחתום בהפועל תל אביב"
        )

    def test_cancelled_deal_title_is_a_reversal(self):
        # The Halaili cancellation — the other genuine reversal in the corpus.
        assert title_claims_reversal("אכזבה עצומה: עסקת ענאן חלאילי לאינטר מבוטלת")

    def test_conditional_deadline_is_not_a_reversal(self):
        # "IF he does not sign by Tuesday" — deadline reporting inside an open
        # negotiation. The real israel_hayom headline that must not fire.
        assert not title_claims_reversal(
            '"אם לא יחתום במכבי תל אביב עד שלישי - הוא יפתח בשבת"'
        )

    def test_affirmative_titles_do_not_fire(self):
        for t in (
            "ים מדר חתם במכבי תל אביב",
            "לינדה נוסקובה זכתה בווימבלדון",
            "מכבי תל אביב נפרדה מהנקינס",
        ):
            assert not title_claims_reversal(t), t


# ══════════════════════════════════════════════════════════════════════════════
# Pair-level behaviour
# ══════════════════════════════════════════════════════════════════════════════

class TestDiarraDoesNotCollapse:
    def test_the_frozen_pair_is_claim_incompatible(self):
        a, b = _load_diarra()
        compatible, detail = claims_compatible(a, b)
        assert not compatible
        assert "rss_bcc9496e12e5b7d3c0f0" in detail   # the reversing side is named

    def test_match_pair_rejects_with_the_named_reason(self):
        a, b = _load_diarra()
        edge, rejection = _match(a, b)
        assert edge is None
        # Claim gate fires BEFORE similarity — the rejection is about the claim,
        # not about thresholds that anchor evidence (#141) could later bypass.
        assert rejection.reason == Rejection.CLAIM_REVERSAL_MISMATCH

    def test_cluster_articles_keeps_both_visible(self):
        result = cluster_articles(_load_diarra(), CFG)
        assert result.clusters == []


class TestSymmetricAndIncidentalClaims:
    def test_two_sources_both_reporting_the_collapse_are_duplicates(self):
        # BOTH titles reverse → same claim → still edge-eligible (subject to
        # every other gate). Two reports of "the deal is off" are one story.
        a = _art("c1", "עסקת דיארה בהפועל תל אביב בוטלה",
                 subtitle="הקשר ממאלי בדרך לקאסימפשה", source="walla_sport")
        b = _art("c2", "רשמי: טיימוקו דיארה לא יחתום בהפועל תל אביב",
                 subtitle="הקשר ממאלי סיכם בקאסימפשה", source="ynet_sport", hours=1.0)
        compatible, _ = claims_compatible(a, b)
        assert compatible

    def test_incidental_subtitle_negation_does_not_block_a_real_duplicate(self):
        # The Hankins trap: the israel_hayom member of the frozen must-merge
        # group says "לא יגיע" in its SUBTITLE about a DIFFERENT player. Title-only
        # scope keeps the genuine duplicate mergeable.
        a = _art("h1", "בדרך לרכש כפול: מכבי תל אביב נפרדה מאחד משחקניה",
                 subtitle="הסנטר האמריקאי לא יגיע לעונה נוספת בישראל",
                 source="israel_hayom_sport", event="release", sport="basketball")
        b = _art("h2", "לאחר עונה אחת: מכבי ת\"א נפרדה מהנקינס",
                 source="sport5_sport", event="release", sport="basketball", hours=1.0)
        compatible, _ = claims_compatible(a, b)
        assert compatible

    def test_intra_source_correction_stays_visible(self):
        # A same-source pair where the second title reverses the first: a
        # CORRECTION, not a republish — the intra-source stage must refuse it
        # even at near-identical similarity.
        from app.clustering.intra_source import IntraRejection, intra_source_match
        a = _art("r1", "טיימוקו דיארה יחתום בהפועל תל אביב", event="negotiation")
        b = _art("r2", "טיימוקו דיארה לא יחתום בהפועל תל אביב", event="negotiation",
                 hours=1.0)
        toks = {x.id: tokenize(x.title) for x in (a, b)}
        df = DocumentFrequency.over(toks.values())
        edge, rejection = intra_source_match(
            a, b, toks["r1"], toks["r2"], toks["r1"], toks["r2"], df, CFG,
        )
        assert edge is None
        assert rejection.reason == IntraRejection.CLAIM_REVERSAL_MISMATCH
