"""
Issue #84 — Human-readable decision provenance.

Structured contributions remain the machine-readable contract; the Hebrew
narrative is presentation built from them. These tests lock the additive
`source` field, the provenance reasoning labels, and the explicit
unknown-event-fallback trace line. NO scoring behavior changes (the full
decision-contract suite from #79 guards that).
"""
from datetime import datetime, timezone

from app.models.article import Article
from app.models.profile import UserProfile
from app.models.profile_v2 import EventAffinity, ProfileV2, ScopeAffinity
from app.services.preference_engine import score_article_v2


def _article(**kwargs) -> Article:
    defaults = dict(
        id="prov_test", source="test", source_display_name="Test",
        url="https://example.com", title="t", language="he",
        published_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
        sport="basketball", league=None, entities=[], event_type="news",
        importance="medium", confidence=0.9, tags=[],
        primary_competition=None, article_competitions=[], entity_ids=[],
        taxonomy_version=1,
    )
    defaults.update(kwargs)
    return Article(**defaults)


def _profile(v2: ProfileV2) -> UserProfile:
    return UserProfile(user_id="prov_user", display_name="Prov",
                       profile_type="test", topics=[], profile_v2=v2)


def _contribution(result, step):
    return next(c for c in result.contributions if c["step"] == step)


class TestSourceField:
    def test_base_scope_carries_source(self):
        for source in ("explicit", "calibration", "learned"):
            profile = _profile(ProfileV2(scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1,
                              source=source),
            ]))
            result = score_article_v2(
                _article(event_type="match_result", primary_competition="comp:nba"),
                profile,
            )
            assert _contribution(result, "base_scope")["source"] == source

    def test_event_affinity_carries_source(self):
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1,
                              source="explicit"),
            ],
            event_affinities=[
                EventAffinity(scope_ref="comp:nba", event_type="interview",
                              delta=1, source="calibration"),
            ],
        ))
        result = score_article_v2(
            _article(event_type="interview", primary_competition="comp:nba"),
            profile,
        )
        assert _contribution(result, "event_affinity")["source"] == "calibration"

    def test_authority_winner_is_the_reported_source(self):
        """The trace reports the entry that actually fired: explicit beats
        learned on the same target, so the trace says explicit."""
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=2,
                          source="explicit"),
            ScopeAffinity(scope="competition", target_id="comp:nba", level=-1,
                          source="learned"),
        ]))
        result = score_article_v2(
            _article(event_type="match_result", primary_competition="comp:nba"),
            profile,
        )
        assert _contribution(result, "base_scope")["source"] == "explicit"

    def test_structured_contract_shape_preserved(self):
        """Every contribution still carries the core structured keys —
        the narrative never replaces structured data."""
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=0),
        ]))
        result = score_article_v2(_article(), profile)
        for c in result.contributions:
            assert {"step", "scope", "effect", "detail"} <= set(c)


class TestHebrewNarrative:
    def test_base_line_carries_provenance_label(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:nba", level=1,
                          source="calibration"),
        ]))
        result = score_article_v2(
            _article(event_type="match_result", primary_competition="comp:nba"),
            profile,
        )
        assert any("מכויל" in line for line in result.reasoning)

    def test_explicit_label_on_explicit_follow(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=0,
                          source="explicit"),
        ]))
        result = score_article_v2(_article(event_type="match_result"), profile)
        assert any("בחירה מפורשת" in line for line in result.reasoning)


class TestUnknownEventFallbackTrace:
    def test_news_article_shows_fallback_step(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=0),
        ]))
        result = score_article_v2(_article(event_type="news"), profile)
        fallback = _contribution(result, "event_affinity")
        assert fallback["detail"] == "unknown_event_fallback"
        assert fallback["effect"] == "0"
        assert any("סוג אירוע לא זוהה" in line for line in result.reasoning)
        assert result.decision == "low_feed"  # the base scope stands

    def test_known_event_has_no_fallback_step(self):
        profile = _profile(ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="basketball", level=0),
        ]))
        result = score_article_v2(_article(event_type="match_result"), profile)
        assert not any(
            c.get("detail") == "unknown_event_fallback" for c in result.contributions
        )

    def test_news_with_matching_delta_reports_delta_not_fallback(self):
        """A profile with an explicit `news` delta gets the delta step —
        fallback is only for the no-entry case."""
        profile = _profile(ProfileV2(
            scope_affinities=[
                ScopeAffinity(scope="sport", target_id="basketball", level=1),
            ],
            event_affinities=[
                EventAffinity(scope_ref=None, event_type="news", delta=-1,
                              source="explicit"),
            ],
        ))
        result = score_article_v2(_article(event_type="news"), profile)
        delta = _contribution(result, "event_affinity")
        assert delta["detail"] != "unknown_event_fallback"
        assert delta["source"] == "explicit"
