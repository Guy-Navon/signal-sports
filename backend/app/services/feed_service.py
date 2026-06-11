from typing import List, Optional, Set
from app.models.article import Article
from app.models.profile import UserProfile
from app.models.scoring import ScoredArticle
from app.services.relevance_engine import score_article, DECISION_RANK


def build_feed(
    articles: List[Article],
    profile: UserProfile,
    include_hidden: bool = False,
    disabled_source_ids: Optional[Set[str]] = None,
) -> List[ScoredArticle]:
    scored = []
    for article in articles:
        result = score_article(article, profile, disabled_source_ids or set())
        if include_hidden or result.decision != "hidden":
            scored.append(ScoredArticle(
                article=article,
                decision=result.decision,
                matched_topic=result.matched_topic,
                matched_event_rule=result.matched_event_rule,
                reasoning=result.reasoning,
            ))

    # Sort: decision rank (desc), then published_at (desc)
    scored.sort(
        key=lambda s: (DECISION_RANK[s.decision], s.article.published_at),
        reverse=True,
    )
    return scored
