"""
Issue #79 — Decision Contract Regression Locks (milestone: Explicit
Interests & Onboarding v2).

Locks the audited Preference V2 semantics that the explicit-interest layer
(#77/#82/#83) builds on. Production scoring logic is FROZEN for the
milestone: if any test in this file fails, the fix is NOT a casual engine
edit — stop, analyze, and only change scoring with explicit product-owner
sign-off and drift re-baseline steps.

Contract summary (verified against preference_engine.py at lock time):

- Overlap: max-points-wins across matched scopes, specificity breaks ties
  toward the broader scope; NO additive sport+competition+team stacking.
- Entity boost: the single deliberate +1 (followed entity on a broader base).
- Unknown event type ("news" after evidence downgrade) is NOT a negative
  signal: direct scope matches (sport, team/player, tier-1 explicit
  competition evidence) are never event-gated. Unknown events only lack
  diffuse reach (membership/participant tiers are allowlist-gated).
- Event precedence: scoped entry beats global (specificity — even a scoped
  calibration entry refines a global explicit one); for the SAME
  (scope_ref, event_type) target, source authority wins
  (explicit > learned > calibration).
- Push is override-only; no boost/delta/importance combination reaches it.

Tier -> level mapping used by the acquisition layer (#77):
  sport        Follow=0  Star=+1
  competition  Follow=+1 Star=+2
  team/player  Follow=+1 Star=+2
"""
from datetime import datetime, timezone

import pytest

from app.models.article import Article
from app.models.profile import UserProfile
from app.models.profile_v2 import EventAffinity, OverrideRule, ProfileV2, ScopeAffinity
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2
from app.services.relevance_engine import DECISION_RANK


def _article(**kwargs) -> Article:
    defaults = dict(
        id="contract_test",
        source="test",
        source_display_name="Test",
        url="https://example.com",
        title="Contract test article",
        language="he",
        published_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
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


def _profile(v2: ProfileV2, user_id: str = "contract_user") -> UserProfile:
    return UserProfile(
        user_id=user_id, display_name=user_id, profile_type="test",
        topics=[], profile_v2=v2,
    )


def _decision(article: Article, profile: UserProfile) -> str:
    return score_article_v2(article, profile).decision


# ── The four approved archetype profiles (built from the #77 tier mapping) ──

def archetype_a() -> UserProfile:
    """Broad basketball fan; EuroLeague followed; Maccabi TLV bb starred."""
    return _profile(ProfileV2(scope_affinities=[
        ScopeAffinity(scope="sport", target_id="basketball", level=0),
        ScopeAffinity(scope="competition", target_id="comp:euroleague", level=1),
        ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
    ]), "archetype_a")


def archetype_b() -> UserProfile:
    """Hapoel TLV bb starred + IBL followed. No sport scope, no NBA."""
    return _profile(ProfileV2(scope_affinities=[
        ScopeAffinity(scope="team", target_id="team:hapoel_tlv_bb", level=2),
        ScopeAffinity(scope="competition", target_id="comp:ibl", level=1),
    ]), "archetype_b")


def archetype_c() -> UserProfile:
    """NBA starred; Grand Slam tournaments followed. No sport:tennis."""
    return _profile(ProfileV2(scope_affinities=[
        ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
        ScopeAffinity(scope="competition", target_id="comp:wimbledon", level=1),
        ScopeAffinity(scope="competition", target_id="comp:roland_garros", level=1),
        ScopeAffinity(scope="competition", target_id="comp:us_open", level=1),
        ScopeAffinity(scope="competition", target_id="comp:australian_open", level=1),
    ]), "archetype_c")


def archetype_d() -> UserProfile:
    """Broad football; one club starred; basketball only via EuroLeague."""
    return _profile(ProfileV2(scope_affinities=[
        ScopeAffinity(scope="sport", target_id="football", level=0),
        ScopeAffinity(scope="team", target_id="team:hapoel_tlv_fc", level=2),
        ScopeAffinity(scope="competition", target_id="comp:euroleague", level=1),
    ]), "archetype_d")


# ── Lock 1: broad sport Follow (level 0) ─────────────────────────────────────

class TestBroadSportFollow:
    def test_sport_follow_gives_low_feed_coverage(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=0),
        ]))
        routine = _article(event_type="match_result")
        assert _decision(routine, profile) == "low_feed"

    def test_sport_follow_very_high_importance_lifts_to_feed(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=0),
        ]))
        big = _article(event_type="title_win", importance="very_high")
        assert _decision(big, profile) == "feed"

    def test_sport_star_gives_feed(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=1),
        ]))
        routine = _article(event_type="match_result")
        assert _decision(routine, profile) == "feed"

    def test_low_importance_pulls_sport_follow_to_hidden(self):
        """Coverage floor is not a noise guarantee: low-importance filler
        under a level-0 sport follow drops out (1 - 1 = 0)."""
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=0),
        ]))
        filler = _article(event_type="pre_match", importance="low")
        assert _decision(filler, profile) == "hidden"


