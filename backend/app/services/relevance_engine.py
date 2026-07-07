"""
Backend relevance engine — faithful Python port of src/engine/relevanceEngine.js

Scoring pipeline (mirrors frontend):
1. Check disabled sources
2. Check muted sources
3. Check muted topics (by sport/league)
4. Find matching topics from profile
5. Score article against each matching topic; take best decision
6. Return DecisionResult with full reasoning chain

Push philosophy: push NEVER auto-escalates from importance boost.
Push requires an explicit eventRules or entityEventRules declaration.
"""
from typing import Optional, Set

from app.models.article import Article
from app.models.profile import UserProfile, TopicPreference
from app.models.scoring import DecisionResult
from app.taxonomy import COMPETITIONS, entity_by_id, entity_by_legacy_name

# Event-reach allowlists (issue #29) — explicit and fail-closed. An event type
# in neither set gets no membership-derived reach at all: it can still match a
# league/league_group topic via explicit competition evidence (or the legacy
# pre-ArticleFacts fallback), just never via "the team also plays in X".
# `interview` is deliberately in neither set — a generic interview shouldn't
# spread through every competition a team belongs to.
TEAM_ANCHORED_EVENTS = frozenset({
    "signing", "major_signing", "negotiation", "candidate", "release",
    "injury", "major_trade", "star_trade", "major_transfer",
})
COMPETITION_ANCHORED_EVENTS = frozenset({
    "match_result", "regular_season_result", "playoff_result", "finals_result",
    "title_win", "schedule", "pre_match", "generic_preview",
    "generic_regular_season_result", "friendly_match", "final_four",
    "major_match_result", "match_summary",
})

# Participant-set competition inference (issue #40 Part B) applies to
# competition-anchored events EXCEPT these: a friendly between two clubs that
# share a competition is, by definition, not a game in that competition — the
# shared-membership premise ("the event happened in exactly one competition
# both participants belong to") does not hold for it.
PARTICIPANT_INFERENCE_EXCLUDED_EVENTS = frozenset({"friendly_match"})

DECISION_RANK = {
    "hidden": 0,
    "low_feed": 1,
    "feed": 2,
    "high_feed": 3,
    "push": 4,
}

DECISION_LABELS = {
    "hidden": "מוסתר",
    "low_feed": "נמוך",
    "feed": "רגיל",
    "high_feed": "חשוב",
    "push": "דורש תשומת לב",
}

# Canonical event type aliases — mirrors the JS ENGINE_ALIASES map
_EVENT_ALIASES: dict[str, list[str]] = {
    "regular_season_result": ["match_result"],
    "match_result": ["regular_season_result"],
    "major_signing": ["signing"],
    "signing": ["major_signing"],
    "major_trade": ["star_trade"],
    "star_trade": ["major_trade"],
    "major_transfer": ["major_signing", "major_trade"],
    "match_summary": ["match_result", "regular_season_result"],
}


# ── Public API ─────────────────────────────────────────────────────────────────

