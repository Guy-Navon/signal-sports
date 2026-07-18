import os
from typing import List, Optional, Set
from app.models.article import Article
from app.models.profile import UserProfile
from app.models.scoring import ScoredArticle
from app.services.freshness import fresh_only
from app.services.preference_engine import score_article_v2
from app.services.relevance_engine import score_article, DECISION_RANK


def active_engine() -> str:
    """Engine selector (issue #32): "v2" (affinity scorer — the default since
    the shadow-validated flip; Fable checkpoint 2026-07-08: Guy 96.3% / Deni
    100% agreement, push parity exact) or "legacy" (topic engine, kept as the
    instant rollback path via PREFERENCE_ENGINE=legacy)."""
    value = os.environ.get("PREFERENCE_ENGINE", "v2").strip().lower()
    return value if value in ("legacy", "v2") else "v2"


def build_feed(
    articles: List[Article],
    profile: UserProfile,
    include_hidden: bool = False,
    disabled_source_ids: Optional[Set[str]] = None,
    engine: Optional[str] = None,
    session=None,
) -> List[ScoredArticle]:
    # Freshness (M8-2, #172): the consumer feed shows only in-window articles.
    # Applied HERE, before scoring, so expired articles are never scored, never
    # count toward tiers, never enter cluster cards (canonical selection sees
    # in-window members only) and never reach the Telegram planner — which
    # consumes this exact function. Debug (include_hidden=True) keeps showing
    # everything, expired included, by contract.
    if not include_hidden:
        articles = fresh_only(articles)

    engine = engine or active_engine()
    # A profile with no v2 payload cannot be scored by the v2 engine — fall
    # back to legacy rather than hiding everything (safe-migration behavior).
    if engine == "v2" and profile.profile_v2 is None:
        engine = "legacy"
    scorer = score_article_v2 if engine == "v2" else score_article

    scored = []
    for article in articles:
        result = scorer(article, profile, disabled_source_ids or set())
        if include_hidden or result.decision != "hidden":
            scored.append(ScoredArticle(
                article=article,
                decision=result.decision,
                matched_topic=result.matched_topic,
                matched_event_rule=result.matched_event_rule,
                reasoning=result.reasoning,
                contributions=result.contributions,
                engine=engine,
            ))

    # Story-clustering collapse (#103). Runs AFTER Preference V2 has scored every article
    # independently — it never touches a score, and article-level decisions are unchanged.
    # With CLUSTERING_ENABLED=false (the production default) this is a no-op and the flat
    # feed is returned completely untouched.
    if session is not None:
        from app.services.cluster_collapse import collapse_clusters, feed_sort_key
        scored = collapse_clusters(scored, session, include_hidden=include_hidden)
        scored.sort(key=feed_sort_key, reverse=True)
        return scored

    # Sort: decision rank (desc), then published_at (desc)
    scored.sort(
        key=lambda s: (DECISION_RANK[s.decision], s.article.published_at),
        reverse=True,
    )
    return scored
