from datetime import datetime
from typing import Dict, Optional, List
from pydantic import BaseModel
from app.models.article import Article


class DecisionResult(BaseModel):
    decision: str  # hidden | low_feed | feed | high_feed | push
    matched_topic: Optional[str] = None
    matched_entities: List[str] = []
    matched_event_rule: Optional[str] = None
    reasoning: List[str] = []
    # Structured contribution trace (Preference V2, issue #32):
    # [{step, scope, effect, detail}]. None on legacy-engine results.
    contributions: Optional[List[Dict]] = None


class ClusterMember(BaseModel):
    """One member of a story cluster, as presented to a user (#103)."""
    article_id: str
    source: str
    source_display_name: str
    title: str
    url: str
    published_at: datetime
    decision: str


class ClusterCard(BaseModel):
    """User-specific collapse of a corpus cluster (#103, docs/CLUSTERING.md §9).

    Attached to the DISPLAYED member's ScoredArticle. Purely additive: the article's own
    ``decision`` is untouched, so clustering causes zero article-level drift. The CARD ranks
    by ``decision`` (max over this user's VISIBLE members) and ``sort_at`` (newest VISIBLE
    member) — never by a hidden member.
    """
    cluster_id: str
    decision: str                                   # MAX over visible members
    representative_article_id: Optional[str] = None  # corpus-level, user-independent
    displayed_article_id: str                        # representative if visible, else best visible
    priority_article_id: str                         # the visible member that SET the decision
    displayed_reason: str                            # representative_visible | representative_hidden_fallback
    source_count: int                                # VISIBLE members only
    sort_at: datetime                                # newest VISIBLE member
    members: List[ClusterMember] = []                # VISIBLE members only
    # Debug-only. ALWAYS empty in the consumer payload — clustering must never resurrect
    # content a user's preferences hid.
    suppressed_members: List[ClusterMember] = []
    rule_version: Optional[int] = None
    event_state: Optional[str] = None


class ScoredArticle(BaseModel):
    article: Article
    decision: str
    matched_topic: Optional[str] = None
    matched_event_rule: Optional[str] = None
    reasoning: List[str] = []
    contributions: Optional[List[Dict]] = None
    # Which engine produced this trace (issue #35): "v2" | "legacy".
    engine: Optional[str] = None
    # Story clustering (#103). None for unclustered articles AND whenever
    # CLUSTERING_ENABLED=false — the production default returns the flat feed unchanged.
    cluster: Optional[ClusterCard] = None
