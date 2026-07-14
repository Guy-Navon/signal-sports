"""
User-specific cluster collapse for the feed (#103) — docs/CLUSTERING.md §9.

Clusters are CORPUS facts. What a user *sees* is not. This module is the boundary.

It runs AFTER Preference V2 has scored every article independently, and it never touches a
score. Its only job is presentation: turn N per-article results that happen to share a
cluster into ONE card, for THIS user.

Hard rules (all test-locked):
  - every article keeps its OWN decision — clustering causes zero article-level drift;
  - a cluster is eligible only when at least ONE member is visible;
  - the CARD decision is the MAX decision over that user's VISIBLE members;
  - the corpus representative is displayed when visible, else the best visible member;
  - source count and alternatives list VISIBLE members only;
  - suppressed (hidden) members NEVER appear in the consumer payload — clustering must not
    resurrect content a user's preferences hid;
  - the card's sort timestamp is the newest VISIBLE member (a hidden member must never bump
    a cluster in this user's feed);
  - at most ONE card per cluster ⇒ at most one push per cluster.

Disabled mode (``CLUSTERING_ENABLED=false``, the production default) returns the flat feed
completely untouched.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.clustering.ingest_stage import clustering_enabled
from app.db.orm_models import StoryClusterRow
from app.models.scoring import ClusterCard, ClusterMember, ScoredArticle
from app.services.relevance_engine import DECISION_RANK


def _rank(decision: str) -> int:
    return DECISION_RANK.get(decision, 0)


def _fact_completeness(a) -> int:
    score = 0
    if getattr(a, "entity_ids", None):
        score += 1
    if getattr(a, "primary_competition", None):
        score += 1
    if getattr(a, "event_type", None) and a.event_type != "news":
        score += 1
    return score


_CERTAINTY_RANK = {"confirmed": 2, "probable": 1}


def _best_visible_key(s: ScoredArticle):
    """Fallback ordering when the representative is hidden for this user.

    Decision first (the user's own priority), then the §9.1 representative ladder so the
    choice stays deterministic and matches the corpus-level notion of "strongest article".
    """
    a = s.article
    return (
        _rank(s.decision),
        _fact_completeness(a),
        _CERTAINTY_RANK.get(getattr(a, "event_certainty", None) or "", 0),
        a.published_at,
        tuple(-ord(c) for c in a.id),   # lowest id wins on a full tie
    )


def collapse_clusters(
    scored: list[ScoredArticle],
    session: Session,
    include_hidden: bool = False,
) -> list[ScoredArticle]:
    """Collapse clustered articles into one card each.

    Consumer feed (``include_hidden=False``): members are collapsed — exactly one item per
    eligible cluster, carrying a ``ClusterCard``.

    Debug feed (``include_hidden=True``): the flat list is preserved (Debug must keep showing
    every article, including hidden ones), but the displayed member additionally carries the
    ``ClusterCard`` — including ``suppressed_members`` — so Debug can explain the collapse
    without the consumer ever seeing it.
    """
    if not clustering_enabled():
        return scored                       # production default: flat feed, untouched

    by_cluster: dict[str, list[ScoredArticle]] = {}
    for s in scored:
        cid = getattr(s.article, "cluster_id", None)
        if cid:
            by_cluster.setdefault(cid, []).append(s)
    if not by_cluster:
        return scored

    cards: dict[str, tuple[str, ClusterCard]] = {}   # cluster_id -> (displayed_id, card)

    for cid, members in by_cluster.items():
        visible = [m for m in members if m.decision != "hidden"]
        if not visible:
            continue                        # eligibility: at least one visible member

        row: Optional[StoryClusterRow] = session.get(StoryClusterRow, cid)
        rep_id = row.representative_article_id if row else None

        # Displayed member: the corpus representative when visible, else the best visible.
        displayed = next((m for m in visible if m.article.id == rep_id), None)
        fallback_used = displayed is None
        if displayed is None:
            displayed = max(visible, key=_best_visible_key)

        # Card decision = MAX over visible members. Priority member = the one that set it.
        priority = max(visible, key=_best_visible_key)
        card_decision = priority.decision

        suppressed = [m for m in members if m.decision == "hidden"]

        card = ClusterCard(
            cluster_id=cid,
            decision=card_decision,
            representative_article_id=rep_id,
            displayed_article_id=displayed.article.id,
            priority_article_id=priority.article.id,
            displayed_reason=(
                "representative_hidden_fallback" if fallback_used else "representative_visible"
            ),
            source_count=len({m.article.source for m in visible}),
            sort_at=max(m.article.published_at for m in visible),
            members=[
                ClusterMember(
                    article_id=m.article.id,
                    source=m.article.source,
                    source_display_name=getattr(m.article, "source_display_name", m.article.source),
                    title=m.article.translated_title or m.article.title,
                    url=m.article.url,
                    published_at=m.article.published_at,
                    decision=m.decision,
                )
                for m in sorted(visible, key=lambda x: x.article.published_at, reverse=True)
            ],
            # Debug-only. Never populated for the consumer payload.
            suppressed_members=[
                ClusterMember(
                    article_id=m.article.id,
                    source=m.article.source,
                    source_display_name=getattr(m.article, "source_display_name", m.article.source),
                    title=m.article.translated_title or m.article.title,
                    url=m.article.url,
                    published_at=m.article.published_at,
                    decision=m.decision,
                )
                for m in suppressed
            ] if include_hidden else [],
            rule_version=row.rule_version if row else None,
            event_state=row.event_state if row else None,
        )
        cards[cid] = (displayed.article.id, card)

    out: list[ScoredArticle] = []
    for s in scored:
        # A hidden member must never reach the consumer — not even from an INELIGIBLE
        # (all-hidden) cluster, which produces no card and would otherwise let its members
        # fall through as ordinary items. Debug still sees everything.
        if s.decision == "hidden" and not include_hidden:
            continue
        cid = getattr(s.article, "cluster_id", None)
        entry = cards.get(cid) if cid else None
        if entry is None:
            out.append(s)                   # unclustered, or an ineligible cluster
            continue
        displayed_id, card = entry
        if s.article.id == displayed_id:
            out.append(s.model_copy(update={"cluster": card}))
        elif include_hidden:
            out.append(s)                   # Debug keeps every article visible
        # else: consumer — the member is folded into the card and NOT emitted
    return out


def feed_sort_key(s: ScoredArticle):
    """Ordering that respects the cluster card.

    The card ranks by its OWN decision (max over visible members) and by its OWN sort_at
    (newest visible member) — never by a hidden member, and never by the displayed member's
    individual decision when a sibling outranks it.
    """
    if s.cluster is not None:
        return (_rank(s.cluster.decision), s.cluster.sort_at)
    return (_rank(s.decision), s.article.published_at)