# ── Lock 2: competition/team Star (+2) ───────────────────────────────────────

class TestStarBehavior:
    def test_starred_competition_gives_high_feed_base(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
        ]))
        article = _article(event_type="match_result", primary_competition="comp:nba")
        assert _decision(article, profile) == "high_feed"

    def test_starred_team_gives_high_feed_base(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
        ]))
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        assert _decision(article, profile) == "high_feed"

    def test_followed_competition_gives_feed_base(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
        ]))
        article = _article(event_type="match_result", primary_competition="comp:nba")
        assert _decision(article, profile) == "feed"


# ── Lock 3: no additive sport+competition+team stacking ──────────────────────

class TestNoAdditiveStacking:
    def test_triple_overlap_is_max_points_plus_single_entity_boost(self):
        """Archetype A's full stack on a Maccabi EuroLeague article:
        base = max(team +2 -> 3 pts) — NOT sport(1) + comp(2) + team(3)."""
        article = _article(
            entity_ids=["team:maccabi_tlv_bb"],
            primary_competition="comp:euroleague",
            event_type="match_result",
        )
        result = score_article_v2(article, archetype_a())
        assert result.decision == "high_feed"  # 3 points, not 6
        base = next(c for c in result.contributions if c["step"] == "base_scope")
        assert base["effect"] == "+3"
        # entity boost only applies when base is a BROADER scope; here the
        # team itself is the base, so no boost stacks on top.
        assert not any(c["step"] == "entity_boost" for c in result.contributions)

    def test_entity_boost_is_single_plus_one_on_broader_base(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ScopeAffinity(scope="player", target_id="player:deni_avdija", level=1),
            ScopeAffinity(scope="team", target_id="team:la_lakers", level=1),
        ]))
        # Two followed entities on one article still boost exactly once.
        article = _article(
            entity_ids=["player:deni_avdija", "team:la_lakers"],
            primary_competition="comp:nba", event_type="match_result",
        )
        result = score_article_v2(article, profile)
        boosts = [c for c in result.contributions if c["step"] == "entity_boost"]
        assert len(boosts) == 1
        assert result.decision == "high_feed"  # 2 + 1, not 2 + 2

    def test_adding_broad_scopes_never_lowers_specific_decision(self):
        narrow = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
        ]))
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        narrow_rank = DECISION_RANK[_decision(article, narrow)]
        stacked_rank = DECISION_RANK[_decision(article, archetype_a())]
        assert stacked_rank >= narrow_rank


# ── Lock 4: unknown event type is not a negative signal ─────────────────────

class TestUnknownEventFallback:
    """event_type="news" is the abstention value (evidence validation
    downgrades unsupported proposals to it). It must never erase known
    scope relevance — it only reduces personalization precision."""

    def test_unknown_event_visible_via_sport_follow(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=0),
        ]))
        article = _article(event_type="news")
        assert _decision(article, profile) == "low_feed"

    def test_unknown_event_visible_via_followed_entity(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="team", target_id="team:hapoel_tlv_bb", level=2),
        ]))
        article = _article(entity_ids=["team:hapoel_tlv_bb"], event_type="news")
        assert _decision(article, profile) == "high_feed"

    def test_unknown_event_visible_via_explicit_competition_evidence(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:euroleague", level=1),
        ]))
        article = _article(event_type="news", primary_competition="comp:euroleague")
        assert _decision(article, profile) == "feed"

    def test_unknown_event_gets_no_membership_reach(self):
        """#64 Q2 decision lock: `news` stays OUT of the reach allowlists.
        A followed competition does NOT see entity-only news via diffuse
        team-membership reach."""
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:euroleague", level=2),
        ]))
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="news")
        assert _decision(article, profile) == "hidden"

    def test_unknown_event_gets_no_participant_inference(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
        ]))
        article = _article(
            entity_ids=["team:la_lakers", "team:boston_celtics"], event_type="news",
        )
        assert _decision(article, profile) == "hidden"

    def test_seed_guy_fixture_unchanged_no_basketball_floor(self):
        """#64 Q1 decision lock: the floor is per-user via explicit
        selection, NOT an edit to Guy's seed fixture. An unresolved
        basketball article stays hidden for seed Guy but is low_feed for a
        user who explicitly follows basketball."""
        guy = next(p for p in SEED_PROFILES if p.user_id == "guy")
        unresolved = _article(event_type="news")  # sport known, nothing else
        assert _decision(unresolved, guy) == "hidden"
        assert _decision(unresolved, archetype_a()) == "low_feed"


