"""#141 wiring — validated anchors as pair evidence, end to end.

The laws, enforced structurally:
  * a candidate span is not an anchor → only PERSISTED, validator-ACCEPTED anchors
    reach the matcher (enrichment filters roles and abstentions);
  * a shared anchor is not a duplicate event → tier-N fires only after EVERY hard
    gate (cross-source, same clusterable non-news state, claim compatibility #142,
    in-play, window, sport) has already passed;
  * `news` + shared anchor is not sufficient (#142) → the catch-all state keeps
    its lexical requirement;
  * validation runs ONCE at ingestion; pair evaluation never invokes a model.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.clustering.anchor_enrichment import (
    StoredAnchor,
    accepted_anchor_keys,
    shared_stored_anchors,
)
from app.clustering.config import DEFAULT_CONFIG as CFG
from app.clustering.contract import ClusterInput
from app.clustering.matcher import TIER_ANCHOR, Rejection, match_pair
from app.clustering.tokens import DocumentFrequency, tokenize

wordfreq = pytest.importorskip("wordfreq")   # the enrichment stage needs V1's resource

BASE = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)


def _anchor(name, role="subject"):
    return StoredAnchor(anchor=name, role=role, source="title",
                        validator_id="lexical_frequency", reason_code="rare_in_language")


def _art(_id, title, subtitle="", source="walla_sport", event="release",
         hours=0.0, sport="basketball", anchors=()):
    return ClusterInput(
        id=_id, source=source, title=title, subtitle=subtitle,
        published_at=BASE + timedelta(hours=hours), sport=sport,
        event_type=event, event_certainty="probable",
        story_anchors=tuple(a.to_json() for a in anchors),
    )


def _match(a, b, extra=()):
    toks = {x.id: tokenize(f"{x.title} {x.subtitle}".strip()) for x in (a, b, *extra)}
    df = DocumentFrequency.over(toks.values())
    return match_pair(a, b, toks[a.id], toks[b.id], df, CFG)


# ══════════════════════════════════════════════════════════════════════════════
# Tier-N: the anchor rescue
# ══════════════════════════════════════════════════════════════════════════════

class TestAnchorRescue:
    def test_shared_validated_anchor_rescues_a_low_overlap_hebrew_pair(self):
        # The Madar-farewell failure mode: same story, formulaic-Hebrew token sets
        # too far apart for jaccard — but both carry the persisted validated anchor.
        a = _art("m1", "אף מילה על הבעלים והמאמן: כך ים מדר נפרד מהפועל תל אביב",
                 source="walla_sport", anchors=[_anchor("מדר")])
        b = _art("m2", 'מדר: "עוזב בראש מורם. השנה לא הייתה קלה"',
                 source="sport5_sport", hours=2.0, anchors=[_anchor("מדר")])
        edge, rejection = _match(a, b)
        assert edge is not None, rejection
        assert edge.tier == TIER_ANCHOR
        assert any("מדר" in k for k in edge.rare_tokens)

    def test_without_anchors_the_same_pair_still_rejects(self):
        a = _art("m1", "אף מילה על הבעלים והמאמן: כך ים מדר נפרד מהפועל תל אביב")
        b = _art("m2", 'מדר: "עוזב בראש מורם. השנה לא הייתה קלה"',
                 source="sport5_sport", hours=2.0)
        edge, rejection = _match(a, b)
        assert edge is None
        assert rejection.reason in (Rejection.BELOW_JACCARD,
                                    Rejection.NO_DISCRIMINATIVE_EVIDENCE)

    def test_a_lexical_pass_keeps_its_lexical_tier(self):
        # Anchors rescue; they never relabel a pair that passed on its own.
        a = _art("h1", "זאק הנקינס שוחרר ממכבי תל אביב", source="ynet_sport",
                 anchors=[_anchor("הנקינס")])
        b = _art("h2", "מכבי תל אביב שחררה את זאק הנקינס", source="walla_sport",
                 hours=1.0, anchors=[_anchor("הנקינס")])
        edge, _ = _match(a, b)
        assert edge is not None
        assert edge.tier != TIER_ANCHOR

    def test_storonski_variants_meet_on_the_translit_key(self):
        # #137 integration: vav metathesis — the raw keys never match; the
        # namespaced skeleton keys do.
        a = _art("s1", "הפועל תל אביב צפויה לצרף את סטורנסקי", source="walla_sport",
                 event="negotiation", anchors=[_anchor("סטורנסקי")])
        b = _art("s2", "סטרונסקי סיכם בהפועל תל אביב: זה השכר שירוויח",
                 source="sport5_sport", event="negotiation", hours=1.0,
                 anchors=[_anchor("סטרונסקי")])
        shared = shared_stored_anchors(list(a.story_anchors), list(b.story_anchors))
        assert any(k.startswith("translit:") for k in shared)
        edge, rejection = _match(a, b)
        assert edge is not None, rejection
        assert edge.tier == TIER_ANCHOR

    def test_translit_keys_are_namespaced_and_cannot_hit_raw_names(self):
        keys = accepted_anchor_keys([_anchor("דיארה").to_json()])
        skeleton_keys = {k for k in keys if k.startswith("translit:")}
        assert skeleton_keys, "the skeleton key must be present"
        # The raw skeleton string itself is NOT a key — only the namespaced form.
        assert "דארה" not in keys

    def test_variant_spelling_is_corroborated_by_the_population_skeleton(self):
        """The sport5 Storonski failure mode (#137 at the GENERATION stage): the
        variant spelling has no bigram partner in its own headline, and the
        population lexicon only knows the OTHER spelling. The skeleton makes the
        lone mention recognisable — and it still faces full validation."""
        from app.clustering.anchor_enrichment import enrich_article_anchors
        from app.clustering.anchor_validators import LexicalFrequencyValidator

        ynet = _art("y", "רכז ברצלונה תומס סטורנסקי סיכם בקבוצה", source="ynet_sport",
                    event="negotiation")
        stored, _ = enrich_article_anchors(
            'סטרונסקי סיכם בהפועל ת"א: זה השכר שירוויח', "",
            LexicalFrequencyValidator(), article_id="s5", population=[ynet],
        )
        assert "סטרונסקי" in {a.anchor for a in stored}


# ══════════════════════════════════════════════════════════════════════════════
# The gates an anchor can never bypass
# ══════════════════════════════════════════════════════════════════════════════

class TestAnchorIsNeverSufficient:
    def test_news_state_pairs_get_no_anchor_rescue(self):
        # #142: shared identity + the catch-all state is not enough.
        a = _art("n1", "כתבה כללית על ים מדר והעונה שהייתה", event="news",
                 anchors=[_anchor("מדר")])
        b = _art("n2", "מדר בכותרות: סיכום שבוע בכדורסל הישראלי", event="news",
                 source="ynet_sport", hours=1.0, anchors=[_anchor("מדר")])
        edge, rejection = _match(a, b)
        assert edge is None
        assert rejection.reason in (Rejection.BELOW_JACCARD,
                                    Rejection.NO_DISCRIMINATIVE_EVIDENCE)

    def test_claim_reversal_fires_before_any_anchor_evidence(self):
        # The Diarra law: the material update rejects at stage 2.5 — anchor
        # evidence is never even consulted.
        a = _art("d1", "עמדה במצוקה: אקס הפועל תל אביב מתרחק מהקבוצה",
                 source="israel_hayom_sport", event="negotiation", sport="football",
                 anchors=[_anchor("דיארה")])
        b = _art("d2", "הפור נפל? דיווח: טיימוקו דיארה לא יחתום בהפועל תל אביב",
                 source="walla_sport", event="negotiation", sport="football",
                 hours=12.0, anchors=[_anchor("דיארה")])
        edge, rejection = _match(a, b)
        assert edge is None
        assert rejection.reason == Rejection.CLAIM_REVERSAL_MISMATCH

    def test_cross_state_pairs_reject_before_anchors(self):
        a = _art("x1", "מדר במגעים עם מכבי תל אביב", event="negotiation",
                 anchors=[_anchor("מדר")])
        b = _art("x2", "ים מדר חתם במכבי תל אביב", event="signing",
                 source="ynet_sport", hours=1.0, anchors=[_anchor("מדר")])
        edge, rejection = _match(a, b)
        assert edge is None
        assert rejection.reason == Rejection.EVENT_STATE_INCOMPATIBLE

    def test_same_source_pairs_never_reach_the_anchor_stage(self):
        a = _art("y1", "כך מדר נפרד מהפועל", anchors=[_anchor("מדר")])
        b = _art("y2", "מדר נפרד מהפועל תל אביב", hours=1.0, anchors=[_anchor("מדר")])
        edge, rejection = _match(a, b)
        assert edge is None
        assert rejection.reason == Rejection.SAME_SOURCE


class TestResultStatesAreMatchIdentified:
    """The #124 manual-review false-merge classes, frozen as negatives. In result
    states the story is the MATCH — a shared player, coach or team word must never
    be merge evidence (Bellingham recurs in every England story; the youth-final
    team word bridged PREVIEW + RESULT + REACTION)."""

    def test_shared_player_does_not_merge_two_different_colour_stories(self):
        # The real trap: Tuchel-criticism story vs the almost-missed-the-match
        # anecdote, both match_result, both carrying the shared star.
        a = _art("c1", 'אנגליה סוערת: טוכל ביקר את שחקניו, בלינגהאם הגיב',
                 source="walla_sport", event="match_result", sport="football",
                 anchors=[_anchor("בלינגהאם")])
        b = _art("c2", "כוכב נבחרת אנגליה כמעט פספס את חצי הגמר - וניצל בזכות אימו",
                 subtitle="ג'וד בלינגהאם כמעט נשאר בבית המלון",
                 source="israel_hayom_sport", event="match_result", sport="football",
                 hours=1.6, anchors=[_anchor("בלינגהאם", role="subject")])
        edge, rejection = _match(a, b)
        assert edge is None, "a person anchor must not merge result-state stories"

    def test_team_word_does_not_chain_preview_result_reaction(self):
        prev = _art("p1", 'נבחרת העתודה תבוא "להסתכל בלבן של העיניים" לפייבוריטית',
                    source="walla_sport", event="finals_result", sport="basketball",
                    anchors=[_anchor("העתודה")])
        res = _art("p2", "נבחרת ישראל הפסידה לצרפת בגמר אליפות אירופה לעתודה",
                   source="israel_hayom_sport", event="finals_result",
                   sport="basketball", hours=3.0, anchors=[_anchor("העתודה")])
        edge, rejection = _match(prev, res)
        assert edge is None

    def test_subtitle_only_incidental_mention_is_not_subject_evidence(self):
        # The roundup trap: two unrelated negotiation roundups sharing an
        # incidental club mention in both SUBTITLES (jaccard 0.016 in the wild).
        a = _art("r1", "אחרי הפיצוץ עם אינטר: מועדוני הענק שבעקבות חלאילי",
                 subtitle="גם אסטון וילה בתמונה", source="israel_hayom_sport",
                 event="negotiation", sport="football",
                 anchors=[StoredAnchor("אסטון", "unknown", "subtitle",
                                       "lexical_frequency", "rare_in_language")])
        b = _art("r2", "טילמאנס בדרך למנצ'סטר יונייטד, ברצלונה מכחישה",
                 subtitle="אסטון וילה מחכה להחלטה", source="walla_sport",
                 event="negotiation", sport="football", hours=2.0,
                 anchors=[StoredAnchor("אסטון", "unknown", "subtitle",
                                       "lexical_frequency", "rare_in_language")])
        edge, rejection = _match(a, b)
        assert edge is None, "subtitle-only-on-both-sides is incidental, not subject"

    def test_title_on_one_side_still_carries_the_hardest_hankins_member(self):
        # israel_hayom names the player only in its SUBTITLE — but its peer
        # headlines him. Title-ness on ONE side suffices.
        a = _art("h1", "בדרך לרכש כפול: מכבי תל אביב נפרדה מאחד משחקניה",
                 subtitle="זאק הנקינס מסיים את דרכו במועדון",
                 source="israel_hayom_sport", event="release",
                 anchors=[StoredAnchor("הנקינס", "subject", "subtitle",
                                       "lexical_frequency", "rare_in_language")])
        b = _art("h2", "לאחר עונה אחת: מכבי ת\"א נפרדה מהנקינס",
                 source="sport5_sport", event="release", hours=1.0,
                 anchors=[_anchor("הנקינס")])
        edge, rejection = _match(a, b)
        assert edge is not None, rejection
        assert edge.tier == TIER_ANCHOR


# ══════════════════════════════════════════════════════════════════════════════
# Ingestion enrichment stage — validation runs ONCE, persisted, idempotent
# ══════════════════════════════════════════════════════════════════════════════

_IDS: list[str] = []


def _add(session, _id, *, source, title, subtitle="", hours=0, sport="basketball",
         event_type="release"):
    from app.db.orm_models import ArticleRow
    _IDS.append(_id)
    row = ArticleRow(
        id=_id, source=source, source_display_name=source,
        url=f"https://example.test/{_id}", title=title, subtitle=subtitle,
        language="he", published_at=(BASE + timedelta(hours=hours)).isoformat(),
        sport=sport, entities=[], event_type=event_type,
        event_certainty="probable", importance="medium", tags=[], entity_ids=[],
    )
    session.add(row)
    return row


@pytest.fixture
def session(_application):
    from app.db.database import SessionLocal, init_db
    from app.db.orm_models import ArticleRow
    init_db()
    _IDS.clear()
    with SessionLocal() as s:
        yield s
        s.rollback()
        if _IDS:
            s.query(ArticleRow).filter(ArticleRow.id.in_(_IDS)).delete(
                synchronize_session=False
            )
        s.commit()


class TestEnrichmentStage:
    def test_enrichment_persists_validated_anchors(self, session):
        from app.clustering.ingest_stage import run_anchor_enrichment_stage
        from app.db.orm_models import ArticleRow

        _add(session, "e1", source="walla_sport",
             title="כך ים מדר נפרד מהפועל תל אביב")
        _add(session, "e2", source="sport5_sport", hours=1,
             title="מדר נפרד מהפועל בדרך למכבי")
        session.commit()

        res = run_anchor_enrichment_stage(session, ["e1", "e2"])
        assert res.ran and not res.failed
        assert res.enriched == 2

        row = session.get(ArticleRow, "e1")
        assert row.anchor_validator_version
        anchors = {a["anchor"] for a in (row.story_anchors or [])}
        assert "מדר" in anchors

    def test_enrichment_is_idempotent_per_validator_version(self, session):
        from app.clustering.ingest_stage import run_anchor_enrichment_stage

        _add(session, "e1", source="walla_sport",
             title="כך ים מדר נפרד מהפועל תל אביב")
        session.commit()

        run_anchor_enrichment_stage(session, ["e1"])
        res = run_anchor_enrichment_stage(session, ["e1"])
        assert res.skipped_current == 1
        assert res.enriched == 0

    def test_enrichment_runs_even_with_clustering_disabled(self, session):
        # Enrichment is FACT persistence, not clustering behaviour: anchors must
        # already be in place whenever #126 flips the flag.
        from app.clustering.ingest_stage import run_anchor_enrichment_stage
        from app.db.orm_models import ArticleRow

        _add(session, "e1", source="walla_sport",
             title="כך ים מדר נפרד מהפועל תל אביב")
        session.commit()

        with patch.dict(os.environ, {"CLUSTERING_ENABLED": "false"}):
            res = run_anchor_enrichment_stage(session, ["e1"])
        assert res.ran and res.enriched == 1
        assert session.get(ArticleRow, "e1").story_anchors is not None

    def test_ordinary_hebrew_words_are_not_persisted_as_anchors(self, session):
        from app.clustering.ingest_stage import run_anchor_enrichment_stage
        from app.db.orm_models import ArticleRow

        # "נשאר אדום" — the generator's favourite trap. The validator rejects it.
        _add(session, "e1", source="walla_sport",
             title="נשאר אדום: אלייז'ה בראיינט האריך חוזה בהפועל תל אביב",
             event_type="signing")
        session.commit()

        run_anchor_enrichment_stage(session, ["e1"])
        row = session.get(ArticleRow, "e1")
        anchors = {a["anchor"] for a in (row.story_anchors or [])}
        assert "אדום" not in anchors
        assert "נשאר אדום" not in anchors
        assert "בראיינט" in anchors