def score_article(
    article: Article,
    profile: UserProfile,
    disabled_source_ids: Optional[Set[str]] = None,
) -> DecisionResult:
    if disabled_source_ids is None:
        disabled_source_ids = set()

    reasoning: list[str] = []
    reasoning.append(f"פרופיל: {profile.display_name}")

    # Step 1a: globally disabled source
    if article.source in disabled_source_ids:
        reasoning.append(f"מקור כבוי (Sources page): {article.source}")
        return _build_result("hidden", reasoning, None, "disabled_source")

    # Step 1b: profile-muted source
    if article.source in (profile.muted_sources or []):
        reasoning.append(f"מקור מושתק: {article.source}")
        return _build_result("hidden", reasoning, None, "muted_source")

    # Step 2: muted topics (by sport or league)
    if profile.muted_topics:
        article_topic_ids = _get_article_topic_ids(article)
        muted = next((t for t in article_topic_ids if t in profile.muted_topics), None)
        if muted:
            reasoning.append(f"נושא מושתק: {muted}")
            return _build_result("hidden", reasoning, None, "muted_topic")

    # Step 3: find matching profile topics
    matching_topics = _find_matching_topics(article, profile)
    if not matching_topics:
        reasoning.append(f"ספורט: {article.sport}, ליגה: {article.league or '—'}")
        reasoning.append("לא נמצאה התאמה לאף נושא בפרופיל")
        reasoning.append("החלטה סופית: מוסתר")
        return _build_result("hidden", reasoning, None, "no_matching_topic")

    # Step 4: score against each matching topic; take best decision
    best_decision = "hidden"
    best_topic_id: Optional[str] = None
    best_rule: Optional[str] = None
    best_topic_reasoning: list[str] = []

    for topic, match_reason, match_kind in matching_topics:
        t_decision, t_rule, t_reasoning = _score_against_topic(article, topic, profile, match_reason)
        if match_kind == "membership" and DECISION_RANK[t_decision] > DECISION_RANK["feed"]:
            # Membership-derived reach with no independent entity backing is one
            # tier below explicit/legacy evidence — it can justify feed visibility
            # but never high_feed/push on its own (issue #29).
            # NOTE: "participant_inference" (issue #40) is deliberately NOT
            # capped here — a unique participant intersection is genuine
            # event-competition evidence, not diffuse reach. Push discipline is
            # unaffected: push still requires an explicit rule (boosts cap at
            # high_feed).
            if not _topic_entity_match(article, topic, profile):
                t_reasoning.append(
                    f"התאמה מבוססת שיוך קבוצתי בלבד (ללא ישות עוקבת) → תקרה: "
                    f"{DECISION_LABELS['feed']} (היה {DECISION_LABELS[t_decision]})"
                )
                t_decision = "feed"
        if DECISION_RANK[t_decision] > DECISION_RANK[best_decision]:
            best_decision = t_decision
            best_topic_id = topic.topic_id
            best_rule = t_rule
            best_topic_reasoning = t_reasoning

    reasoning.extend(best_topic_reasoning)
    reasoning.append(f"החלטה סופית: {DECISION_LABELS[best_decision]}")

    return _build_result(best_decision, reasoning, best_topic_id, best_rule)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _score_against_topic(
    article: Article,
    topic: TopicPreference,
    profile: UserProfile,
    match_reason: Optional[str] = None,
) -> tuple[str, Optional[str], list[str]]:
    r: list[str] = []
    r.append(f'נושא: "{topic.label}" (עדיפות: {topic.priority}, מצב: {topic.mode})')
    if match_reason:
        r.append(match_reason)

    if topic.mode == "muted":
        r.append("נושא מושתק → מוסתר")
        return ("hidden", "topic_muted", r)

    if topic.mode == "followed_entities_only":
        return _score_followed_entities_only(article, topic, profile, r)

    if topic.mode == "titles_only":
        event_decision = _get_event_decision(article.event_type, topic.event_rules)
        if not event_decision or event_decision == "hidden":
            r.append(f"מצב titles_only — אירוע: {article.event_type} → מוסתר")
            return ("hidden", "titles_only_no_match", r)
        r.append(f"מצב titles_only — אירוע: {article.event_type} → {DECISION_LABELS[event_decision]}")
        return (event_decision, f"event:{article.event_type}", r)

    if topic.mode == "high_importance_only":
        if article.importance in ("low", "very_low"):
            r.append(f"מצב high_importance_only — חשיבות: {article.importance} → מוסתר")
            return ("hidden", "low_importance", r)
        r.append(f"מצב high_importance_only — חשיבות: {article.importance} (עובר)")
        event_decision = _get_event_decision(article.event_type, topic.event_rules)
        if event_decision and event_decision != "hidden":
            r.append(f"כלל אירוע: {article.event_type} → {DECISION_LABELS[event_decision]}")
            return (event_decision, f"event:{article.event_type}", r)
        fallback = _importance_fallback(article.importance, topic.priority, r)
        return (fallback, "importance_fallback", r)

    if topic.mode == "major_only":
        # The importance-based `major_importance_fallback` → low_feed leak was
        # removed (issue #29): a high-importance article with no matching event
        # rule is not a "real matched scope", so it's hidden like titles_only,
        # not surfaced as low_feed. This makes major_only behaviorally identical
        # to titles_only; the mode is kept only for backward-compat with any
        # already-persisted profile referencing it.
        event_decision = _get_event_decision(article.event_type, topic.event_rules)
        if event_decision and event_decision != "hidden":
            r.append(f"מצב major_only — כלל אירוע: {article.event_type} → {DECISION_LABELS[event_decision]}")
            return (event_decision, f"event:{article.event_type}", r)
        r.append(f"מצב major_only — אין כלל אירוע תואם ({article.event_type}) → מוסתר")
        return ("hidden", "major_only_no_match", r)

    # Default: all
    return _score_all_mode(article, topic, profile, r)


