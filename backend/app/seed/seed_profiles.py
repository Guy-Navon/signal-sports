from app.models.profile import UserProfile, TopicPreference

SEED_PROFILES = [
    UserProfile(
        user_id="guy",
        display_name="Guy",
        language="he",
        profile_type="basketball_power_user",
        topics=[
            TopicPreference(
                topic_id="maccabi_tel_aviv_basketball",
                label="מכבי ת״א כדורסל",
                sport="basketball",
                scope="entity",
                priority=100,
                mode="all",
                leagues=["Israeli Basketball League", "EuroLeague"],
                entities=["Maccabi Tel Aviv Basketball", "Oded Katash"],
                event_rules={
                    "signing": "push",
                    "major_signing": "push",
                    "negotiation": "push",
                    "injury": "push",
                    "title_win": "push",
                    "candidate": "high_feed",
                    "rumor": "high_feed",
                    "playoff_result": "high_feed",
                    "match_result": "feed",
                    "match_summary": "feed",
                    "regular_season_result": "feed",
                    "interview": "feed",
                    "analysis": "feed",
                    "opinion": "feed",
                    "friendly_match": "low_feed",
                    "pre_match": "hidden",
                    "schedule": "hidden",
                    "generic_preview": "hidden",
                },
            ),
            TopicPreference(
                topic_id="nba",
                label="NBA",
                sport="basketball",
                scope="league",
                priority=90,
                mode="all",
                leagues=["NBA"],
                entities=["Deni Avdija"],
                entity_event_rules={
                    "Deni Avdija": {
                        "major_trade": "push",
                        "injury": "push",
                    }
                },
                event_rules={
                    "star_trade": "push",
                    "major_trade": "high_feed",
                    "title_win": "push",
                    "finals_result": "high_feed",
                    "playoff_result": "high_feed",
                    "injury": "feed",
                    "signing": "feed",
                    "major_signing": "high_feed",
                    "record": "high_feed",
                    "regular_season_result": "feed",
                    "match_result": "feed",
                    "match_summary": "feed",
                    "interview": "feed",
                    "analysis": "feed",
                    "generic_preview": "low_feed",
                    "schedule": "hidden",
                },
            ),
            TopicPreference(
                topic_id="euroleague",
                label="יורוליג",
                sport="basketball",
                scope="league",
                priority=95,
                mode="all",
                leagues=["EuroLeague", "EuroCup"],
                entities=["Maccabi Tel Aviv Basketball"],
                event_rules={
                    "signing": "high_feed",
                    "major_signing": "high_feed",
                    "negotiation": "high_feed",
                    "major_transfer": "high_feed",
                    "candidate": "feed",
                    "injury": "feed",
                    "match_result": "feed",
                    "match_summary": "feed",
                    "regular_season_result": "feed",
                    "playoff_result": "high_feed",
                    "final_four": "high_feed",
                    "title_win": "push",
                    "interview": "feed",
                    "analysis": "feed",
                    "opinion": "feed",
                    "generic_preview": "low_feed",
                    "schedule": "low_feed",
                },
            ),
            TopicPreference(
                topic_id="israeli_basketball",
                label="כדורסל ישראלי",
                sport="basketball",
                scope="league",
                priority=85,
                mode="all",
                leagues=["Israeli Basketball League"],
                entities=[],
                event_rules={
                    "signing": "feed",
                    "major_signing": "high_feed",
                    "negotiation": "feed",
                    "candidate": "feed",
                    "injury": "feed",
                    "match_result": "feed",
                    "regular_season_result": "feed",
                    "match_summary": "feed",
                    "playoff_result": "high_feed",
                    "title_win": "high_feed",
                    "interview": "feed",
                    "analysis": "feed",
                    "opinion": "feed",
                    "friendly_match": "low_feed",
                    "generic_preview": "low_feed",
                    "schedule": "hidden",
                },
            ),
            TopicPreference(
                topic_id="major_european_domestic_basketball",
                label="ליגות כדורסל בכירות באירופה",
                sport="basketball",
                scope="league_group",
                priority=65,
                mode="high_importance_only",
                leagues=["Spanish ACB", "Turkish BSL", "Greek Basket League", "Italian LBA", "French LNB"],
                entities=[],
                event_rules={
                    "major_match_result": "feed",
                    "playoff_result": "feed",
                    "title_win": "high_feed",
                    "major_signing": "feed",
                    "euroleague_related_transfer": "high_feed",
                    "regular_season_result": "hidden",
                    "generic_regular_season_result": "hidden",
                    "match_result": "hidden",
                    "generic_preview": "hidden",
                    "schedule": "hidden",
                },
            ),
            TopicPreference(
                # Single authoritative football policy (issue #29 profile-drift
                # fix): explicit low-interest sport scope gated to genuinely
                # major events, not a titles_only-with-empty-rules blanket hide
                # nor a major_only importance fallback (which leaked). Keep this
                # identical to frontend/src/data/userProfiles.js's football topic.
                topic_id="football",
                label="כדורגל",
                sport="football",
                scope="sport",
                priority=20,
                mode="titles_only",
                leagues=[],
                entities=[],
                event_rules={
                    "major_transfer": "low_feed",
                    "title_win": "low_feed",
                },
            ),
            TopicPreference(
                topic_id="tennis",
                label="טניס",
                sport="tennis",
                scope="sport",
                priority=25,
                mode="titles_only",
                leagues=[],
                entities=[],
                event_rules={
                    "grand_slam_winner": "high_feed",
                    "grand_slam_final": "feed",
                    "early_round_result": "hidden",
                    "generic_news": "hidden",
                    "match_result": "hidden",
                    "regular_season_result": "hidden",
                    "analysis": "hidden",
                    "schedule": "hidden",
                },
            ),
        ],
        muted_topics=[],
        muted_sources=[],
        followed_entities=["Maccabi Tel Aviv Basketball", "Deni Avdija", "Oded Katash"],
    ),
    UserProfile(
        user_id="casual_deni_fan",
        display_name="אוהד דני קז׳ואל",
        language="he",
        profile_type="casual_entity_follower",
        topics=[
            TopicPreference(
                topic_id="nba",
                label="NBA",
                sport="basketball",
                scope="league",
                priority=45,
                mode="followed_entities_only",
                leagues=["NBA"],
                entities=["Deni Avdija"],
                entity_event_rules={
                    "Deni Avdija": {
                        "major_trade": "push",
                        "injury": "push",
                        "regular_season_result": "high_feed",
                        "record": "high_feed",
                    }
                },
                event_rules={
                    "regular_season_result": "feed",
                    "match_result": "feed",
                    "match_summary": "feed",
                    "injury": "feed",
                    "major_trade": "feed",
                    "star_trade": "feed",
                    "finals_result": "feed",
                    "playoff_result": "feed",
                    "record": "feed",
                    "interview": "feed",
                    "analysis": "feed",
                    "generic_preview": "hidden",
                    "schedule": "hidden",
                    "signing": "hidden",
                    "followed_entity_news": "high_feed",
                },
            ),
        ],
        muted_topics=[],
        muted_sources=[],
        followed_entities=["Deni Avdija"],
    ),
]


