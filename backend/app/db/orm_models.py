from sqlalchemy import (
    Column, String, Text, Float, Boolean, JSON, Integer, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class ArticleRow(Base):
    __tablename__ = "articles"

    id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    source_display_name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    original_title = Column(String, nullable=True)
    translated_title = Column(String, nullable=True)
    language = Column(String, nullable=False, default="he")
    # Stored as ISO-8601 string for reliable round-trip with timezone info
    published_at = Column(String, nullable=False)
    # Timestamp provenance audit (M8-4, #174) — soft migration; NULL means
    # source-provided (and is all pre-M8 rows can honestly claim).
    published_at_meta = Column(JSON, nullable=True)
    sport = Column(String, nullable=False)
    league = Column(String, nullable=True)
    entities = Column(JSON, nullable=False)
    event_type = Column(String, nullable=False)
    event_certainty = Column(String, nullable=True, default="confirmed")
    importance = Column(String, nullable=False)
    confidence = Column(Float, nullable=False, default=0.85)
    tags = Column(JSON, nullable=False)
    cluster_id = Column(String, nullable=True)
    # Subtitle/description from RSS feed — added via soft migration; nullable for existing rows
    subtitle = Column(Text, nullable=True)
    # LLM classification metadata — added via soft migration; nullable for existing rows
    classified_by = Column(String, nullable=True, default="rules")
    classification_provider = Column(String, nullable=True)
    classification_reason = Column(String, nullable=True)
    classification_confidence = Column(Float, nullable=True)
    # ArticleFacts (issue #28) — added via soft migration; nullable for existing rows
    primary_competition = Column(String, nullable=True)
    article_competitions = Column(JSON, nullable=True)
    entity_ids = Column(JSON, nullable=True)
    classification_trace = Column(JSON, nullable=True)
    taxonomy_version = Column(Integer, nullable=True)
    # Validated story anchors (#141) — computed ONCE at ingestion/enrichment and persisted, so
    # pairwise clustering reads accepted anchors only and never invokes a model per pair. JSON
    # list of {anchor, role, source, validator_id, reason_code}. nullable for existing rows.
    story_anchors = Column(JSON, nullable=True)
    anchor_validator_version = Column(String, nullable=True)


class ProfileRow(Base):
    __tablename__ = "profiles"

    user_id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    language = Column(String, nullable=False, default="he")
    profile_type = Column(String, nullable=False)
    # Topics stored as JSON list of dicts; avoids over-normalizing a deeply nested structure
    topics = Column(JSON, nullable=False)
    muted_topics = Column(JSON, nullable=False)
    muted_sources = Column(JSON, nullable=False)
    followed_entities = Column(JSON, nullable=False)
    # ProfileV2 affinity model (issue #32) — soft-migrated JSON, nullable
    # during the legacy-topics coexistence window.
    profile_v2 = Column(JSON, nullable=True)


class UserRow(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=True, unique=True, index=True)
    password_hash = Column(String, nullable=True)
    role = Column(String, nullable=False, default="user")
    created_at = Column(String, nullable=False)
    onboarding_completed_at = Column(String, nullable=True)
    # Interest-stage process state (issue #77) — soft-migrated; NULL for
    # legacy users, who are treated as complete (never re-funneled).
    interests_completed_at = Column(String, nullable=True)
    last_login_at = Column(String, nullable=True)

    sessions = relationship(
        "AuthSessionRow",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AuthSessionRow(Base):
    __tablename__ = "auth_sessions"

    token_hash = Column(String, primary_key=True)
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)
    last_seen_at = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    user = relationship("UserRow", back_populates="sessions")


class SourceRow(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    language = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    trust_level = Column(String, nullable=False)


class SourceOverrideRow(Base):
    """Runtime enabled/disabled override for ingestion sources (PR 13.1).

    config.py holds the code default; a row here (set via
    PATCH /api/ingest/sources/{source_id}) wins over it and survives restarts.
    Distinct from the legacy `sources` demo table — keyed by ingestion
    source_id (e.g. "sport5_sport").
    """
    __tablename__ = "source_overrides"

    source_id = Column(String, primary_key=True)
    enabled = Column(Boolean, nullable=False)


class FeedbackRow(Base):
    __tablename__ = "feedback_events"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    article_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    # Stored as ISO-8601 string
    created_at = Column(String, nullable=False)
    # Click-time context (issue #34) — soft-migrated JSON.
    context = Column(JSON, nullable=True)
    # Tombstone flag (issue #34) — soft-migrated; 0 = active, 1 = retracted.
    retracted = Column(Integer, nullable=False, default=0)


class CalibrationResponseRow(Base):
    """Calibration V2 (issue #33): one persisted rating per (user, item).
    Re-rating upserts; dataset_version records which dataset was rated."""
    __tablename__ = "calibration_responses"

    user_id = Column(String, primary_key=True)
    item_id = Column(String, primary_key=True)
    rating = Column(String, nullable=False)          # 5-level ordinal key
    dataset_version = Column(Integer, nullable=False)
    created_at = Column(String, nullable=False)      # ISO-8601


class CalibrationHeadlineRow(Base):
    __tablename__ = "calibration_headlines"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    sport = Column(String, nullable=False)
    league = Column(String, nullable=True)
    entities = Column(JSON, nullable=False)
    event_type = Column(String, nullable=False)
    importance = Column(String, nullable=False)
    tags = Column(JSON, nullable=False)


class IngestionRunRow(Base):
    __tablename__ = "ingestion_runs"

    id = Column(String, primary_key=True)
    source_id = Column(String, nullable=False, index=True)
    # Stored as ISO-8601 strings (same pattern as other datetime fields)
    started_at = Column(String, nullable=False)
    finished_at = Column(String, nullable=True)
    status = Column(String, nullable=False)           # ok | error
    fetched_count = Column(Integer, nullable=False, default=0)
    inserted_count = Column(Integer, nullable=False, default=0)
    skipped_duplicate_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    error_message = Column(String, nullable=True)
    # LLM dependency / quality metrics dict (issue #31) — soft-migrated JSON.
    metrics = Column(JSON, nullable=True)
    # Parent orchestration cycle (M7-1, #147). Nullable: pre-M7 rows have none.
    cycle_id = Column(String, nullable=True, index=True)


class SchedulerCycleRow(Base):
    """One ORCHESTRATED ingestion cycle (M7-1, #147) — the durable run record.

    A cycle is the parent of the per-source ``ingestion_runs`` rows it produced
    (children link back via ``cycle_id``); there is deliberately no third
    competing concept. Every trigger — scheduled, startup_catchup, manual,
    run_now — produces exactly one cycle row, including triggers that were
    SKIPPED because another run was active (those record why they did not run).
    """
    __tablename__ = "scheduler_cycles"

    id = Column(String, primary_key=True)             # "cycle_" + uuid4 hex
    trigger = Column(String, nullable=False)          # scheduled | startup_catchup | manual | run_now
    requested_at = Column(String, nullable=False)     # ISO-8601, when the trigger fired
    started_at = Column(String, nullable=True)        # None for skipped cycles
    finished_at = Column(String, nullable=True)
    # running | succeeded | succeeded_with_warnings | failed | skipped_active_run | abandoned
    status = Column(String, nullable=False, index=True)
    # Sanitized one-line error summary; never a stack trace, never a secret.
    error_summary = Column(String, nullable=True)
    # Per-source result summaries (source_id, counts, error) — JSON list.
    source_results = Column(JSON, nullable=True)
    # Filled by later milestone stages; nullable until those stages exist/run.
    notification_summary = Column(JSON, nullable=True)   # M7-6/M7-7 planning + dispatch
    cleanup_summary = Column(JSON, nullable=True)        # M7-3 retention
    # Diagnosing duplicate schedulers: which process ran this cycle.
    process_identity = Column(String, nullable=True)     # "pid=… host=…"
    # Config fingerprint needed to explain behavior (interval, flags) — JSON.
    config_snapshot = Column(JSON, nullable=True)


class NotificationEventRow(Base):
    """One story-level notification event for one profile (M7-5, #151).

    The event id IS the stable story identity for notification purposes.
    What makes it stable is not this row — it is the LINEAGE below: creating
    an event requires inserting every current component member into
    ``notification_story_members``, whose DB UNIQUE constraint is the actual
    duplicate-prevention mechanism. Cluster ids may churn (anchor change,
    component merge, backfill — reconcile_scope preserves ids only through
    overlap); article ids never do (``rss_`` + sha1(url)). So the lineage is
    keyed on article ids, and the event survives every realistic component
    evolution.
    """
    __tablename__ = "notification_events"

    id = Column(String, primary_key=True)              # "notif_" + uuid4 hex
    profile_id = Column(String, nullable=False, index=True)
    policy_version = Column(String, nullable=False)
    # pending | claimed | sent | failed_retryable | failed_final | unknown
    # | suppressed_watermark  (planted at activation; never dispatched)
    status = Column(String, nullable=False, index=True)
    created_at = Column(String, nullable=False)

    # Story snapshot AT CREATION (a later canonical change must not re-notify,
    # and the message links what the feed showed when the decision was made).
    cluster_id_at_creation = Column(String, nullable=True)   # None: unclustered story
    canonical_article_id = Column(String, nullable=False)
    canonical_headline = Column(String, nullable=False)
    source = Column(String, nullable=False)
    url = Column(String, nullable=False)
    tier = Column(String, nullable=False)                    # "push" for the pilot
    decision_provenance = Column(JSON, nullable=True)

    # Delivery lifecycle (M7-7 fills these).
    claimed_at = Column(String, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(String, nullable=True)
    final_at = Column(String, nullable=True)
    provider = Column(String, nullable=True)                 # "telegram"
    provider_message_id = Column(String, nullable=True)
    last_error_class = Column(String, nullable=True)         # sanitized class, never a payload
    # Lineage notes: later component merges/expansions recorded for audit.
    lineage_notes = Column(JSON, nullable=True)


class NotificationStoryMemberRow(Base):
    """THE uniqueness mechanism (M7-5, #151): an article id may belong to at
    most one notified story per (profile, policy version) — enforced by the
    database, not by application ``exists()`` checks.

    Rows are durable and independent of the ``articles`` table (no FK): they
    are the notification system's MEMORY, and retention deleting an old
    article must not erase the fact that its story was already notified.
    """
    __tablename__ = "notification_story_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(String, nullable=False)
    policy_version = Column(String, nullable=False)
    article_id = Column(String, nullable=False)
    event_id = Column(String, nullable=False, index=True)
    added_at = Column(String, nullable=False)
    # Why this member is in the lineage: "creation" | "expansion" | "merge"
    reason = Column(String, nullable=False, default="creation")

    __table_args__ = (
        UniqueConstraint("profile_id", "policy_version", "article_id",
                         name="uq_notification_story_member"),
    )


class NotificationWatermarkRow(Base):
    """Activation watermark (M7-5, #151): enabling Telegram must not flood
    every historically PUSH-eligible story. Set once per (profile, policy)
    by the guarded activation initialization; the planner refuses to plan
    for a profile with no watermark.
    """
    __tablename__ = "notification_watermarks"

    profile_id = Column(String, primary_key=True)
    policy_version = Column(String, primary_key=True)
    activated_at = Column(String, nullable=False)
    suppressed_story_count = Column(Integer, nullable=False, default=0)


class WorkerStatusRow(Base):
    """The scheduler worker's alive signal (M7-2, #148) — one row, id always 1.

    Distinct from the run lease: the lease says "a cycle is mutating the
    corpus"; this says "the worker PROCESS exists", refreshed on idle ticks
    too, so health (M7-4) can tell a dead worker from a quiet one.
    """
    __tablename__ = "worker_status"

    id = Column(Integer, primary_key=True)            # always 1
    last_seen_at = Column(String, nullable=True)      # ISO-8601
    state = Column(String, nullable=True)             # starting | idle | stopped
    owner = Column(String, nullable=True)             # process identity
    interval_seconds = Column(Integer, nullable=True)


class SchedulerLeaseRow(Base):
    """THE single-flight guard (M7-1, #147) — one durable row, id always 1.

    HONEST SINGLE-NODE CONTRACT: SQLite serializes writers, so a conditional
    UPDATE on this row is atomic across PROCESSES on this machine sharing this
    database file. That is the whole guarantee — this is not a distributed
    lock and must never be described as one.

    Acquisition: one atomic UPDATE that succeeds only when the lease is free
    OR the holder's heartbeat is older than the stale cutoff (dead-process
    takeover). The previous holder's cycle is then marked ``abandoned``.
    A process-local mutex would not survive process boundaries; this does.
    """
    __tablename__ = "scheduler_lease"

    id = Column(Integer, primary_key=True)            # always 1
    active_cycle_id = Column(String, nullable=True)   # NULL == free
    heartbeat_at = Column(String, nullable=True)      # ISO-8601, refreshed during a run
    owner = Column(String, nullable=True)             # process identity of the holder


class StoryClusterRow(Base):
    """A corpus-level GROUPING RECORD — not a fact (issue #101, docs/CLUSTERING.md §4).

    Deliberately carries NO cluster-level article facts: no unioned entity_ids, no max
    importance, no merged event facts. Article facts stay authoritative on each member
    article and are never rewritten by clustering. ``event_state`` and ``sport`` here are
    GROUPING KEYS (what the members had in common), not assertions about the world.

    Membership lives on the existing ``articles.cluster_id`` column — so this adds a new
    table but requires NO migration to ``articles``.
    """
    __tablename__ = "story_clusters"

    # Formation-time identity: "cluster_" + sha1(anchor_article_id)[:16].
    # Assigned ONCE. Late arrivals append; the id NEVER churns (docs/CLUSTERING.md §8).
    id = Column(String, primary_key=True)

    # The founding member (earliest published_at, tie -> lowest article id).
    #
    # NULLABLE, and deliberately so (pruning-safety review, #101). The id above was minted
    # from this article AT FORMATION and is now an immutable historical fact — the cluster
    # does NOT depend on the anchor article continuing to exist. The feed horizon is ~36h
    # but articles are retained longer for clustering/dedup/feedback/QA (docs/CLUSTERING.md
    # §14); when a retention capability eventually prunes articles, this reference must be
    # able to move (to the earliest surviving member) or be nulled WITHOUT the cluster id
    # ever churning. A NOT NULL column keyed to a prunable row is a foot-gun.
    #
    # After a prune this is the OPERATIONAL anchor (earliest surviving member), which may
    # differ from the article the id was originally derived from. That is fine and expected:
    # id != f(current anchor) once pruning has occurred.
    anchor_article_id = Column(String, nullable=True, index=True)

    # The §9.1 ladder winner. MAY change when a stronger member arrives — that is fine and
    # does not affect the id.
    representative_article_id = Column(String, nullable=False)

    event_state = Column(String, nullable=False)      # grouping key, not a fact
    sport = Column(String, nullable=True)             # grouping key; NULL when unknown-sport

    # ISO-8601 strings, matching every other datetime column in this schema.
    formed_at = Column(String, nullable=False)
    # OPERATIONAL/DEBUG metadata only. NEVER used for feed ordering — the per-user
    # sort_at comes from the newest VISIBLE member (docs/CLUSTERING.md §9.3).
    last_member_added_at = Column(String, nullable=False)

    method = Column(String, nullable=False, default="deterministic")   # v1: always this
    # Which rule generation produced this cluster. A rule change is an explicit,
    # auditable recompute — never silent drift.
    rule_version = Column(Integer, nullable=False, default=1)
    member_count = Column(Integer, nullable=False, default=0)


class GameResultRow(Base):
    """A normalized, project-owned sports game/result (issue #178).

    Provider-agnostic by design: a ``ResultsProvider`` adapter maps its raw
    payload into this shape, so API routes and the UI never see provider
    field names. IDENTITY is ``(provider, external_id)`` — the primary key is
    ``game_`` + sha1(provider|external_id), so repeated syncs UPDATE the same
    row (score/status/start_time drift) and never create duplicates.

    Relevance is NOT stored here — it is a per-user decision computed at read
    time from ProfileV2 affinities (docs/RESULTS.md). This table is corpus
    data shared across all users, exactly like ``articles``.
    """
    __tablename__ = "game_results"

    id = Column(String, primary_key=True)             # "game_" + sha1(provider|external_id)[:24]
    provider = Column(String, nullable=False)         # "thesportsdb" | "fake"
    external_id = Column(String, nullable=False)      # provider event id — stable identity

    competition_id = Column(String, nullable=False, index=True)  # comp:* (project taxonomy)
    sport = Column(String, nullable=False)
    season = Column(String, nullable=True)
    stage = Column(String, nullable=True)             # round/stage label (e.g. "Final", "12")

    # scheduled | live | final | postponed | cancelled | unknown
    status = Column(String, nullable=False, default="unknown")
    # Normalized kickoff/tipoff as ISO-8601 UTC (same string convention as the
    # rest of the schema). Nullable when the provider gives no usable time.
    start_time = Column(String, nullable=True, index=True)

    # Team display comes from the provider; team IDENTITY (for followed-team
    # relevance) is resolved against the taxonomy at sync time. NULL id = the
    # provider team is not in our taxonomy (the game can still be relevant via
    # a followed competition).
    home_team_name = Column(String, nullable=False)
    away_team_name = Column(String, nullable=False)
    home_team_id = Column(String, nullable=True, index=True)   # team:* or NULL
    away_team_id = Column(String, nullable=True, index=True)   # team:* or NULL
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)

    last_synced_at = Column(String, nullable=False)   # ISO-8601, refreshed every upsert

    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_game_result_identity"),
    )


class ResultsSyncStateRow(Base):
    """Single-row results-sync bookkeeping (issue #178), id always 1.

    Powers throttling (``last_attempt_at`` gates the scheduler stage so opening
    the page never triggers provider calls and cycles don't hammer the API) and
    ops observability (last status + summary). Mirrors the WorkerStatus pattern.
    """
    __tablename__ = "results_sync_state"

    id = Column(Integer, primary_key=True)            # always 1
    last_attempt_at = Column(String, nullable=True)
    last_success_at = Column(String, nullable=True)
    last_status = Column(String, nullable=True)       # ok | error | partial
    last_summary = Column(JSON, nullable=True)


class ClusterEdgeRow(Base):
    """ACCEPTED match evidence only (issue #101, docs/CLUSTERING.md §4).

    Rejected candidates are deliberately NOT persisted: near-miss diagnostics are bounded
    and computed ON DEMAND for QA/Debug. Persisting every rejection would be unbounded
    write amplification with no proven need.
    """
    __tablename__ = "cluster_edges"

    id = Column(String, primary_key=True)             # sha1(cluster_id|a|b) — idempotent
    cluster_id = Column(String, nullable=False, index=True)
    article_a = Column(String, nullable=False)
    article_b = Column(String, nullable=False)

    jaccard = Column(Float, nullable=False)
    hours_apart = Column(Float, nullable=False)
    rare_tokens = Column(JSON, nullable=False)        # the discriminative tokens that carried it
    entity_overlap = Column(JSON, nullable=False)
    competition_overlap = Column(JSON, nullable=False)
    tier = Column(String, nullable=False)             # A | B | C
