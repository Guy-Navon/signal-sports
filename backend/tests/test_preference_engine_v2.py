"""
Issue #32 — Preference Model V2: layered affinity scorer.

Covers: per-layer scorer behavior (base scope, entity boost, event delta,
importance, membership ceiling, exclude, overrides), monotonicity property
tests (raising an affinity never lowers a decision; adding a matching entity
never lowers rank; mute beats everything), ProfileV2 validation, the shadow
harness, and the Guy / Casual-Deni-Fan end-to-end regression fixtures.
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.article import Article
from app.models.profile import UserProfile
from app.models.profile_v2 import (
    EventAffinity,
    OverrideRule,
    ProfileV2,
    ScopeAffinity,
)
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2
from app.services.relevance_engine import DECISION_RANK
from app.services.shadow_service import build_shadow_report


def _article(**kwargs) -> Article:
    defaults = dict(
        id="v2_test",
        source="test",
        source_display_name="Test",
        url="https://example.com",
        title="Test article",
        language="he",
        published_at=datetime(2026, 7, 7, tzinfo=timezone.utc),
        sport="basketball",
        league=None,
        entities=[],
        event_type="news",
        importance="medium",
        confidence=0.9,
        tags=[],
        primary_competition=None,
        article_competitions=[],
        entity_ids=[],
        taxonomy_version=1,
    )
    defaults.update(kwargs)
    return Article(**defaults)


def _profile(v2: ProfileV2, **kwargs) -> UserProfile:
    defaults = dict(
        user_id="v2_test_user",
        display_name="V2 Test",
        profile_type="test",
        topics=[],
        profile_v2=v2,
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)


@pytest.fixture(scope="module")
def guy():
    return next(p for p in SEED_PROFILES if p.user_id == "guy")


@pytest.fixture(scope="module")
def deni_fan():
    return next(p for p in SEED_PROFILES if p.user_id == "casual_deni_fan")


# ── Layer: base scope ────────────────────────────────────────────────────────

class TestBaseScope:
    @pytest.mark.parametrize("level,expected", [
        (2, "high_feed"), (1, "feed"), (0, "low_feed"), (-1, "hidden"),
    ])
    def test_competition_level_maps_to_base_decision(self, level, expected):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=level),
        ]))
        article = _article(event_type="match_result", primary_competition="comp:nba")
        assert score_article_v2(article, profile).decision == expected

    def test_no_matching_scope_hidden(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
        ]))
        article = _article(sport="football", event_type="match_result")
        result = score_article_v2(article, profile)
        assert result.decision == "hidden"
        assert result.matched_event_rule == "no_matching_scope"

    def test_no_profile_v2_hidden(self):
        profile = UserProfile(user_id="x", display_name="X", profile_type="test")
        assert score_article_v2(_article(), profile).decision == "hidden"

    def test_competition_scope_consumes_visibility_match_kinds(self):
        """The v2 scorer reuses match_competition_names — a participant-
        inferred NBA game matches a comp:nba affinity with no explicit
        evidence, and the trace carries the provenance."""
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
        ]))
        article = _article(
            entity_ids=["team:la_lakers", "team:boston_celtics"],
            event_type="match_result",
        )
        result = score_article_v2(article, profile)
        assert result.decision == "feed"
        base = next(c for c in result.contributions if c["step"] == "base_scope")
        assert "participant_inference" in base["detail"]

    def test_team_scope_entity_ids_first(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
        ]))
        # post-facts row: legacy string absent, canonical id present → match
        by_id = _article(entity_ids=["team:maccabi_tlv_bb"], entities=[],
                         event_type="candidate")
        assert score_article_v2(by_id, profile).decision == "high_feed"
        # legacy row: display string path
        legacy = _article(entities=["Maccabi Tel Aviv Basketball"], entity_ids=[],
                          taxonomy_version=None, event_type="candidate")
        assert score_article_v2(legacy, profile).decision == "high_feed"

    def test_team_scope_sport_guard(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
        ]))
        football = _article(sport="football", entity_ids=["team:maccabi_tlv_bb"],
                            event_type="match_result")
        assert score_article_v2(football, profile).decision == "hidden"

    def test_max_points_wins_over_specificity(self):
        """A low team follow must not drag a very-high competition follow
        down — max points wins (adding an affinity never lowers)."""
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
            ScopeAffinity(scope="team", target_id="team:la_lakers", level=-1),
        ]))
        article = _article(entity_ids=["team:la_lakers"], event_type="signing",
                           primary_competition="comp:nba")
        assert score_article_v2(article, profile).decision == "high_feed"


# ── Layer: exclude ───────────────────────────────────────────────────────────

class TestExclude:
    def test_exclude_hides(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="football", level=-2),
        ]))
        article = _article(sport="football", event_type="major_transfer",
                           importance="very_high")
        result = score_article_v2(article, profile)
        assert result.decision == "hidden"
        assert result.matched_event_rule == "excluded_scope"

    def test_more_specific_follow_beats_broader_exclude(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=-2),
            ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
        ]))
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="candidate")
        assert score_article_v2(article, profile).decision == "high_feed"

    def test_specific_exclude_beats_broader_follow(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
            ScopeAffinity(scope="team", target_id="team:la_lakers", level=-2),
        ]))
        article = _article(entity_ids=["team:la_lakers"], event_type="signing",
                           primary_competition="comp:nba")
        assert score_article_v2(article, profile).decision == "hidden"


# ── Layer: entity boost ──────────────────────────────────────────────────────

class TestEntityBoost:
    def test_followed_player_boosts_competition_base(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ScopeAffinity(scope="player", target_id="player:deni_avdija", level=1),
        ]))
        with_deni = _article(entity_ids=["player:deni_avdija"],
                             event_type="match_result", primary_competition="comp:nba")
        without = _article(event_type="match_result", primary_competition="comp:nba")
        assert score_article_v2(without, profile).decision == "feed"
        assert score_article_v2(with_deni, profile).decision == "high_feed"

    def test_low_level_entity_does_not_boost(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ScopeAffinity(scope="player", target_id="player:deni_avdija", level=0),
        ]))
        article = _article(entity_ids=["player:deni_avdija"],
                           event_type="match_result", primary_competition="comp:nba")
        assert score_article_v2(article, profile).decision == "feed"


# ── Layer: event affinity ────────────────────────────────────────────────────

class TestEventAffinity:
    def test_scoped_delta_beats_global(self):
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ],
            event_affinities=[
                EventAffinity(scope_ref=None, event_type="schedule", delta=-1),
                EventAffinity(scope_ref="comp:nba", event_type="schedule", delta=-2),
            ],
        ))
        article = _article(event_type="schedule", primary_competition="comp:nba")
        assert score_article_v2(article, profile).decision == "hidden"  # 2-2=0

    def test_global_delta_applies_when_no_scoped(self):
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ],
            event_affinities=[
                EventAffinity(scope_ref=None, event_type="playoff_result", delta=1),
            ],
        ))
        article = _article(event_type="playoff_result", primary_competition="comp:nba")
        assert score_article_v2(article, profile).decision == "high_feed"

    def test_event_alias_honored(self):
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ],
            event_affinities=[
                EventAffinity(scope_ref="comp:nba", event_type="match_result", delta=-2),
            ],
        ))
        # regular_season_result aliases to match_result
        article = _article(event_type="regular_season_result",
                           primary_competition="comp:nba")
        assert score_article_v2(article, profile).decision == "hidden"


# ── Layer: importance ────────────────────────────────────────────────────────

class TestImportance:
    def test_very_high_importance_plus_one(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
        ]))
        article = _article(event_type="match_result", primary_competition="comp:nba",
                           importance="very_high")
        assert score_article_v2(article, profile).decision == "high_feed"

    def test_low_importance_minus_one(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
        ]))
        article = _article(event_type="match_result", primary_competition="comp:nba",
                           importance="low")
        assert score_article_v2(article, profile).decision == "low_feed"

    def test_importance_never_reaches_push(self):
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
            ],
            event_affinities=[
                EventAffinity(scope_ref="team:maccabi_tlv_bb",
                              event_type="title_win", delta=2),
            ],
        ))
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="title_win",
                           importance="very_high")
        # 3 + 2 + 1 = 6 → still capped at high_feed (no always_push override here)
        assert score_article_v2(article, profile).decision == "high_feed"


# ── Layer: membership ceiling ────────────────────────────────────────────────

class TestMembershipCeiling:
    def test_membership_reach_capped_at_feed_without_entity_backing(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:euroleague", level=2),
        ]))
        # Maccabi signing reaches EuroLeague via diffuse membership only.
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        result = score_article_v2(article, profile)
        assert result.decision == "feed"
        assert any(c["step"] == "ceiling" for c in result.contributions)

    def test_entity_backing_exempts_ceiling(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:euroleague", level=2),
            ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
        ]))
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        assert score_article_v2(article, profile).decision == "high_feed"

    def test_participant_inference_not_capped(self):
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
            ],
        ))
        article = _article(entity_ids=["team:la_lakers", "team:boston_celtics"],
                           event_type="match_result")
        # base 3 via participant inference — no ceiling.
        assert score_article_v2(article, profile).decision == "high_feed"


# ── Layer: overrides ─────────────────────────────────────────────────────────

class TestOverrides:
    def test_always_push_is_the_only_push_path(self):
        v2 = ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
            ],
            overrides=[
                OverrideRule(kind="always_push", scope="team",
                             target_id="team:maccabi_tlv_bb", event_type="signing"),
            ],
        )
        profile = _profile(v2)
        signing = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        candidate = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="candidate")
        assert score_article_v2(signing, profile).decision == "push"
        assert score_article_v2(candidate, profile).decision != "push"

    def test_never_show_beats_very_high_base(self):
        v2 = ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
            ],
            overrides=[
                OverrideRule(kind="never_show", scope="team",
                             target_id="team:maccabi_tlv_bb", event_type="pre_match"),
            ],
        )
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="pre_match",
                           importance="very_high")
        assert score_article_v2(article, _profile(v2)).decision == "hidden"

    def test_mute_beats_always_push(self):
        v2 = ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
            ],
            overrides=[
                OverrideRule(kind="mute", scope="team",
                             target_id="team:maccabi_tlv_bb"),
                OverrideRule(kind="always_push", scope="team",
                             target_id="team:maccabi_tlv_bb", event_type="signing"),
            ],
        )
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        assert score_article_v2(article, _profile(v2)).decision == "hidden"


# ── Provenance: learned never overrides explicit ─────────────────────────────

class TestProvenance:
    def test_learned_entry_never_overrides_explicit(self):
        v2 = ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=2,
                          source="explicit"),
            ScopeAffinity(scope="competition", target_id="comp:nba", level=-1,
                          source="learned"),
        ])
        article = _article(event_type="match_result", primary_competition="comp:nba")
        assert score_article_v2(article, _profile(v2)).decision == "high_feed"

    def test_learned_entry_applies_when_no_explicit(self):
        v2 = ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1,
                          source="learned"),
        ])
        article = _article(event_type="match_result", primary_competition="comp:nba")
        assert score_article_v2(article, _profile(v2)).decision == "feed"


# ── Monotonicity properties ──────────────────────────────────────────────────

class TestMonotonicity:
    ARTICLES = [
        dict(event_type="match_result", primary_competition="comp:nba"),
        dict(event_type="signing", primary_competition="comp:nba",
             entity_ids=["team:la_lakers"]),
        dict(event_type="playoff_result", primary_competition="comp:nba",
             importance="very_high"),
        dict(event_type="schedule", primary_competition="comp:nba", importance="low"),
    ]

    def test_raising_scope_affinity_never_lowers_decision(self):
        for spec in self.ARTICLES:
            article = _article(**spec)
            previous = -1
            for level in (-1, 0, 1, 2):
                profile = _profile(ProfileV2(scope_affinities=[
                    ScopeAffinity(scope="competition", target_id="comp:nba", level=level),
                ]))
                rank = DECISION_RANK[score_article_v2(article, profile).decision]
                assert rank >= previous, f"level {level} lowered decision for {spec}"
                previous = rank

    def test_raising_event_delta_never_lowers_decision(self):
        article = _article(event_type="match_result", primary_competition="comp:nba")
        previous = -1
        for delta in (-2, -1, 0, 1, 2):
            profile = _profile(ProfileV2(
                scope_affinities=[
                    ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
                ],
                event_affinities=[
                    EventAffinity(scope_ref="comp:nba", event_type="match_result",
                                  delta=delta),
                ],
            ))
            rank = DECISION_RANK[score_article_v2(article, profile).decision]
            assert rank >= previous
            previous = rank

    def test_adding_matching_entity_never_lowers_rank(self):
        base_profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
        ]))
        richer_profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ScopeAffinity(scope="player", target_id="player:deni_avdija", level=1),
        ]))
        for spec in self.ARTICLES:
            spec = {**spec, "entity_ids": [*spec.get("entity_ids", []),
                                           "player:deni_avdija"]}
            article = _article(**spec)
            base_rank = DECISION_RANK[score_article_v2(article, base_profile).decision]
            richer_rank = DECISION_RANK[score_article_v2(article, richer_profile).decision]
            assert richer_rank >= base_rank

    def test_mute_beats_everything(self):
        v2 = ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
                ScopeAffinity(scope="competition", target_id="comp:ibl", level=2),
            ],
            overrides=[
                OverrideRule(kind="mute", scope="team", target_id="team:maccabi_tlv_bb"),
                OverrideRule(kind="always_push", scope="team",
                             target_id="team:maccabi_tlv_bb", event_type="signing"),
            ],
        )
        for event in ("signing", "negotiation", "title_win", "match_result"):
            article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type=event,
                               importance="very_high", primary_competition="comp:ibl")
            assert score_article_v2(article, _profile(v2)).decision == "hidden", event


# ── ProfileV2 validation ─────────────────────────────────────────────────────

class TestValidation:
    def test_level_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            ScopeAffinity(scope="competition", target_id="comp:nba", level=3)

    def test_target_kind_mismatch_rejected(self):
        with pytest.raises(ValidationError):
            ScopeAffinity(scope="competition", target_id="team:la_lakers", level=1)
        with pytest.raises(ValidationError):
            ScopeAffinity(scope="team", target_id="comp:nba", level=1)
        with pytest.raises(ValidationError):
            ScopeAffinity(scope="sport", target_id="comp:nba", level=1)

    def test_override_source_must_be_explicit(self):
        with pytest.raises(ValidationError):
            OverrideRule(kind="mute", scope="team", target_id="team:la_lakers",
                         source="learned")

    def test_event_delta_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            EventAffinity(event_type="signing", delta=3)


# ── Guy / Deni end-to-end fixtures (acceptance list) ─────────────────────────

class TestSeedProfileFixtures:
    def test_guy_maccabi_push_rules_fire(self, guy):
        for event in ("signing", "negotiation", "injury", "title_win"):
            article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type=event)
            assert score_article_v2(article, guy).decision == "push", event

    def test_guy_broad_visibility(self, guy):
        nba = _article(entity_ids=["team:la_lakers", "team:boston_celtics"],
                       event_type="match_result")
        ibl = _article(entity_ids=["team:maccabi_ramat_gan"], event_type="signing")
        el = _article(event_type="match_result", primary_competition="comp:euroleague")
        for a in (nba, ibl, el):
            assert score_article_v2(a, guy).decision in ("feed", "high_feed")

    def test_guy_secondary_leagues_selective(self, guy):
        routine = _article(event_type="match_result", primary_competition="comp:acb")
        title = _article(event_type="title_win", primary_competition="comp:acb",
                         importance="very_high")
        assert score_article_v2(routine, guy).decision == "hidden"
        assert score_article_v2(title, guy).decision == "high_feed"

    def test_guy_football_tennis_quiet(self, guy):
        football = _article(sport="football", event_type="match_result")
        tennis = _article(sport="tennis", event_type="early_round_result")
        assert score_article_v2(football, guy).decision == "hidden"
        assert score_article_v2(tennis, guy).decision == "hidden"

    def test_deni_fan_only_sees_deni(self, deni_fan):
        deni_trade = _article(entity_ids=["player:deni_avdija"], event_type="major_trade")
        nba_game = _article(entity_ids=["team:la_lakers", "team:boston_celtics"],
                            event_type="match_result")
        assert score_article_v2(deni_trade, deni_fan).decision == "push"
        assert score_article_v2(nba_game, deni_fan).decision == "hidden"

    def test_same_article_different_decisions_per_profile(self, guy, deni_fan):
        """The core product invariant: one article, two users, two decisions."""
        nba_game = _article(entity_ids=["team:charlotte_hornets",
                                        "team:washington_wizards"],
                            event_type="regular_season_result", league="NBA")
        assert score_article_v2(nba_game, guy).decision == "feed"
        assert score_article_v2(nba_game, deni_fan).decision == "hidden"

    def test_every_decision_has_contributions(self, guy):
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        result = score_article_v2(article, guy)
        assert result.contributions, "explainability is non-negotiable"
        assert all({"step", "effect", "detail"} <= set(c) for c in result.contributions)


# ── Shadow harness ───────────────────────────────────────────────────────────

class TestShadowHarness:
    def test_report_shape_and_counts(self, guy):
        articles = [
            _article(id="a1", entity_ids=["team:maccabi_tlv_bb"], event_type="signing"),
            _article(id="a2", sport="tennis", event_type="early_round_result"),
            _article(id="a3", entity_ids=["team:la_lakers", "team:boston_celtics"],
                     event_type="match_result", league="NBA"),
        ]
        report = build_shadow_report(articles, guy)
        assert report.total == 3
        assert report.agreements + report.disagreements == 3
        assert all(not c.agree for c in report.comparisons)
        for c in report.comparisons:
            assert c.direction in ("promoted", "demoted")
            assert c.v2_contributions is not None
