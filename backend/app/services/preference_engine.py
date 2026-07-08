"""
Preference Model V2 — layered affinity scorer (issue #32).

Scoring pipeline (monotonic by construction):

1. Hard constraints — disabled/muted sources, legacy muted_topics,
   mute / never_show overrides. Absolute; nothing below can resurrect.
2. Base visibility — best matching followed scope. Matching NEVER re-derives
   visibility: competition scopes go through
   `relevance_engine.match_competition_names()` (the four-tier #29/#40
   machinery, same match_kind vocabulary), team/player scopes through the
   entity_ids-first identity contract, sport scopes through article.sport.
   Base points come from the affinity level; the *max* points across matched
   scopes wins (so adding an affinity can never lower a decision), with
   specificity (team/player > competition > sport) breaking ties for the
   trace. An `exclude` (-2) affinity hides the article unless a strictly
   more specific matched affinity is non-exclude.
3. Entity boost — +1 when base came from a broader scope (competition/sport)
   and a followed (level ≥ +1) team/player is present on the article.
4. Event affinity delta — the scoped entry for (base scope, event_type) if
   one exists, else the global entry; event aliases are honored.
5. Importance interaction — very_high +1, low/very_low −1.
6. Membership ceiling — a base that matched via diffuse membership reach
   (match_kind == "membership") with no followed-entity backing is capped at
   feed, exactly like the legacy engine (#29). Participant-inferred and
   explicit matches are never capped.
7. Threshold mapping — score ≤0 hidden, 1 low_feed, 2 feed, ≥3 high_feed.
   **Push exists ONLY via explicit always_push overrides** (step 8) — no
   boost, delta, or importance combination can reach push.
8. always_push overrides — fire when the override's target matches the
   article (same matching primitives) and the article was not hidden by a
   hard constraint or exclude.

Every step emits a structured contribution {step, scope, effect, detail} —
the source for the human-readable reasoning chain, Preferences display, and
Debug. Python-only: the JS engine is frozen and receives no port (#32).
"""
from typing import List, Optional, Set

from app.models.article import Article
from app.models.profile import UserProfile
from app.models.profile_v2 import (
    AFFINITY_LEVEL_NAMES,
    EventAffinity,
    OverrideRule,
    ProfileV2,
    ScopeAffinity,
)
from app.models.scoring import DecisionResult
from app.services.relevance_engine import (
    DECISION_LABELS,
    _EVENT_ALIASES,
    match_competition_names,
)
from app.taxonomy import COMPETITIONS, entity_by_id

# Scope specificity: team/player beat competition beat sport.
_SPECIFICITY = {"team": 3, "player": 3, "competition": 2, "sport": 1}

# Affinity level → base points. exclude (-2) is handled before this table.
_LEVEL_POINTS = {2: 3, 1: 2, 0: 1, -1: 0}

_THRESHOLDS = ["hidden", "low_feed", "feed", "high_feed"]  # index = clamped score


def _threshold(score: int) -> str:
    return _THRESHOLDS[max(0, min(score, 3))]


class _ScopeMatch:
    def __init__(self, affinity: ScopeAffinity, match_kind: Optional[str], detail: str):
        self.affinity = affinity
        self.match_kind = match_kind          # competition scopes only
        self.detail = detail
        self.points = _LEVEL_POINTS.get(affinity.level, 0)
        self.specificity = _SPECIFICITY[affinity.scope]


def _entity_on_article(article: Article, taxonomy_id: str) -> bool:
    """entity_ids-first identity, identical contract to the legacy engine:
    post-ArticleFacts rows compare canonical ids only; legacy rows compare
    the entity's legacy display name against article.entities."""
    ent = entity_by_id(taxonomy_id)
    if ent is None:
        return False
    # Sport-compatibility guard (mirrors legacy entity-scope behavior):
    # a known article sport that contradicts the entity's sport blocks the match.
    if article.sport != "unknown" and article.sport != ent.sport:
        return False
    if article.taxonomy_version is not None:
        return taxonomy_id in (article.entity_ids or [])
    return ent.legacy_name in (article.entities or [])


def _match_scope(article: Article, affinity: ScopeAffinity) -> Optional[_ScopeMatch]:
    if affinity.scope == "sport":
        if article.sport == affinity.target_id:
            return _ScopeMatch(affinity, None, f"sport: {affinity.target_id}")
        return None

    if affinity.scope == "competition":
        comp = COMPETITIONS.get(affinity.target_id)
        if comp is None:
            return None
        hit = match_competition_names(article, [comp.display_en])
        if hit is None:
            return None
        match_kind, _name, provenance = hit
        return _ScopeMatch(affinity, match_kind, f"{comp.display_en} ({provenance})")

    # team / player
    if _entity_on_article(article, affinity.target_id):
        ent = entity_by_id(affinity.target_id)
        return _ScopeMatch(affinity, None, ent.legacy_name if ent else affinity.target_id)
    return None


