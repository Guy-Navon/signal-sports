"""
Shadow-mode comparison harness (issue #32).

Scores every article with BOTH engines — the legacy topic engine
(authoritative until the flip) and the Preference V2 affinity scorer — and
reports agreements/disagreements with full traces. Powers the
`GET /api/debug/shadow/{user_id}` endpoint, the shadow tests, and the Fable
flip-review checkpoint.
"""
from typing import List, Optional, Set

from pydantic import BaseModel

from app.models.article import Article
from app.models.profile import UserProfile
from app.services.preference_engine import score_article_v2
from app.services.relevance_engine import DECISION_RANK, score_article


class ShadowComparison(BaseModel):
    article_id: str
    title: str
    event_type: str
    sport: str
    league: Optional[str] = None
    legacy_decision: str
    v2_decision: str
    agree: bool
    direction: Optional[str] = None      # "promoted" | "demoted" (v2 vs legacy)
    legacy_reasoning: List[str] = []
    v2_reasoning: List[str] = []
    v2_contributions: Optional[List[dict]] = None


class ShadowReport(BaseModel):
    user_id: str
    total: int
    agreements: int
    disagreements: int
    agreement_rate: Optional[float] = None
    promoted: int = 0                    # v2 ranks higher than legacy
    demoted: int = 0                     # v2 ranks lower than legacy
    v2_push_count: int = 0
    legacy_push_count: int = 0
    comparisons: List[ShadowComparison] = []   # disagreements only


def compare_article(
    article: Article,
    profile: UserProfile,
    disabled_source_ids: Optional[Set[str]] = None,
) -> ShadowComparison:
    legacy = score_article(article, profile, disabled_source_ids or set())
    v2 = score_article_v2(article, profile, disabled_source_ids or set())
    agree = legacy.decision == v2.decision
    direction = None
    if not agree:
        direction = (
            "promoted"
            if DECISION_RANK[v2.decision] > DECISION_RANK[legacy.decision]
            else "demoted"
        )
    return ShadowComparison(
        article_id=article.id,
        title=article.title,
        event_type=article.event_type,
        sport=article.sport,
        league=article.league,
        legacy_decision=legacy.decision,
        v2_decision=v2.decision,
        agree=agree,
        direction=direction,
        legacy_reasoning=legacy.reasoning,
        v2_reasoning=v2.reasoning,
        v2_contributions=v2.contributions,
    )


def build_shadow_report(
    articles: List[Article],
    profile: UserProfile,
    disabled_source_ids: Optional[Set[str]] = None,
) -> ShadowReport:
    comparisons = [compare_article(a, profile, disabled_source_ids) for a in articles]
    disagreements = [c for c in comparisons if not c.agree]
    total = len(comparisons)
    return ShadowReport(
        user_id=profile.user_id,
        total=total,
        agreements=total - len(disagreements),
        disagreements=len(disagreements),
        agreement_rate=round((total - len(disagreements)) / total, 4) if total else None,
        promoted=sum(1 for c in disagreements if c.direction == "promoted"),
        demoted=sum(1 for c in disagreements if c.direction == "demoted"),
        v2_push_count=sum(1 for c in comparisons if c.v2_decision == "push"),
        legacy_push_count=sum(1 for c in comparisons if c.legacy_decision == "push"),
        comparisons=disagreements,
    )