# ── Lock 5: direct scope match vs diffuse reach ──────────────────────────────

class TestDirectVsDiffuseReach:
    def test_membership_reach_stays_event_gated(self):
        """interview is deliberately in neither allowlist: no reach."""
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:euroleague", level=2),
        ]))
        interview = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="interview")
        assert _decision(interview, profile) == "hidden"

    def test_membership_ceiling_caps_diffuse_reach_at_feed(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:euroleague", level=2),
        ]))
        signing = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        result = score_article_v2(signing, profile)
        assert result.decision == "feed"
        assert any(c["step"] == "ceiling" for c in result.contributions)

    def test_entity_backing_exempts_membership_ceiling(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:euroleague", level=2),
            ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=0),
        ]))
        signing = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        assert _decision(signing, profile) == "high_feed"

    def test_tier1_explicit_evidence_never_capped(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:euroleague", level=2),
        ]))
        article = _article(event_type="match_result",
                           primary_competition="comp:euroleague",
                           importance="very_high")
        assert _decision(article, profile) == "high_feed"


# ── Lock 6: scoped vs global event affinity (both precedence directions) ────

class TestEventPrecedence:
    def test_scoped_calibration_refines_global_explicit(self):
        """Specificity direction: a scoped CALIBRATION delta beats a global
        EXPLICIT delta for the base scope — nuance refines gesture. This is
        intended behavior (documented in RELEVANCE_CONTRACT / INTERESTS)."""
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ],
            event_affinities=[
                EventAffinity(scope_ref=None, event_type="interview", delta=-1,
                              source="explicit"),
                EventAffinity(scope_ref="comp:nba", event_type="interview", delta=1,
                              source="calibration"),
            ],
        ))
        article = _article(event_type="interview", primary_competition="comp:nba")
        assert _decision(article, profile) == "high_feed"  # 2 + 1, not 2 - 1

    def test_global_explicit_applies_when_no_scoped_entry(self):
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ],
            event_affinities=[
                EventAffinity(scope_ref=None, event_type="interview", delta=-1,
                              source="explicit"),
            ],
        ))
        article = _article(event_type="interview", primary_competition="comp:nba")
        assert _decision(article, profile) == "low_feed"  # 2 - 1

    def test_same_target_authority_explicit_beats_calibration(self):
        """Authority direction: for the SAME (scope_ref, event_type), the
        explicit entry wins over the calibration entry."""
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ],
            event_affinities=[
                EventAffinity(scope_ref="comp:nba", event_type="interview", delta=-1,
                              source="explicit"),
                EventAffinity(scope_ref="comp:nba", event_type="interview", delta=2,
                              source="calibration"),
            ],
        ))
        article = _article(event_type="interview", primary_competition="comp:nba")
        assert _decision(article, profile) == "low_feed"  # 2 - 1, not 2 + 2

    def test_same_target_authority_explicit_beats_learned(self):
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
            ],
            event_affinities=[
                EventAffinity(scope_ref="comp:nba", event_type="schedule", delta=1,
                              source="explicit"),
                EventAffinity(scope_ref="comp:nba", event_type="schedule", delta=-2,
                              source="learned"),
            ],
        ))
        article = _article(event_type="schedule", primary_competition="comp:nba")
        assert _decision(article, profile) == "high_feed"  # 2 + 1


# ── Lock 7: same-target scope authority ──────────────────────────────────────