def _score_followed_entities_only(
    article: Article,
    topic: TopicPreference,
    profile: UserProfile,
    r: list[str],
) -> tuple[str, Optional[str], list[str]]:
    article_entities = article.entities or []
    relevant_entities = list({
        *(topic.entities or []),
        *(profile.followed_entities or []),
    })

    entity_match = _topic_entity_match(article, topic, profile)

    if not entity_match:
        r.append("מצב followed_entities_only")
        r.append(f"ישויות במאמר: {', '.join(article_entities) or 'אין'}")
        r.append(f"ישויות מעקב: {', '.join(relevant_entities)}")
        r.append("לא נמצאה ישות תואמת → מוסתר")
        return ("hidden", "entity_not_followed", r)

    r.append(f"ישות תואמת: {entity_match}")

    # Entity-specific rule takes precedence
    entity_rules = (topic.entity_event_rules or {}).get(entity_match)
    entity_event_rule = _get_event_decision(article.event_type, entity_rules)
    if entity_event_rule is not None:
        r.append(f"כלל ספציפי לישות ({entity_match}): {article.event_type} → {DECISION_LABELS[entity_event_rule]}")
        if entity_event_rule == "hidden":
            return ("hidden", f"entity_event:{article.event_type}", r)
        boosted = _apply_importance_boost(entity_event_rule, article.importance, r)
        return (boosted, f"entity_event:{article.event_type}", r)

    # Generic event rule
    event_decision = _get_event_decision(article.event_type, topic.event_rules)
    if event_decision and event_decision != "hidden":
        r.append(f"כלל אירוע: {article.event_type} → {DECISION_LABELS[event_decision]}")
        return (event_decision, f"event:{article.event_type}", r)

    # Catch-all for followed entity news
    catch_all = (topic.event_rules or {}).get("followed_entity_news")
    if catch_all and catch_all != "hidden":
        r.append(f"ישות תואמת ({entity_match}) + catch-all → {DECISION_LABELS[catch_all]}")
        return (catch_all, "entity_news_catchall", r)

    r.append(f"ישות תואמת ({entity_match}), אין כלל ספציפי → feed")
    return ("feed", "entity_match_default", r)


def _score_all_mode(
    article: Article,
    topic: TopicPreference,
    profile: UserProfile,
    r: list[str],
) -> tuple[str, Optional[str], list[str]]:
    topic_entities = topic.entities or []

    entity_match = _topic_entity_match(article, topic, profile)

    if entity_match:
        r.append(f"ישות תואמת: {entity_match}")

    # Entity-specific event rule override
    if entity_match:
        entity_rules = (topic.entity_event_rules or {}).get(entity_match)
        entity_event_rule = _get_event_decision(article.event_type, entity_rules)
        if entity_event_rule is not None:
            r.append(f"כלל ספציפי לישות ({entity_match}): {article.event_type} → {DECISION_LABELS[entity_event_rule]}")
            if entity_event_rule == "hidden":
                return ("hidden", f"entity_event:{article.event_type}", r)
            boosted = _apply_importance_boost(entity_event_rule, article.importance, r)
            return (boosted, f"entity_event:{article.event_type}", r)

    # Generic event rule
    event_decision = _get_event_decision(article.event_type, topic.event_rules)

    if event_decision is not None:
        if event_decision == "hidden":
            r.append(f"כלל אירוע: {article.event_type} → מוסתר")
            return ("hidden", f"event:{article.event_type}", r)

        r.append(f"כלל אירוע: {article.event_type} → {DECISION_LABELS[event_decision]}")

        # Entity boost: only for primary topic entities (not just followedEntities), only feed→high_feed
        if entity_match and entity_match in topic_entities:
            boosted = _apply_entity_boost(event_decision, r)
            if boosted != event_decision:
                return (boosted, f"event:{article.event_type}+entity_boost", r)

        boosted = _apply_importance_boost(event_decision, article.importance, r)
        return (boosted, f"event:{article.event_type}", r)

    # No event rule — importance + priority fallback
    r.append(f"אין כלל עבור אירוע: {article.event_type}")
    fallback = _importance_fallback(article.importance, topic.priority, r)
    return (fallback, "importance_fallback", r)