def _resolve_event_delta(
    v2: ProfileV2, base_target: Optional[str], event_type: str
) -> Optional[EventAffinity]:
    """Scoped entry for the base scope beats the global entry; exact event
    type beats an alias; for a duplicate (scope_ref, event_type) the
    higher-authority source wins (explicit > learned > calibration, #34)."""
    from app.models.profile_v2 import SOURCE_AUTHORITY

    def _best(cands: list) -> Optional[EventAffinity]:
        return max(cands, key=lambda e: SOURCE_AUTHORITY[e.source]) if cands else None

    def _find(scope_ref: Optional[str]) -> Optional[EventAffinity]:
        pool = [e for e in v2.event_affinities if e.scope_ref == scope_ref]
        exact = _best([e for e in pool if e.event_type == event_type])
        if exact:
            return exact
        for alias in _EVENT_ALIASES.get(event_type, []):
            hit = _best([e for e in pool if e.event_type == alias])
            if hit:
                return hit
        return None

    if base_target is not None:
        scoped = _find(base_target)
        if scoped is not None:
            return scoped
    return _find(None)


def _override_matches(article: Article, rule: OverrideRule) -> bool:
    if rule.event_type is not None:
        # EXACT event match only — no alias widening. Shadow analysis caught
        # the alias map turning every NBA major_trade into a star_trade push;
        # push (and never_show) must be surgical.
        if article.event_type != rule.event_type:
            return False
    if rule.scope == "sport":
        return article.sport == rule.target_id
    if rule.scope == "competition":
        comp = COMPETITIONS.get(rule.target_id)
        return comp is not None and match_competition_names(article, [comp.display_en]) is not None
    return _entity_on_article(article, rule.target_id)