class TestScopeAuthority:
    @pytest.mark.parametrize("weaker_source", ["calibration", "learned"])
    def test_explicit_scope_level_wins_same_target(self, weaker_source):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=2,
                          source="explicit"),
            ScopeAffinity(scope="competition", target_id="comp:nba", level=-1,
                          source=weaker_source),
        ]))
        article = _article(event_type="match_result", primary_competition="comp:nba")
        assert _decision(article, profile) == "high_feed"

    def test_learned_refines_calibration_same_target(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=0,
                          source="calibration"),
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1,
                          source="learned"),
        ]))
        article = _article(event_type="match_result", primary_competition="comp:nba")
        assert _decision(article, profile) == "feed"


# ── Lock 8: exclude semantics ────────────────────────────────────────────────

class TestExcludeSemantics:
    def test_strictly_more_specific_follow_beats_broader_exclude(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=-2),
            ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
        ]))
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        assert _decision(article, profile) == "high_feed"

    def test_specific_exclude_beats_broader_follow(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
            ScopeAffinity(scope="team", target_id="team:la_lakers", level=-2),
        ]))
        article = _article(entity_ids=["team:la_lakers"], event_type="signing",
                           primary_competition="comp:nba")
        assert _decision(article, profile) == "hidden"

    def test_equal_specificity_exclude_hides(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=-2),
            ScopeAffinity(scope="sport", target_id="basketball", level=1),
        ]))
        # comp exclude is MORE specific than the sport follow → hides.
        article = _article(event_type="match_result", primary_competition="comp:nba")
        assert _decision(article, profile) == "hidden"


# ── Lock 9: importance interaction ───────────────────────────────────────────

class TestImportanceInteraction:
    def test_very_high_only_elevates_already_visible(self):
        """The importance gate: very_high never creates visibility."""
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="tennis", level=-1),
        ]))
        article = _article(sport="tennis", event_type="grand_slam_winner",
                           importance="very_high")
        assert _decision(article, profile) == "hidden"  # 0 → gate blocks +1

    def test_low_importance_steps_down(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
        ]))
        article = _article(event_type="match_result", primary_competition="comp:nba",
                           importance="low")
        assert _decision(article, profile) == "low_feed"


# ── Lock 10: push discipline ─────────────────────────────────────────────────

class TestPushDiscipline:
    def test_no_combination_reaches_push_without_override(self):
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
                ScopeAffinity(scope="competition", target_id="comp:euroleague", level=2),
                ScopeAffinity(scope="sport", target_id="basketball", level=1),
            ],
            event_affinities=[
                EventAffinity(scope_ref="team:maccabi_tlv_bb",
                              event_type="title_win", delta=2),
            ],
        ))
        article = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="title_win",
                           primary_competition="comp:euroleague",
                           importance="very_high")
        assert _decision(article, profile) == "high_feed"

    def test_always_push_override_is_the_only_push_path(self):
        v2 = ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
            ],
            overrides=[
                OverrideRule(kind="always_push", scope="team",
                             target_id="team:maccabi_tlv_bb", event_type="signing"),
            ],
        )
        signing = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing")
        other = _article(entity_ids=["team:maccabi_tlv_bb"], event_type="candidate")
        assert _decision(signing, _profile(v2)) == "push"
        assert _decision(other, _profile(v2)) != "push"

    def test_archetypes_without_overrides_never_push(self):
        """Onboarding (#82) creates no always_push rules — archetype
        profiles must be push-free on any article."""
        articles = [
            _article(entity_ids=["team:maccabi_tlv_bb"], event_type="signing",
                     importance="very_high"),
            _article(entity_ids=["team:hapoel_tlv_bb"], event_type="title_win",
                     importance="very_high"),
            _article(event_type="finals_result", primary_competition="comp:nba",
                     importance="very_high"),
        ]
        for arch in (archetype_a(), archetype_b(), archetype_c(), archetype_d()):
            for article in articles:
                assert _decision(article, arch) != "push"


# ── Required scenario 1: initial feeds materially differ, zero feedback ──────