def _get_event_decision(event_type: str, event_rules: Optional[dict]) -> Optional[str]:
    if not event_rules:
        return None
    if event_type in event_rules:
        return event_rules[event_type]
    for alias in _EVENT_ALIASES.get(event_type, []):
        if alias in event_rules:
            return event_rules[alias]
    return None


def _apply_entity_boost(decision: str, r: list[str]) -> str:
    if decision == "feed":
        r.append("ישות ראשית תואמת → שדרוג: feed → high_feed")
        return "high_feed"
    return decision


def _apply_importance_boost(decision: str, importance: str, r: list[str]) -> str:
    HIGH_FEED_RANK = 3  # hard cap — never auto-boost to push (rank 4)
    if importance == "very_high" and DECISION_RANK[decision] > 0:
        current_rank = DECISION_RANK[decision]
        target_rank = min(current_rank + 1, HIGH_FEED_RANK)
        if target_rank > current_rank:
            ranks = ["hidden", "low_feed", "feed", "high_feed", "push"]
            boosted = ranks[target_rank]
            r.append(
                f"חשיבות מאוד גבוהה → שדרוג: {DECISION_LABELS[decision]} → "
                f"{DECISION_LABELS[boosted]} (push דורש הגדרה מפורשת)"
            )
            return boosted
    return decision


def _importance_fallback(importance: str, topic_priority: int, r: list[str]) -> str:
    if importance == "very_high" and topic_priority >= 80:
        decision = "high_feed"
    elif importance == "high" and topic_priority >= 80:
        decision = "feed"
    elif importance == "medium" and topic_priority >= 70:
        decision = "feed"
    elif importance == "high":
        decision = "feed"
    elif importance == "medium":
        decision = "low_feed"
    elif importance == "low" and topic_priority >= 70:
        decision = "low_feed"
    else:
        decision = "hidden"  # very_low, or low with low-priority topic

    r.append(f"גיבוי לפי חשיבות ({importance}) + עדיפות ({topic_priority}) → {DECISION_LABELS[decision]}")
    return decision


def _explicit_competition_names(article: Article) -> set[str]:
    """Display names of the article's explicitly-evidenced competitions (#28) —
    primary_competition + article_competitions. Never includes membership-only
    reach; that is computed separately in `_entity_reach`."""
    comp_ids = list(article.article_competitions or [])
    if article.primary_competition:
        comp_ids = [article.primary_competition] + comp_ids
    return {COMPETITIONS[c].display_en for c in comp_ids if c in COMPETITIONS}


def _entity_reach(article: Article) -> dict[str, str]:
    """Competition display name -> comp id, via the article's resolved
    entities' taxonomy memberships (issue #29).

    Identity source is tiered, matching the entity_ids-first contract:
      - post-ArticleFacts rows (taxonomy_version is not None): resolve
        *only* through the canonical `entity_ids` — the authoritative,
        rename-proof path.
      - legacy rows (taxonomy_version is None, entity_ids never populated):
        fall back to the legacy `entities` display strings, compatibility
        path only.
    """
    reach: dict[str, str] = {}

    def _add(ent) -> None:
        if ent is None:
            return
        for comp_id, _season in ent.memberships:
            comp = COMPETITIONS.get(comp_id)
            if comp:
                reach.setdefault(comp.display_en, comp_id)

    if article.taxonomy_version is not None:
        for entity_id in article.entity_ids or []:
            _add(entity_by_id(entity_id))
    else:
        for legacy_name in article.entities or []:
            _add(entity_by_legacy_name(legacy_name))

    return reach