def score_article_v2(
    article: Article,
    profile: UserProfile,
    disabled_source_ids: Optional[Set[str]] = None,
) -> DecisionResult:
    if disabled_source_ids is None:
        disabled_source_ids = set()

    contributions: List[dict] = []
    reasoning: List[str] = [f"פרופיל (v2): {profile.display_name}"]

    def _contribute(step: str, scope: Optional[str], effect: str, detail: str) -> None:
        contributions.append({"step": step, "scope": scope, "effect": effect, "detail": detail})

    def _result(decision: str, matched: Optional[str], rule: Optional[str]) -> DecisionResult:
        reasoning.append(f"החלטה סופית: {DECISION_LABELS[decision]}")
        return DecisionResult(
            decision=decision,
            matched_topic=matched,
            matched_event_rule=rule,
            reasoning=reasoning,
            contributions=contributions,
        )

    v2 = profile.profile_v2
    if v2 is None:
        reasoning.append("אין פרופיל v2 → מוסתר")
        _contribute("hard_constraint", None, "hidden", "no_profile_v2")
        return _result("hidden", None, "no_profile_v2")

    # ── 1. Hard constraints ──────────────────────────────────────────────────
    if article.source in disabled_source_ids:
        reasoning.append(f"מקור כבוי (Sources page): {article.source}")
        _contribute("hard_constraint", None, "hidden", f"disabled_source: {article.source}")
        return _result("hidden", None, "disabled_source")

    if article.source in (profile.muted_sources or []):
        reasoning.append(f"מקור מושתק: {article.source}")
        _contribute("hard_constraint", None, "hidden", f"muted_source: {article.source}")
        return _result("hidden", None, "muted_source")

    if profile.muted_topics:
        for tid in (article.sport, article.league):
            if tid and tid in profile.muted_topics:
                reasoning.append(f"נושא מושתק: {tid}")
                _contribute("hard_constraint", None, "hidden", f"muted_topic: {tid}")
                return _result("hidden", None, "muted_topic")

    for rule in v2.overrides:
        if rule.kind in ("mute", "never_show") and _override_matches(article, rule):
            reasoning.append(f"חוק {rule.kind}: {rule.target_id}"
                             + (f" ({rule.event_type})" if rule.event_type else ""))
            _contribute("override", rule.target_id, "hidden", f"{rule.kind}"
                        + (f":{rule.event_type}" if rule.event_type else ""))
            return _result("hidden", rule.target_id, f"{rule.kind}_override")

    # ── 2. Base visibility from matched scope affinities ────────────────────
    matches: List[_ScopeMatch] = []
    for affinity in v2.effective_scope_affinities():
        m = _match_scope(article, affinity)
        if m is not None:
            matches.append(m)

    if not matches:
        reasoning.append(f"ספורט: {article.sport}, ליגה: {article.league or '—'}")
        reasoning.append("אין תחום עניין תואם בפרופיל → מוסתר")
        _contribute("base_scope", None, "hidden", "no_matching_scope")
        return _result("hidden", None, "no_matching_scope")

    # exclude(-2) hides unless a strictly more specific matched scope is non-exclude.
    excludes = [m for m in matches if m.affinity.level == -2]
    for ex in excludes:
        stronger = [
            m for m in matches
            if m.affinity.level > -2 and m.specificity > ex.specificity
        ]
        if not stronger:
            reasoning.append(f"תחום מוחרג (exclude): {ex.detail} → מוסתר")
            _contribute("base_scope", ex.affinity.target_id, "hidden", "excluded_scope")
            return _result("hidden", ex.affinity.target_id, "excluded_scope")
    matches = [m for m in matches if m.affinity.level > -2]

    # Max points win. Ties break toward the BROADER scope so a followed
    # entity inside a followed broad scope is expressed as base + entity
    # boost ("shown because you follow the NBA; elevated because Deni Avdija
    # is involved") instead of silently absorbing the entity into the base.
    base = max(matches, key=lambda m: (m.points, -m.specificity))
    score = base.points
    level_name = AFFINITY_LEVEL_NAMES[base.affinity.level]
    reasoning.append(
        f"בסיס: עוקב ({level_name}) אחרי {base.detail} → {score} נק'"
    )
    _contribute(
        "base_scope", base.affinity.target_id, f"+{score}",
        f"{base.affinity.scope}:{base.detail} level={level_name}"
        + (f" match_kind={base.match_kind}" if base.match_kind else ""),
    )

    # ── 3. Entity boost ──────────────────────────────────────────────────────
    entity_backing = next(
        (
            m for m in matches
            if m.affinity.scope in ("team", "player") and m.affinity.level >= 0
        ),
        None,
    )
    if base.affinity.scope in ("competition", "sport"):
        boost_entity = next(
            (
                m for m in matches
                if m.affinity.scope in ("team", "player") and m.affinity.level >= 1
            ),
            None,
        )
        if boost_entity is not None:
            score += 1
            reasoning.append(f"ישות במעקב בכתבה ({boost_entity.detail}) → ‎+1")
            _contribute("entity_boost", boost_entity.affinity.target_id, "+1",
                        boost_entity.detail)

    # ── 4. Event affinity delta ──────────────────────────────────────────────
    delta_entry = _resolve_event_delta(v2, base.affinity.target_id, article.event_type)
    if delta_entry is not None and delta_entry.delta != 0:
        score += delta_entry.delta
        sign = "+" if delta_entry.delta > 0 else ""
        scope_txt = delta_entry.scope_ref or "גלובלי"
        reasoning.append(
            f"העדפת אירוע ({article.event_type} @ {scope_txt}): {sign}{delta_entry.delta}"
        )
        _contribute("event_affinity", delta_entry.scope_ref, f"{sign}{delta_entry.delta}",
                    article.event_type)

    # ── 5. Importance interaction ────────────────────────────────────────────
    # very_high elevates only articles that are ALREADY visible (score ≥ 1) —
    # importance modulates within legitimate visibility, it never creates it.
    # (Shadow analysis: without this gate, every very_high World Cup /
    # Wimbledon story leaked to low_feed through Guy's low-interest sports.)
    if article.importance == "very_high" and score >= 1:
        score += 1
        reasoning.append("חשיבות מאוד גבוהה → ‎+1")
        _contribute("importance", None, "+1", "very_high")
    elif article.importance in ("low", "very_low"):
        score -= 1
        reasoning.append(f"חשיבות נמוכה ({article.importance}) → ‎-1")
        _contribute("importance", None, "-1", article.importance)

    # ── 6. Membership ceiling (diffuse reach, no entity backing → cap feed) ──
    decision = _threshold(score)
    if (
        base.match_kind == "membership"
        and entity_backing is None
        and _THRESHOLDS.index(decision) > _THRESHOLDS.index("feed")
    ):
        reasoning.append(
            "התאמה מבוססת שיוך קבוצתי בלבד (ללא ישות עוקבת) → תקרה: "
            f"{DECISION_LABELS['feed']} (היה {DECISION_LABELS[decision]})"
        )
        _contribute("ceiling", base.affinity.target_id, "cap:feed", "membership_reach_no_entity")
        decision = "feed"

    # ── 7/8. always_push overrides (the ONLY path to push) ──────────────────
    if decision != "hidden":
        for rule in v2.overrides:
            if rule.kind == "always_push" and _override_matches(article, rule):
                reasoning.append(
                    f"חוק push מפורש: {rule.target_id}"
                    + (f" ({rule.event_type})" if rule.event_type else "")
                )
                _contribute("override", rule.target_id, "push",
                            f"always_push:{rule.event_type or '*'}")
                return _result("push", base.affinity.target_id,
                               f"always_push:{rule.event_type or '*'}")

    reasoning.append(f"ניקוד: {score} → {DECISION_LABELS[decision]}")
    _contribute("threshold", None, decision, f"score={score}")
    return _result(decision, base.affinity.target_id, "affinity_score")
