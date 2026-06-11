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

    for topic in matching_topics:
        t_decision, t_rule, t_reasoning = _score_against_topic(article, topic, profile)
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
) -> tuple[str, Optional[str], list[str]]:
    r: list[str] = []
    r.append(f'נושא: "{topic.label}" (עדיפות: {topic.priority}, מצב: {topic.mode})')

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
        major_importance = {"high", "very_high"}
        event_decision = _get_event_decision(article.event_type, topic.event_rules)
        if article.importance not in major_importance and (not event_decision or event_decision == "hidden"):
            r.append(f"מצב major_only — חשיבות: {article.importance}, אירוע: {article.event_type} → מוסתר")
            return ("hidden", "major_only_no_match", r)
        if event_decision and event_decision != "hidden":
            r.append(f"מצב major_only — כלל אירוע: {article.event_type} → {DECISION_LABELS[event_decision]}")
            return (event_decision, f"event:{article.event_type}", r)
        if article.importance in major_importance:
            r.append("מצב major_only — חשיבות גבוהה ללא כלל ספציפי → low_feed")
            return ("low_feed", "major_importance_fallback", r)
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

    entity_match = next((e for e in article_entities if e in relevant_entities), None)

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
    article_entities = article.entities or []
    topic_entities = topic.entities or []
    profile_entities = profile.followed_entities or []

    entity_match = next(
        (e for e in article_entities if e in topic_entities or e in profile_entities),
        None,
    )

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


def _find_matching_topics(
    article: Article,
    profile: UserProfile,
) -> list[TopicPreference]:
    matched = []
    for topic in profile.topics:
        matches = False
        if topic.sport and article.sport == topic.sport:
            matches = True
        if topic.leagues and article.league and article.league in topic.leagues:
            matches = True
        if topic.entities and article.entities:
            if any(e in topic.entities for e in article.entities):
                matches = True
        if matches:
            matched.append(topic)
    # highest priority first
    matched.sort(key=lambda t: t.priority, reverse=True)
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