def _participant_teams(article: Article) -> list:
    """The article's resolved TEAM entities — the participant candidates for
    competition inference (issue #40 Part B).

    Identity is tiered identically to `_entity_reach`: post-ArticleFacts rows
    resolve only through canonical `entity_ids`; legacy rows fall back to the
    `entities` display strings. Players and coaches are never participants —
    a player mention plus his own team must not become a two-participant set.
    """
    teams: dict[str, object] = {}
    if article.taxonomy_version is not None:
        for entity_id in article.entity_ids or []:
            ent = entity_by_id(entity_id)
            if ent is not None and ent.kind == "team":
                teams[ent.id] = ent
    else:
        for legacy_name in article.entities or []:
            ent = entity_by_legacy_name(legacy_name)
            if ent is not None and ent.kind == "team":
                teams[ent.id] = ent
    return list(teams.values())


def _participant_inferred_competition(article: Article) -> Optional[str]:
    """Unique shared competition of the article's participating teams, or None.

    The inference contract (issue #40 Part B):
    - at least two resolved team entities (fewer → abstain);
    - intersect ALL participating teams' competition memberships — an
      incidental extra team can only shrink the intersection, so it can force
      abstention but never redirect the inference (fail-closed by shape);
    - accept only a singleton intersection; empty or >1 (e.g. two Israeli
      EuroLeague clubs sharing {IBL, EuroLeague}) → abstain.

    Relevance-time only: the inferred id is never persisted into
    `primary_competition`/`article_competitions` (explicit article evidence
    only, #28) — it exists in the scoring trace alone.
    """
    teams = _participant_teams(article)
    if len(teams) < 2:
        return None
    shared: Optional[set[str]] = None
    for team in teams:
        memberships = {comp_id for comp_id, _season in team.memberships}
        shared = memberships if shared is None else (shared & memberships)
        if not shared:
            return None
    return next(iter(shared)) if shared is not None and len(shared) == 1 else None


def _topic_entity_match(
    article: Article, topic: TopicPreference, profile: UserProfile
) -> Optional[str]:
    """The article entity (returned as its legacy display name, for
    `entity_event_rules` dict lookups) that backs this topic for this
    profile, or None.

    Tiered identically to `_entity_reach`: post-ArticleFacts rows compare
    canonical ids (topic/profile entity names — still legacy strings in
    today's profile schema — resolved to ids, checked against the article's
    canonical `entity_ids`), so a renamed/missing legacy display string on a
    post-facts row does not break entity backing. Legacy rows compare
    display strings directly, exactly as before.
    """
    if article.taxonomy_version is not None:
        relevant_ids: set[str] = set()
        for name in (*(topic.entities or []), *(profile.followed_entities or [])):
            ent = entity_by_legacy_name(name)
            if ent:
                relevant_ids.add(ent.id)
        hit_id = next((eid for eid in (article.entity_ids or []) if eid in relevant_ids), None)
        if hit_id is None:
            return None
        ent = entity_by_id(hit_id)
        return ent.legacy_name if ent else hit_id

    article_entities = article.entities or []
    relevant = {*(topic.entities or []), *(profile.followed_entities or [])}
    return next((e for e in article_entities if e in relevant), None)