def seed_profiles(db) -> None:
    for profile in SEED_PROFILES:
        db.profiles[profile.user_id] = profile


# ── ProfileV2 seeds (issue #32) ───────────────────────────────────────────────
# The same product semantics expressed as affinities + overrides. Legacy
# topics above stay authoritative until the shadow-validated engine flip;
# known deliberate divergences are documented in docs/PREFERENCE_MODEL_V2.md.

from app.models.profile_v2 import (  # noqa: E402
    EventAffinity,
    OverrideRule,
    ProfileV2,
    ScopeAffinity,
)


def _ev(scope_ref, event_type, delta):
    return EventAffinity(scope_ref=scope_ref, event_type=event_type, delta=delta)


GUY_PROFILE_V2 = ProfileV2(
    scope_affinities=[
        # Maccabi Tel Aviv basketball — the very-high core follow.
        ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
        # Broad competition follows.
        ScopeAffinity(scope="competition", target_id="comp:euroleague", level=1),
        ScopeAffinity(scope="competition", target_id="comp:eurocup", level=1),
        ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
        ScopeAffinity(scope="competition", target_id="comp:ibl", level=1),
        # Secondary European domestic leagues — selective (low).
        ScopeAffinity(scope="competition", target_id="comp:acb", level=-1),
        ScopeAffinity(scope="competition", target_id="comp:bsl", level=-1),
        ScopeAffinity(scope="competition", target_id="comp:greek_basket", level=-1),
        ScopeAffinity(scope="competition", target_id="comp:lba", level=-1),
        ScopeAffinity(scope="competition", target_id="comp:lnb", level=-1),
        # Low-interest sports — visible only through event affinities.
        ScopeAffinity(scope="sport", target_id="football", level=-1),
        ScopeAffinity(scope="sport", target_id="tennis", level=-1),
        # Followed people.
        ScopeAffinity(scope="player", target_id="player:deni_avdija", level=1),
        ScopeAffinity(scope="player", target_id="coach:oded_kattash", level=1),
    ],
    event_affinities=[
        # NBA (base 2 = feed): elevated and demoted events.
        _ev("comp:nba", "finals_result", 1),
        _ev("comp:nba", "playoff_result", 1),
        _ev("comp:nba", "major_trade", 1),
        _ev("comp:nba", "major_signing", 1),
        _ev("comp:nba", "record", 1),
        _ev("comp:nba", "generic_preview", -1),
        _ev("comp:nba", "schedule", -2),
        # EuroLeague / EuroCup (base 2 = feed).
        _ev("comp:euroleague", "signing", 1),
        _ev("comp:euroleague", "major_signing", 1),
        _ev("comp:euroleague", "negotiation", 1),
        _ev("comp:euroleague", "major_transfer", 1),
        _ev("comp:euroleague", "playoff_result", 1),
        _ev("comp:euroleague", "final_four", 1),
        _ev("comp:euroleague", "generic_preview", -1),
        _ev("comp:euroleague", "schedule", -1),
        _ev("comp:eurocup", "signing", 1),
        _ev("comp:eurocup", "major_signing", 1),
        _ev("comp:eurocup", "negotiation", 1),
        _ev("comp:eurocup", "major_transfer", 1),
        _ev("comp:eurocup", "playoff_result", 1),
        _ev("comp:eurocup", "final_four", 1),
        _ev("comp:eurocup", "generic_preview", -1),
        _ev("comp:eurocup", "schedule", -1),
        # Israeli Basketball League (base 2 = feed).
        _ev("comp:ibl", "major_signing", 1),
        _ev("comp:ibl", "playoff_result", 1),
        _ev("comp:ibl", "title_win", 1),
        _ev("comp:ibl", "friendly_match", -1),
        _ev("comp:ibl", "generic_preview", -1),
        _ev("comp:ibl", "schedule", -2),
        # Maccabi (base 3 = high_feed): routine events step down to feed;
        # transfer-cycle events keep the high base; pushes are overrides.
        _ev("team:maccabi_tlv_bb", "news", -1),
        _ev("team:maccabi_tlv_bb", "match_result", -1),
        _ev("team:maccabi_tlv_bb", "match_summary", -1),
        _ev("team:maccabi_tlv_bb", "regular_season_result", -1),
        _ev("team:maccabi_tlv_bb", "interview", -1),
        _ev("team:maccabi_tlv_bb", "analysis", -1),
        _ev("team:maccabi_tlv_bb", "opinion", -1),
        _ev("team:maccabi_tlv_bb", "friendly_match", -2),
        # Secondary European leagues (base 0): only genuinely major events.
        _ev("comp:acb", "title_win", 2),
        _ev("comp:acb", "major_match_result", 2),
        _ev("comp:acb", "playoff_result", 2),
        _ev("comp:acb", "major_signing", 2),
        _ev("comp:bsl", "title_win", 2),
        _ev("comp:bsl", "major_match_result", 2),
        _ev("comp:bsl", "playoff_result", 2),
        _ev("comp:bsl", "major_signing", 2),
        _ev("comp:greek_basket", "title_win", 2),
        _ev("comp:greek_basket", "major_match_result", 2),
        _ev("comp:greek_basket", "playoff_result", 2),
        _ev("comp:greek_basket", "major_signing", 2),
        _ev("comp:lba", "title_win", 2),
        _ev("comp:lba", "major_match_result", 2),
        _ev("comp:lba", "playoff_result", 2),
        _ev("comp:lba", "major_signing", 2),
        _ev("comp:lnb", "title_win", 2),
        _ev("comp:lnb", "major_match_result", 2),
        _ev("comp:lnb", "playoff_result", 2),
        _ev("comp:lnb", "major_signing", 2),
        # Football (base 0): only huge stories surface, as low_feed.
        _ev("football", "major_transfer", 1),
        _ev("football", "title_win", 1),
        # Tennis (base 0): Grand Slam finals/winners only.
        _ev("tennis", "grand_slam_winner", 2),
        _ev("tennis", "grand_slam_final", 2),
    ],
    overrides=[
        # Push — explicit and rare (the only push path in v2).
        OverrideRule(kind="always_push", scope="team", target_id="team:maccabi_tlv_bb",
                     event_type="signing"),
        OverrideRule(kind="always_push", scope="team", target_id="team:maccabi_tlv_bb",
                     event_type="major_signing"),
        OverrideRule(kind="always_push", scope="team", target_id="team:maccabi_tlv_bb",
                     event_type="negotiation"),
        OverrideRule(kind="always_push", scope="team", target_id="team:maccabi_tlv_bb",
                     event_type="injury"),
        OverrideRule(kind="always_push", scope="team", target_id="team:maccabi_tlv_bb",
                     event_type="title_win"),
        OverrideRule(kind="always_push", scope="competition", target_id="comp:nba",
                     event_type="star_trade"),
        OverrideRule(kind="always_push", scope="competition", target_id="comp:nba",
                     event_type="title_win"),
        OverrideRule(kind="always_push", scope="competition", target_id="comp:euroleague",
                     event_type="title_win"),
        OverrideRule(kind="always_push", scope="competition", target_id="comp:eurocup",
                     event_type="title_win"),
        OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija",
                     event_type="major_trade"),
        OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija",
                     event_type="injury"),
        # Maccabi noise events stay hidden even at a very-high base.
        OverrideRule(kind="never_show", scope="team", target_id="team:maccabi_tlv_bb",
                     event_type="pre_match"),
        OverrideRule(kind="never_show", scope="team", target_id="team:maccabi_tlv_bb",
                     event_type="schedule"),
        OverrideRule(kind="never_show", scope="team", target_id="team:maccabi_tlv_bb",
                     event_type="generic_preview"),
    ],
)


DENI_FAN_PROFILE_V2 = ProfileV2(
    scope_affinities=[
        # The one thing this user cares about.
        ScopeAffinity(scope="player", target_id="player:deni_avdija", level=2),
    ],
    event_affinities=[
        # Routine Deni coverage steps down from the very-high base to feed.
        _ev("player:deni_avdija", "interview", -1),
        _ev("player:deni_avdija", "analysis", -1),
        _ev("player:deni_avdija", "match_summary", -1),
        _ev("player:deni_avdija", "match_result", -1),
    ],
    overrides=[
        OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija",
                     event_type="major_trade"),
        OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija",
                     event_type="injury"),
        OverrideRule(kind="never_show", scope="player", target_id="player:deni_avdija",
                     event_type="generic_preview"),
        OverrideRule(kind="never_show", scope="player", target_id="player:deni_avdija",
                     event_type="schedule"),
    ],
)


PROFILE_V2_SEEDS = {
    "guy": GUY_PROFILE_V2,
    "casual_deni_fan": DENI_FAN_PROFILE_V2,
}

# Attach v2 payloads to the seed profiles (fresh DBs get both models at once).
for _p in SEED_PROFILES:
    _p.profile_v2 = PROFILE_V2_SEEDS.get(_p.user_id)