class TestRequiredScenarioCrossProfile:
    # Shared article set: (id, kwargs)
    ARTICLES = {
        "greek_routine": dict(event_type="match_result",
                              primary_competition="comp:greek_basket"),
        "el_result": dict(event_type="match_result",
                          primary_competition="comp:euroleague"),
        "maccabi_signing": dict(entity_ids=["team:maccabi_tlv_bb"],
                                event_type="signing"),
        "nba_game": dict(entity_ids=["team:charlotte_hornets",
                                     "team:washington_wizards"],
                         event_type="regular_season_result"),
        "unknown_bb": dict(event_type="news"),
    }

    def _feed_vector(self, profile: UserProfile) -> dict:
        return {
            key: _decision(_article(id=key, **spec), profile)
            for key, spec in self.ARTICLES.items()
        }

    def test_archetype_a_differs_from_generic_and_nba_only(self):
        generic_bb = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=0),
        ]), "generic_bb")
        nba_only = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
        ]), "nba_only")

        a_vec = self._feed_vector(archetype_a())
        generic_vec = self._feed_vector(generic_bb)
        nba_vec = self._feed_vector(nba_only)

        # Exact expected decisions — the material differences, not just "differ".
        assert a_vec == {
            "greek_routine": "low_feed",     # broad coverage floor
            "el_result": "feed",             # followed competition
            "maccabi_signing": "high_feed",  # starred team
            "nba_game": "low_feed",          # only via the sport floor
            "unknown_bb": "low_feed",        # unknown event ≠ negative signal
        }
        assert generic_vec == {
            "greek_routine": "low_feed",
            "el_result": "low_feed",
            "maccabi_signing": "low_feed",
            "nba_game": "low_feed",
            "unknown_bb": "low_feed",
        }
        assert nba_vec == {
            "greek_routine": "hidden",
            "el_result": "hidden",
            "maccabi_signing": "hidden",
            "nba_game": "feed",
            "unknown_bb": "hidden",
        }
        assert a_vec != generic_vec and a_vec != nba_vec and generic_vec != nba_vec

    def test_same_article_four_archetype_decisions(self):
        nba_game = _article(entity_ids=["team:charlotte_hornets",
                                        "team:washington_wizards"],
                            event_type="regular_season_result")
        assert _decision(nba_game, archetype_a()) == "low_feed"
        assert _decision(nba_game, archetype_b()) == "hidden"
        assert _decision(nba_game, archetype_c()) == "high_feed"
        assert _decision(nba_game, archetype_d()) == "hidden"


# ── Required scenario 2: unknown-event basketball article eligibility ────────

class TestRequiredScenarioUnknownEvent:
    def test_unknown_event_basketball_article_across_profiles(self):
        article = _article(event_type="news", sport="basketball")
        # Sport follower: eligible at the coverage cap (low_feed).
        assert _decision(article, archetype_a()) == "low_feed"
        # No basketball sport scope, no evidence → hidden.
        assert _decision(article, archetype_b()) == "hidden"

    def test_unknown_event_with_explicit_competition_evidence(self):
        article = _article(event_type="news", sport="basketball",
                           primary_competition="comp:nba")
        # Starred competition + tier-1 evidence: full base even with
        # unknown event (direct matches are never event-gated).
        assert _decision(article, archetype_c()) == "high_feed"


# ── Archetype end-to-end sanity (the walkthroughs from the plan) ─────────────

class TestArchetypeWalkthroughs:
    def test_archetype_b_hapoel_and_ibl(self):
        b = archetype_b()
        hapoel = _article(entity_ids=["team:hapoel_tlv_bb"], event_type="signing")
        ibl = _article(event_type="match_result", primary_competition="comp:ibl")
        nba = _article(entity_ids=["team:la_lakers", "team:boston_celtics"],
                       event_type="match_result")
        assert _decision(hapoel, b) == "high_feed"
        assert _decision(ibl, b) == "feed"
        assert _decision(nba, b) == "hidden"

    def test_archetype_c_slams_only_tennis(self):
        c = archetype_c()
        slam = _article(sport="tennis", event_type="grand_slam_winner",
                        primary_competition="comp:wimbledon", importance="very_high")
        early = _article(sport="tennis", event_type="early_round_result")
        assert _decision(slam, c) == "high_feed"
        assert _decision(early, c) == "hidden"

    def test_archetype_d_football_and_euroleague_only(self):
        d = archetype_d()
        club = _article(sport="football", entity_ids=["team:hapoel_tlv_fc"],
                        event_type="signing")
        generic_fc = _article(sport="football", event_type="match_result")
        el = _article(event_type="match_result",
                      primary_competition="comp:euroleague")
        nba = _article(entity_ids=["team:la_lakers", "team:boston_celtics"],
                       event_type="match_result")
        assert _decision(club, d) == "high_feed"
        assert _decision(generic_fc, d) == "low_feed"
        assert _decision(el, d) == "feed"
        assert _decision(nba, d) == "hidden"
