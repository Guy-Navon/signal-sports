"""
Deterministic clustering matcher (#100) — driven by the FROZEN fixtures (#99).

No corpus DB access anywhere in this module. The fixtures are the contract.

The whole fixture set is fed to the matcher as ONE candidate window, because that is
what production looks like: a lookback window contains many unrelated stories, and
document frequency — hence what counts as "discriminative" — is relative to it.
Feeding each case in isolation would make every token look rare and the precision
gate would be vacuous.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.clustering import (
    DEFAULT_CONFIG,
    ClusterInput,
    ClusteringConfig,
    cluster_articles,
    select_anchor,
    select_representative,
)
from app.clustering.event_states import is_in_play, states_compatible
from app.clustering.matcher import Rejection, TIER_A, TIER_C, select_tier, sports_hard_reject
from app.clustering.tokens import DocumentFrequency, jaccard, normalize, tokenize

FIXTURES = Path(__file__).parent / "fixtures" / "clustering_cases.json"


def _load() -> dict:
    with FIXTURES.open(encoding="utf-8") as fh:
        return json.load(fh)


def _to_input(raw: dict) -> ClusterInput:
    return ClusterInput(
        id=raw["id"],
        source=raw["source"],
        title=raw["title"],
        published_at=datetime.fromisoformat(raw["published_at"].replace("Z", "+00:00")),
        sport=raw["sport"],
        event_type=raw["event_type"],
        event_certainty=raw.get("event_certainty"),
        entity_ids=tuple(raw.get("entity_ids") or ()),
        primary_competition=raw.get("primary_competition"),
        subtitle=raw.get("subtitle", ""),
    )


@pytest.fixture(scope="module")
def cases() -> dict:
    return _load()


# ── Realistic DF denominator (test scaffolding, NOT contract data) ───────────
#
# Document frequency is MEANINGLESS in a 41-article window, and clustering's whole
# precision mechanism is built on it. Two failures prove it:
#
#   - "רקנאטי"/"פדרמן" appear in df=4 documents (the 4 sources covering that story).
#     With a tiny window that reads as "common" — so the MORE sources cover a story,
#     the LESS likely it would cluster. Exactly backwards.
#   - "העונה"/"פתחה"/"בניצחון" appear in df=2 and read as "rare" — so two unrelated
#     "X opened the season with a win" headlines would merge.
#
# A real lookback window (24-48h across four Hebrew sports sources) holds HUNDREDS of
# articles, which is what the recorded calibration (df_ratio_max=0.01) assumes: at
# n≈400, "רקנאטי" (df=4 → ratio 0.0099) is discriminative and "העונה" (df≈50) is not.
#
# These filler articles exist ONLY to give DF that realistic denominator. They are
# generic sports furniture, carry NO expectations, and are deliberately all from one
# source so they can never cluster with each other (cross-source hard gate). They are
# NOT part of the frozen contract — that is why they live here and not in the fixture
# file.
_FILLER_SOURCE = "filler_source"

# Common Hebrew sports vocabulary. Every one of these MUST end up non-discriminative;
# none of them may be the thing that carries a real match.
_FILLER_PHRASES = [
    "הקבוצה פתחה את העונה בניצחון גדול",
    "השחקן חתם על חוזה חדש עם הקבוצה",
    "המאמן האריך חוזה לקראת העונה הבאה",
    "הקבוצה מחתימה את הגארד האמריקאי לקראת העונה",
    "ניצחון חשוב במשחק הליגה אתמול",
    "הקבוצה מתל אביב סיימה את המשחק בתיקו",
    "שחקן הליגה עבר בדיקות לקראת החתימה",
    "מכבי והפועל נפגשות במשחק הליגה",
    "הקבוצה הודיעה על צירוף שחקן חדש",
    "משחק הליגה הסתיים בניצחון הקבוצה המארחת",
]


def _background_window() -> list[ClusterInput]:
    """Filler sized so the DF window satisfies ClusteringConfig.min_window_for_valid_df().

    With df_ratio_max=0.01 and max_cluster_size=6 that means >= 700 eligible docs, so a
    fully-covered 6-source story still clusters (its own tokens have df=6). Sizing this
    at ~400 put the 4-source Recanati cluster exactly on the knife's edge (threshold
    3.96 vs its df of 4) and silently dropped it — see the coverage-paradox note in
    ClusteringConfig.
    """
    base = datetime.fromisoformat("2026-06-01T09:00:00+00:00")
    out: list[ClusterInput] = []
    for i in range(800):
        phrase = _FILLER_PHRASES[i % len(_FILLER_PHRASES)]
        out.append(ClusterInput(
            id=f"bg_{i:03d}",
            source=_FILLER_SOURCE,          # same source → filler never clusters
            title=f"{phrase} מספר {i}",
            published_at=base,
            sport="basketball",
            event_type="news",
            event_certainty="probable",
            entity_ids=(),
            primary_competition=None,
        ))
    return out


@pytest.fixture(scope="module")
def real_articles(cases) -> list[ClusterInput]:
    """Only the frozen contract articles (no scaffolding)."""
    seen: dict[str, ClusterInput] = {}
    for section in ("true_positive_groups", "must_not_cluster", "excluded_from_candidacy"):
        for case in cases[section]:
            for art in case["articles"]:
                seen.setdefault(art["id"], _to_input(art))
    return list(seen.values())


@pytest.fixture(scope="module")
def window(real_articles) -> list[ClusterInput]:
    """Production-scale candidate window: the frozen fixtures + a realistic DF denominator."""
    return real_articles + _background_window()


@pytest.fixture(scope="module")
def result(window):
    return cluster_articles(window, DEFAULT_CONFIG, collect_rejections=True)


def _cluster_of(result, article_id: str):
    for c in result.clusters:
        if article_id in c.member_ids:
            return c
    return None


def _together(result, a: str, b: str) -> bool:
    ca, cb = _cluster_of(result, a), _cluster_of(result, b)
    return ca is not None and cb is not None and ca.anchor_id == cb.anchor_id


# ── Token normalization ───────────────────────────────────────────────────────

class TestTokenNormalization:
    def test_gershayim_and_ascii_quotes_unify(self):
        assert normalize('מכבי ת"א') == normalize("מכבי ת״א")

    def test_geresh_variants_unify(self):
        assert normalize("ז'לגיריס") == normalize("ז׳לגיריס")

    def test_template_words_are_stripped(self):
        # "ממשיכה להתחזק" is headline furniture — it must never be shared evidence.
        toks = tokenize("ממשיכה להתחזק: דומפריס חתם בריאל מדריד")
        assert "ממשיכה" not in toks and "להתחזק" not in toks
        assert "דומפריס" in toks

    def test_reporting_verbs_are_stripped(self):
        toks = tokenize("רשמי: דיווח בלעדי על החתימה")
        assert not ({"רשמי", "דיווח", "בלעדי"} & toks)

    def test_stopwords_stripped(self):
        assert "של" not in tokenize("הגארד של הקבוצה")

    def test_jaccard_symmetric_and_bounded(self):
        a, b = tokenize("גרג לי חתם בהפועל חולון"), tokenize("גרג לי חתם רשמית בהפועל חולון")
        assert jaccard(a, b) == jaccard(b, a)
        assert 0.0 < jaccard(a, b) <= 1.0

    def test_empty_sets_score_zero(self):
        assert jaccard(set(), {"a"}) == 0.0


# ── Discriminative-token evidence (the precision backbone) ────────────────────

class TestDiscriminativeEvidence:
    def test_absolute_floor_marks_rare_token(self):
        df = DocumentFrequency.over([{"רקנאטי"}, {"אחר"}, {"אחר"}, {"אחר"}])
        assert df.is_discriminative("רקנאטי", DEFAULT_CONFIG)

    def test_common_token_is_not_discriminative_in_a_large_window(self):
        # df=10 in a 100-doc window: fails the abs floor (3) AND the ratio (0.10 > 0.01).
        docs = [{"חתם"} for _ in range(10)] + [{"x"} for _ in range(90)]
        df = DocumentFrequency.over(docs)
        assert df.df("חתם") == 10
        assert not df.is_discriminative("חתם", DEFAULT_CONFIG)

    def test_df_ratio_rescues_a_token_in_a_very_large_window(self):
        # df=5 exceeds the abs floor, but ratio 5/1000 = 0.005 <= 0.01 → discriminative.
        docs = [{"נדיר"} for _ in range(5)] + [{"x"} for _ in range(995)]
        df = DocumentFrequency.over(docs)
        assert df.df("נדיר") > DEFAULT_CONFIG.df_abs_floor
        assert df.df_ratio("נדיר") <= DEFAULT_CONFIG.df_ratio_max
        assert df.is_discriminative("נדיר", DEFAULT_CONFIG)

    def test_df_counts_each_document_once(self):
        df = DocumentFrequency.over([{"a"}, {"a"}, {"b"}])
        assert df.df("a") == 2 and df.total_documents == 3

    def test_thresholds_are_tunable_not_hardcoded(self):
        strict = ClusteringConfig(df_abs_floor=0, df_ratio_max=0.0)
        df = DocumentFrequency.over([{"t"}, {"x"}, {"y"}])
        assert not df.is_discriminative("t", strict)


# ── Event state / windows / in-play ──────────────────────────────────────────

class TestEventStates:
    def test_strict_same_state_only(self):
        assert states_compatible("signing", "signing")
        assert not states_compatible("negotiation", "signing")
        assert not states_compatible("candidate", "negotiation")
        assert not states_compatible("rumor", "signing")

    def test_perspective_pieces_never_cluster(self):
        for state in ("interview", "analysis", "opinion", "preview", "schedule"):
            assert not states_compatible(state, state)

    def test_unknown_state_abstains(self):
        assert not states_compatible("some_new_event", "some_new_event")

    def test_in_play_markers_detected(self):
        assert is_in_play("שוויץ - קולומביה 0:0 (מחצית)")
        assert is_in_play("חי מהמונדיאל: שווייץ - קולומביה 0:0")
        assert is_in_play("חי מרבע הגמר, מחצית: ספרד - בלגיה 1:1")

    def test_in_play_does_not_false_positive_on_normal_titles(self):
        assert not is_in_play("גרג לי חתם בהפועל חולון")
        assert not is_in_play("דרמה במכבי תל אביב: משפחת רקנאטי רוכשת את מניות משפחת פדרמן")

    def test_time_window_boundaries(self, window):
        cfg = DEFAULT_CONFIG
        assert cfg.window_for("signing") == 24.0
        assert cfg.window_for("match_result") == 12.0
        assert cfg.window_for("injury") == 48.0


# ── Sport rules ──────────────────────────────────────────────────────────────

class TestSportRules:
    def _mk(self, _id, sport, event="signing"):
        return ClusterInput(id=_id, source="s" + _id, title="t", sport=sport,
                            event_type=event,
                            published_at=datetime.fromisoformat("2026-07-07T10:00:00+00:00"))

    def test_two_proven_different_sports_hard_reject(self):
        assert sports_hard_reject(self._mk("a", "basketball"), self._mk("b", "football"))

    def test_same_proven_sport_is_fine(self):
        assert not sports_hard_reject(self._mk("a", "basketball"), self._mk("b", "basketball"))

    def test_unknown_sport_is_not_a_hard_reject_but_escalates_to_tier_c(self):
        a, b = self._mk("a", "unknown"), self._mk("b", "basketball")
        assert not sports_hard_reject(a, b)
        assert select_tier(a, b) == TIER_C   # NOT a wildcard — it makes things STRICTER

    def test_news_always_tier_c(self):
        a = self._mk("a", "basketball", "news")
        b = self._mk("b", "basketball", "news")
        assert select_tier(a, b) == TIER_C

    def test_shared_entity_gives_tier_a(self):
        a = ClusterInput(id="a", source="s1", title="t", sport="basketball",
                         event_type="signing", entity_ids=("team:hapoel_holon",),
                         published_at=datetime.fromisoformat("2026-07-07T10:00:00+00:00"))
        b = ClusterInput(id="b", source="s2", title="t", sport="basketball",
                         event_type="signing", entity_ids=("team:hapoel_holon",),
                         published_at=datetime.fromisoformat("2026-07-07T11:00:00+00:00"))
        assert select_tier(a, b) == TIER_A


# ── Representative / anchor ladder ───────────────────────────────────────────

class TestRepresentativeLadder:
    def _mk(self, _id, *, ents=(), comp=None, event="news", cert=None, hour=10):
        return ClusterInput(
            id=_id, source="src" + _id, title="t", sport="basketball",
            event_type=event, event_certainty=cert, entity_ids=ents,
            primary_competition=comp,
            published_at=datetime.fromisoformat(f"2026-07-07T{hour:02d}:00:00+00:00"),
        )

    def test_fact_completeness_wins_first(self):
        rich = self._mk("a", ents=("team:x",), comp="comp:ibl", event="signing")
        poor = self._mk("b", hour=23)   # newer, but factually empty
        assert select_representative([poor, rich]).id == "a"

    def test_event_certainty_breaks_completeness_tie(self):
        confirmed = self._mk("a", ents=("team:x",), cert="confirmed")
        probable = self._mk("b", ents=("team:x",), cert="probable", hour=23)
        assert select_representative([probable, confirmed]).id == "a"

    def test_recency_breaks_certainty_tie(self):
        older = self._mk("a", ents=("team:x",), cert="confirmed", hour=9)
        newer = self._mk("b", ents=("team:x",), cert="confirmed", hour=20)
        assert select_representative([older, newer]).id == "b"

    def test_stable_id_is_the_final_tiebreak(self):
        a = self._mk("aaa", ents=("team:x",), cert="confirmed")
        b = self._mk("bbb", ents=("team:x",), cert="confirmed")
        assert select_representative([b, a]).id == "aaa"   # lowest id wins

    def test_anchor_is_earliest_not_representative(self):
        early_poor = self._mk("a", hour=8)
        late_rich = self._mk("b", ents=("team:x",), comp="comp:ibl", event="signing", hour=20)
        members = [early_poor, late_rich]
        assert select_anchor(members).id == "a"          # earliest → stable id basis
        assert select_representative(members).id == "b"  # richest → what we display


# ══ THE CONTRACT: every frozen fixture, end to end ═══════════════════════════

class TestFrozenTruePositives:
    """Every audited true-positive group must cluster."""

    @pytest.mark.parametrize("case_id", [
        "tp_greg_lee_signing",
        "tp_recanati_federman_ownership",
        "tp_odiasi_extension",
        "tp_blakeney_extension",
        "tp_bryce_washington_signing",
        "tp_cacok_signing_transliteration",
        "tp_dompris_real_madrid",
        "tp_walker_leaving_maccabi",
        "tp_halaili_negotiation",
        "tp_halaili_signing_medical",
    ])
    def test_group_clusters_together(self, cases, result, case_id):
        case = next(c for c in cases["true_positive_groups"] if c["id"] == case_id)
        ids = [a["id"] for a in case["articles"]]
        clusters = {_cluster_of(result, i).anchor_id if _cluster_of(result, i) else None
                    for i in ids}
        assert None not in clusters, f"{case_id}: some members did not cluster ({ids})"
        assert len(clusters) == 1, f"{case_id}: members split across clusters"

    def test_greg_lee_is_a_three_source_cluster(self, result):
        c = _cluster_of(result, "f_gl_1")
        assert c is not None and c.size == 3

    def test_recanati_is_a_four_source_cluster_despite_unknown_sport_member(
        self, result, window
    ):
        c = _cluster_of(result, "f_rf_1")
        assert c is not None and c.size == 4
        # The flagship: a member with sport=unknown AND entity_ids=[] still joined,
        # carried by Tier C discriminative tokens (רקנאטי / פדרמן / מניות).
        walla = next(a for a in window if a.id == "f_rf_1")
        assert walla.sport == "unknown" and walla.entity_ids == ()
        assert c.event_state == "news"

    def test_cacok_clusters_despite_transliteration_variance(self, result):
        # קייקוק vs קאקוק — the surname token does NOT match; entity corroboration
        # (Tier A) plus the remaining shared tokens carry it.
        assert _together(result, "f_ck_1", "f_ck_2")

    def test_every_cluster_is_cross_source(self, result, window):
        by_id = {a.id: a for a in window}
        for c in result.clusters:
            sources = [by_id[m].source for m in c.member_ids]
            assert len(set(sources)) == len(sources), f"{c.anchor_id}: same-source members"

    def test_every_cluster_is_single_event_state(self, result, window):
        by_id = {a.id: a for a in window}
        for c in result.clusters:
            states = {by_id[m].event_type for m in c.member_ids}
            assert len(states) == 1, f"{c.anchor_id}: mixed states {states}"


class TestFrozenFalsePositives:
    """The whole point. Every one of these must NOT cluster."""

    def test_formulaic_template_does_not_cluster(self, result):
        # "ממשיכה להתחזק: X חתם ב-Y" — two unrelated signings, J=0.33, 79.5h apart.
        # Naive jaccard WOULD merge these.
        assert not _together(result, "f_dp_2", "f_ash_1")

    def test_youth_qf_and_sf_do_not_cluster(self, result):
        # Same team, same competition, J=0.60 — but a different event, 48.6h apart.
        assert not _together(result, "f_yt_1", "f_yt_2")

    def test_halaili_candidate_stays_out_of_the_negotiation_cluster(self, result):
        assert not _together(result, "f_hl_c1", "f_hl_n2")

    def test_halaili_saga_is_three_separate_outcomes(self, result):
        # negotiation cluster, signing cluster, and the candidate article alone.
        assert _together(result, "f_hl_n1", "f_hl_n2")   # negotiation
        assert _together(result, "f_hl_s1", "f_hl_s2")   # signing
        assert not _together(result, "f_hl_n1", "f_hl_s1")
        assert _cluster_of(result, "f_hl_c1") is None    # candidate abstains

    def test_cross_sport_maccabi_tlv_hard_rejected(self, result):
        assert not _together(result, "f_xs_1", "f_xs_2")

    def test_bare_family_names_do_not_cluster(self, result):
        assert not _together(result, "f_fam_1", "f_fam_2")

    def test_same_source_pair_rejected(self, result):
        assert not _together(result, "f_ss_1", "f_ss_2")

    def test_transitive_chain_does_not_merge_unrelated_ends(self, result):
        # A ~ B ~ C where the bridge B mentions both clubs. A and C are DIFFERENT
        # signings at DIFFERENT clubs — plain union-find would merge all three.
        assert not _together(result, "f_tc_a", "f_tc_c")

    def test_zero_false_positives_overall(self, cases, result):
        """No must-not-cluster pair ended up in the same cluster. The acceptance bar."""
        violations = []
        for case in cases["must_not_cluster"]:
            ids = [a["id"] for a in case["articles"]]
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    if case["id"] == "fp_transitive_chain" and {ids[i], ids[j]} != {"f_tc_a", "f_tc_c"}:
                        continue  # only the A/C ends must be apart; A~B may legitimately pair
                    if _together(result, ids[i], ids[j]):
                        violations.append((case["id"], ids[i], ids[j]))
        assert violations == [], f"FALSE POSITIVES: {violations}"


class TestInPlayExclusion:
    def test_in_play_articles_never_become_candidates(self, cases, result):
        for case in cases["excluded_from_candidacy"]:
            for art in case["articles"]:
                assert art["id"] in result.excluded_ids, f"{art['id']} was not excluded"
                assert _cluster_of(result, art["id"]) is None

    def test_in_play_articles_produce_no_edges(self, cases, result):
        excluded = {a["id"] for c in cases["excluded_from_candidacy"] for a in c["articles"]}
        for e in result.edges:
            assert e.article_a not in excluded and e.article_b not in excluded


class TestGuardsAndDeterminism:
    def test_max_cluster_size_guard_respected(self, result):
        for c in result.clusters:
            assert c.size <= DEFAULT_CONFIG.max_cluster_size

    def test_cluster_time_span_bounded(self, result, window):
        by_id = {a.id: a for a in window}
        for c in result.clusters:
            times = [by_id[m].published_at for m in c.member_ids]
            span = (max(times) - min(times)).total_seconds() / 3600
            assert span <= DEFAULT_CONFIG.max_cluster_time_span_hours

    def test_matcher_is_deterministic(self, window):
        a = cluster_articles(window, DEFAULT_CONFIG)
        b = cluster_articles(window, DEFAULT_CONFIG)
        assert [(c.anchor_id, c.member_ids) for c in a.clusters] == \
               [(c.anchor_id, c.member_ids) for c in b.clusters]

    def test_input_order_does_not_change_output(self, window):
        a = cluster_articles(window, DEFAULT_CONFIG)
        b = cluster_articles(list(reversed(window)), DEFAULT_CONFIG)
        assert {(c.anchor_id, c.member_ids) for c in a.clusters} == \
               {(c.anchor_id, c.member_ids) for c in b.clusters}

    def test_matcher_does_not_mutate_inputs(self, window):
        before = [(a.id, a.title, a.entity_ids) for a in window]
        cluster_articles(window, DEFAULT_CONFIG)
        assert [(a.id, a.title, a.entity_ids) for a in window] == before

    def test_anchor_is_a_member_and_earliest(self, result, window):
        by_id = {a.id: a for a in window}
        for c in result.clusters:
            assert c.anchor_id in c.member_ids
            times = [by_id[m].published_at for m in c.member_ids]
            assert by_id[c.anchor_id].published_at == min(times)

    def test_representative_is_a_member(self, result):
        for c in result.clusters:
            assert c.representative_id in c.member_ids

    def test_every_edge_carries_discriminative_evidence(self, result):
        for e in result.edges:
            assert e.rare_tokens, f"edge {e.article_a}~{e.article_b} has no evidence"

    def test_edges_only_reference_surviving_members(self, result):
        for c in result.clusters:
            for e in c.edges:
                assert e.article_a in c.member_ids and e.article_b in c.member_ids

    def test_singletons_are_not_clusters(self, result):
        for c in result.clusters:
            assert c.size >= 2


class TestCoherenceDirectly:
    """The frozen transitive-chain fixture is now rejected at the PAIR level (its
    bridging tokens are non-discriminative in a realistic window), so it no longer
    exercises coherence. Coherence is a safety net and must be tested on its own —
    an untested safety net is not a safety net.
    """

    def _mk(self, _id, src, title, hour, ents=()):
        return ClusterInput(
            id=_id, source=src, title=title, sport="basketball",
            event_type="signing", event_certainty="confirmed", entity_ids=ents,
            published_at=datetime.fromisoformat(f"2026-07-07T{hour:02d}:00:00+00:00"),
        )

    def test_weak_bridge_cannot_chain_two_unrelated_ends(self):
        from app.clustering.coherence import validate_coherence
        from app.clustering.contract import MatchEdge

        a = self._mk("A", "s1", "כהן חתם במכבי", 9)
        bridge = self._mk("B", "s2", "כהן ולוי חתמו במכבי ובהפועל", 11)
        c = self._mk("C", "s3", "לוי חתם בהפועל", 13)

        # Only the bridge touches each end. A and C never match each other.
        edges = [
            MatchEdge("A", "B", 0.5, 2.0, ("כהן",), (), (), "B"),
            MatchEdge("B", "C", 0.5, 2.0, ("לוי",), (), (), "B"),
        ]
        coherent = validate_coherence([a, bridge, c], edges, DEFAULT_CONFIG)
        ids = {m.id for m in coherent} if coherent else set()
        # C matches only B — a PERIPHERAL member, not the anchor (A) or the
        # representative — so it must not be dragged in.
        assert not ({"A", "C"} <= ids), f"transitive chain merged unrelated ends: {ids}"

    def test_member_matching_the_anchor_is_admitted(self):
        from app.clustering.coherence import validate_coherence
        from app.clustering.contract import MatchEdge

        anchor = self._mk("A", "s1", "כהן חתם במכבי תל אביב", 9)
        rich = self._mk("B", "s2", "כהן חתם במכבי תל אביב רשמית", 11, ents=("team:x",))
        short = self._mk("C", "s3", "כהן במכבי", 12)

        edges = [
            MatchEdge("A", "B", 0.6, 2.0, ("כהן",), (), (), "B"),
            MatchEdge("A", "C", 0.5, 3.0, ("כהן",), (), (), "B"),  # strong, to the ANCHOR
        ]
        coherent = validate_coherence([anchor, rich, short], edges, DEFAULT_CONFIG)
        ids = {m.id for m in coherent}
        assert ids == {"A", "B", "C"}, "a strong match to the anchor must be admitted"

    def test_cluster_time_span_bound_rejects_a_far_member(self):
        from app.clustering.coherence import validate_coherence
        from app.clustering.contract import MatchEdge

        cfg = ClusteringConfig(max_cluster_time_span_hours=4.0)
        a = self._mk("A", "s1", "כהן חתם במכבי", 9)
        b = self._mk("B", "s2", "כהן חתם במכבי רשמית", 11)
        far = ClusterInput(
            id="C", source="s3", title="כהן חתם במכבי", sport="basketball",
            event_type="signing",
            published_at=datetime.fromisoformat("2026-07-09T09:00:00+00:00"),
        )
        edges = [
            MatchEdge("A", "B", 0.6, 2.0, ("כהן",), (), (), "B"),
            MatchEdge("A", "C", 0.6, 48.0, ("כהן",), (), (), "B"),
        ]
        coherent = validate_coherence([a, b, far], edges, cfg)
        assert {m.id for m in coherent} == {"A", "B"}


class TestCoveragePardox:
    """A story covered by N sources has df == N for its OWN defining tokens. If the
    discriminative threshold falls below the cluster size, a story becomes
    unclusterable BECAUSE it is widely covered — exactly backwards. This silently
    dropped the 4-source Recanati cluster during #100 and must never regress.
    """

    def test_threshold_must_exceed_max_cluster_size(self):
        cfg = DEFAULT_CONFIG
        min_window = cfg.min_window_for_valid_df()
        effective_threshold = cfg.df_ratio_max * min_window
        assert effective_threshold > cfg.max_cluster_size

    def test_small_window_is_flagged_as_unable_to_support_clustering(self):
        cfg = DEFAULT_CONFIG
        assert not cfg.df_supports_full_size_cluster(100)
        assert cfg.df_supports_full_size_cluster(cfg.min_window_for_valid_df())

    def test_the_test_window_satisfies_the_constraint(self, window):
        eligible = [a for a in window
                    if a.event_type not in ("interview",) and not is_in_play(a.title)]
        assert DEFAULT_CONFIG.df_supports_full_size_cluster(len(eligible)), (
            f"test window ({len(eligible)}) is too small for DF to be meaningful; "
            f"need >= {DEFAULT_CONFIG.min_window_for_valid_df()}"
        )

    def test_a_widely_covered_story_still_clusters(self, real_articles):
        # The regression guard: the 4-source story's own tokens (df=4) must remain
        # discriminative in a properly sized window.
        window = real_articles + _background_window()
        res = cluster_articles(window, DEFAULT_CONFIG)
        rf = next((c for c in res.clusters if "f_rf_1" in c.member_ids), None)
        assert rf is not None and rf.size == 4


class TestRejectionDiagnostics:
    def test_rejections_are_opt_in_only(self, window):
        assert cluster_articles(window, DEFAULT_CONFIG).rejections == []

    def test_rejection_reasons_are_bounded_and_named(self, result):
        allowed = {v for k, v in vars(Rejection).items() if not k.startswith("_")}
        assert result.rejections, "expected some near-misses in this window"
        for r in result.rejections:
            assert r.reason in allowed

    def test_template_pair_rejected_for_a_named_reason(self, result):
        r = next(
            (x for x in result.rejections
             if {x.article_a, x.article_b} == {"f_dp_2", "f_ash_1"}),
            None,
        )
        assert r is not None
        # Time window fires first; the discriminative gate would also have caught it.
        assert r.reason in (Rejection.OUTSIDE_TIME_WINDOW,
                            Rejection.NO_DISCRIMINATIVE_EVIDENCE)

    def test_cross_sport_pair_rejected_as_cross_sport(self, result):
        r = next(
            (x for x in result.rejections
             if {x.article_a, x.article_b} == {"f_xs_1", "f_xs_2"}),
            None,
        )
        assert r is not None and r.reason == Rejection.CROSS_SPORT