def _does_topic_match_article(
    article: Article, topic: TopicPreference
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Scope-aware topic matching. Returns (matched, match_reason, match_kind).

    match_kind is one of "explicit", "legacy", "participant_inference",
    "membership", or None (not applicable — entity/sport scopes, or no match).
    It drives the membership-reach feed ceiling applied in `score_article`
    (which applies to "membership" only).

    Scope semantics (mirrors frontend doesTopicMatchArticle):
      "entity"       — match only if article.entities ∩ topic.entities is non-empty.
      "league"       — four-tier competition-aware match (issues #29 + #40):
                       explicit evidence, legacy fallback, participant-set
                       inference, or team-membership reach.
      "league_group" — same three-tier match as "league".
      "sport"        — match only if article.sport == topic.sport.
      None           — legacy OR matching: sport OR league OR entity.
    """
    scope = topic.scope

    if scope is None:
        # Legacy OR matching for topics without an explicit scope
        if topic.sport and article.sport == topic.sport:
            return (True, f"התאמה לפי ספורט: {article.sport}", None)
        if topic.leagues and article.league and article.league in topic.leagues:
            return (True, f"התאמה לפי ליגה: {article.league}", None)
        if topic.entities and article.entities:
            hit = next((e for e in article.entities if e in topic.entities), None)
            if hit:
                return (True, f"התאמה לפי ישות: {hit}", None)
        return (False, None, None)

    if scope == "entity":
        if topic.entities and article.entities:
            hit = next((e for e in article.entities if e in topic.entities), None)
            if hit:
                # Sport compatibility guard: a basketball entity topic must not match a
                # football/tennis article even if entities overlap due to classification error.
                # "unknown" sport passes through — the article may simply be unclassified.
                if topic.sport and article.sport != "unknown" and article.sport != topic.sport:
                    return (False, None, None)
                return (True, f"התאמה לפי ישות (scope: entity): {hit}", None)
        return (False, None, None)

    if scope in ("league", "league_group"):
        if not topic.leagues:
            return (False, None, None)

        # 1. Explicit competition evidence — works for any event type.
        explicit_names = _explicit_competition_names(article)
        hit = next((name for name in topic.leagues if name in explicit_names), None)
        if hit:
            return (True, f"התאמה לפי תחרות מפורשת (scope: {scope}): {hit}", "explicit")

        # 2. Legacy fallback — only for rows that predate ArticleFacts, where
        # the explicit/membership distinction was never persisted.
        if article.taxonomy_version is None and article.league and article.league in topic.leagues:
            return (True, f"התאמה לפי ליגה (scope: {scope}): {article.league}", "legacy")

        # 3. Participant-set competition inference (issue #40 Part B) —
        # competition-anchored events only. When ALL participating teams share
        # exactly one competition, that intersection identifies the event's
        # competition. This is event-competition evidence (not diffuse team
        # reach), so it is NOT subject to the membership feed ceiling — but it
        # is still lower authority than explicit evidence (tier 1 wins above).
        if (
            article.event_type in COMPETITION_ANCHORED_EVENTS
            and article.event_type not in PARTICIPANT_INFERENCE_EXCLUDED_EVENTS
        ):
            comp_id = _participant_inferred_competition(article)
            if comp_id is not None:
                comp = COMPETITIONS.get(comp_id)
                if comp and comp.display_en in topic.leagues:
                    return (
                        True,
                        f"התאמה דרך הסקת משתתפים (via_participant_inference: {comp_id}) "
                        f"(scope: {scope}): {comp.display_en}",
                        "participant_inference",
                    )

        # 4. Membership-derived reach — team-anchored events only (allowlist).
        if article.event_type in TEAM_ANCHORED_EVENTS:
            reach = _entity_reach(article)
            hit = next((name for name in topic.leagues if name in reach), None)
            if hit:
                comp_id = reach[hit]
                return (
                    True,
                    f"התאמה דרך שיוך קבוצתי (via_team_membership: {comp_id}) (scope: {scope}): {hit}",
                    "membership",
                )

        return (False, None, None)

    if scope == "sport":
        if topic.sport and article.sport == topic.sport:
            return (True, f"התאמה לפי ספורט (scope: sport): {article.sport}", None)
        return (False, None, None)

    return (False, None, None)


def _find_matching_topics(
    article: Article,
    profile: UserProfile,
) -> list[tuple[TopicPreference, Optional[str], Optional[str]]]:
    """Return list of (topic, match_reason, match_kind) sorted by priority descending."""
    matched = []
    for topic in profile.topics:
        is_match, reason, match_kind = _does_topic_match_article(article, topic)
        if is_match:
            matched.append((topic, reason, match_kind))
    matched.sort(key=lambda t: t[0].priority, reverse=True)
    return matched


def _get_article_topic_ids(article: Article) -> list[str]:
    ids = []
    if article.sport:
        ids.append(article.sport)
    if article.league:
        ids.append(article.league)
    return ids


def _build_result(
    decision: str,
    reasoning: list[str],
    matched_topic: Optional[str],
    matched_rule: Optional[str],
) -> DecisionResult:
    return DecisionResult(
        decision=decision,
        matched_topic=matched_topic,
        matched_entities=[],
        matched_event_rule=matched_rule,
        reasoning=reasoning,
    )
