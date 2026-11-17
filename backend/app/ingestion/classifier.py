"""
Deterministic keyword-based article classifier.

No LLM. No external calls. Fully testable as a pure function.

Design notes:
- Primary signal is the article title. Optional subtitle fills gaps when title is
  ambiguous or produces sport=unknown / no entities / generic event_type="news".
- Subtitle never overrides an already-resolved sport value from the title.
- Optional url is used for URL-path-based league inference (e.g. EuroCup vs EuroLeague).
- Hebrew and English keywords live in the same lists; lowercased before matching.
- Source ID is used to apply basketball-only defaults for Eurohoops/Sportando.
- Confidence is additive: each matched signal contributes a fixed increment.
- When unsure, sport="unknown", event_type="news", confidence<=0.5.

Layout (audit L8): this module owns ``ClassificationResult`` and ``classify()``, the
orchestration of the rule families. The families live in ``app.ingestion.classifier_rules``
(matching, sport, league, entities, events, scoring) and are all re-exported below, so
``from app.ingestion.classifier import <name>`` keeps working for every existing name.
"""

from dataclasses import dataclass
from typing import Optional

# Re-exports: names that lived in this module before the split (audit L8). Kept so
# existing imports keep working; classify() also resolves its helpers through these.
from app.classification.event_evidence import (  # noqa: F401
    PREVAILED_OVER_PATTERN,
    EventEvidence,
    reads_as_champion_epithet,
    validate_event_evidence,
)
from app.classification.sport_guards import (  # noqa: F401
    committed_sport,
    has_bcl_abbreviation,
    has_shared_champions_league_name,
    is_unsupported_sport,
    shared_champions_league_sport,
)
from app.ingestion.classifier_rules.matching import (  # noqa: F401
    _BASKETBALL_ONLY_SOURCES,
    _has,
    _has_word,
)
from app.ingestion.classifier_rules.sport import (  # noqa: F401
    _BASKETBALL_CTX_KW,
    _BASKETBALL_KW,
    _derive_football_maccabi_kw,
    _detect_sport,
    _FOOTBALL_CTX_KW,
    _FOOTBALL_KW,
    _FOOTBALL_MACCABI_KW,
    _GRAND_SLAM_PHRASES,
    _HAPOEL_TLV_KW,
    _has_basketball_context,
    _has_football_context,
    _has_football_maccabi_context,
    _has_hapoel_tel_aviv_phrase,
    _has_maccabi_tel_aviv_phrase,
    _MACCABI_TLV_KW,
    _NON_TENNIS_SLAM_CONTEXT,
    _shared_name_context,
    tennis_keywords_for,
    _TENNIS_KW,
)
from app.ingestion.classifier_rules.league import (  # noqa: F401
    _ACB_KW,
    _AUSTRALIAN_OPEN_KW,
    _BCL_KW,
    _BSL_KW,
    _detect_league,
    _EUROCUP_KW,
    _EUROLEAGUE_KW,
    _GREEK_KW,
    _infer_league_from_membership,
    _ISRAELI_BBALL_CONTEXT_KW,
    _ISRAELI_BBALL_DIRECT_KW,
    _LBA_KW,
    _LNB_KW,
    _NBA_DIRECT_KW,
    _NBA_TEAM_KW,
    _ROLAND_GARROS_KW,
    _US_OPEN_KW,
    _WIMBLEDON_KW,
)
from app.ingestion.classifier_rules.entities import (  # noqa: F401
    _BASKETBALL_ENRICHMENT_PHRASES,
    _club_person_sport,
    _DENI_KW,
    _DEPARTURE,
    _derive_basketball_enrichment_phrases,
    _detect_entities,
    enrich_basketball_entities_after_sport_resolve,
    enrich_maccabi_entity_after_sport_resolve,
    _filter_entities_for_sport,
    _NATIONAL_TEAM_MARKERS,
    _resolution_to_legacy_entities,
    _resolve_text_entities,
    _sport_context_for_resolver,
    _TRANSFER,
)
from app.ingestion.classifier_rules.events import (  # noqa: F401
    _CANDIDATE_KW,
    _CANDIDATE_WORD_KW,
    _DEATH_ACCIDENT_KW,
    detect_article_event,
    _detect_event_evidence,
    _EARLY_ROUND_TENNIS_KW,
    _FINALS_KW,
    _GRAND_SLAM_KW,
    _GRAND_SLAM_WIN_KW,
    _INJURY_KW,
    _NEGOTIATION_KW,
    _NEGOTIATION_WORD_KW,
    _PLAYOFF_KW,
    _REGULAR_SEASON_KW,
    _RELEASE_KW,
    _RESULT_KW,
    _SCHEDULE_KW,
    _SIGNING_KW,
    _SIGNING_WORD_KW,
    _TITLE_WIN_UNAMBIGUOUS_KW,
    _TRADE_KW,
    _TRADE_WORD_KW,
    _WIN_CHAMPIONSHIP_CTX_KW,
    _WIN_VERB_HE,
)
from app.ingestion.classifier_rules.scoring import (  # noqa: F401
    _assign_confidence,
    _assign_importance,
    _collect_tags,
    compute_importance,
    _HIGH_ENTITIES,
    _HIGH_EVENTS,
    _HIGH_LEAGUES,
    _LOW_EVENTS,
    _VERY_HIGH_EVENTS,
)
from app.taxonomy import (  # noqa: F401
    COMPETITIONS,
    EntityResolution,
    entities_by_sport,
    entity_by_id,
    entity_by_legacy_name,
    is_wnba_story,
    legacy_sport,
    resolve_entities,
    without_nba_clubs,
)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    sport: str                  # basketball | football | tennis | unknown
    league: Optional[str]       # NBA | EuroLeague | EuroCup | Israeli Basketball League | …
    entities: list[str]         # Maccabi Tel Aviv Basketball | Deni Avdija | …
    event_type: str             # signing | negotiation | injury | … | news
    importance: str             # very_low | low | medium | high | very_high
    confidence: float           # 0.0 – 1.0
    tags: list[str]             # keyword hits for debugging / display
    event_certainty: str = "confirmed"  # confirmed | probable | weak


# ── Public interface ──────────────────────────────────────────────────────────

def classify(
    title: str,
    source_id: str = "",
    language: str = "en",
    url: str = "",
    subtitle: str | None = None,
    source_sport_hint: str | None = None,
) -> ClassificationResult:
    """Classify an article title using deterministic keyword rules.

    Args:
        title:             Article title in Hebrew or English.
        source_id:         Internal source ID for source-specific defaults.
        language:          "he" or "en".
        url:               Article URL — used for URL-path-based league inference
                           (e.g. detecting EuroCup vs EuroLeague from /eurocup/ path).
        subtitle:          Optional subtitle/description text. Title is always the primary
                           signal. Subtitle may fill sport=unknown, add missing entities,
                           improve league detection, or refine event_type="news" when the
                           title context is insufficient. Subtitle never overrides an
                           already-resolved sport value from the title.
        source_sport_hint: Pre-computed sport hint from the article URL for sources with
                           reliable category URL schemes (e.g. Israel Hayom). When set,
                           overrides keyword-based sport detection in the deterministic path.

    Returns:
        ClassificationResult with all fields populated.
    """
    text = title.lower()
    sub_text = subtitle.lower() if subtitle else ""

    sport = _detect_sport(text, source_id, source_sport_hint=source_sport_hint)

    _basketball_only_src = source_id in _BASKETBALL_ONLY_SOURCES
    title_resolution = _resolve_text_entities(text, source_id)
    entities = _resolution_to_legacy_entities(title_resolution, text)

    # Ambiguous club mention: the resolver found a cross-sport club name it could
    # not disambiguate (e.g. "מכבי תל אביב" / "הפועל ירושלים" with no sport
    # evidence). Abstain — no entity, ambiguous_club tag, LLM gate force-calls.
    # Basketball-only sources are never ambiguous — they only cover basketball.
    is_ambiguous_club = not _basketball_only_src and bool(title_resolution.ambiguous)

    # A named club person proves the sport even next to an ambiguous club name (#259).
    # That evidence also lets a GUARDED club in the same title resolve ("ג'ימי קלארק חתם
    # בפנאתינייקוס"): without it the person's registry club was the article's only club.
    if sport == "unknown":
        sport = _club_person_sport(title_resolution) or "unknown"
        if sport != "unknown":
            # The sport-aware resolution sees every club the title names, so it also decides
            # whether a departure/transfer makes the roster club unreliable.
            entities = _detect_entities(text, source_id, sport_override=sport)

    # Entity-based sport inference: when all resolved entities agree on one
    # sport, that sport is taxonomy evidence (previously a basketball-only bias).
    if sport == "unknown" and entities and not is_ambiguous_club:
        entity_sports = {legacy_sport(e) for e in entities} - {None}
        if len(entity_sports) == 1:
            sport = next(iter(entity_sports))

    # Cross-sport entity post-filter — defensive; entity resolution should already
    # agree with sport detection, but this prevents stray entities if they diverge.
    entities = _filter_entities_for_sport(entities, sport)

    # Sport detection may have resolved the sport (source hint, explicit sport
    # keywords) even when mixed context words made entity resolution abstain
    # (e.g. "ליגת העל בכדורסל" contains both football and basketball markers).
    # Re-resolve the ambiguous mention with the resolved sport as taxonomy evidence.
    if is_ambiguous_club and sport in ("basketball", "football"):
        for name in _detect_entities(text, source_id, sport_override=sport):
            if name not in entities:
                entities.append(name)
        if entities:
            is_ambiguous_club = False

    # ── Subtitle gap-filling ───────────────────────────────────────────────────
    # Title is always the primary signal. Subtitle fills gaps only:
    #   sport=unknown → try subtitle for sport detection
    #   entities=[]  → try subtitle for entity detection
    # Subtitle cannot change an already-resolved sport value.
    # Football Maccabi clubs must still be checked first (same priority as in title).
    if sub_text:
        # Sport gap: subtitle fills sport only when title produced unknown.
        if sport == "unknown":
            if _has_football_maccabi_context(sub_text):
                sport = "football"
            else:
                sub_sport = _detect_sport(sub_text, source_id)
                if sub_sport == "unknown":
                    sub_sport = _club_person_sport(_resolve_text_entities(sub_text, source_id)) or "unknown"
                if sub_sport != "unknown":
                    sport = sub_sport
                elif _has_basketball_context(sub_text):
                    # Catch basketball context keywords not covered by _detect_sport
                    # (e.g. "הפועל ירושלים", position names like "גארד").
                    sport = "basketball"
                elif _has_football_context(sub_text):
                    sport = "football"

            # When subtitle resolved sport for an ambiguous-club title, re-resolve
            # the title's entities using that sport as taxonomy evidence.
            if sport != "unknown" and is_ambiguous_club:
                for name in _detect_entities(text, source_id, sport_override=sport):
                    if name not in entities:
                        entities.append(name)
                if entities:
                    is_ambiguous_club = False  # ambiguity resolved via subtitle

            # Re-apply entity-based sport inference and the cross-sport post-filter
            # after subtitle may have modified sport or entities.
            if sport == "unknown" and entities and not is_ambiguous_club:
                entity_sports = {legacy_sport(e) for e in entities} - {None}
                if len(entity_sports) == 1:
                    sport = next(iter(entity_sports))
            entities = _filter_entities_for_sport(entities, sport)

        # Entity gap: subtitle adds entities when title produced none.
        if not entities:
            # A person named only in the subtitle is often incidental: they prove
            # the sport (above) but do not make the article about their club (#259).
            sub_entities = _detect_entities(
                sub_text, source_id,
                sport_override=sport if sport in ("basketball", "football") else None,
                imply_clubs=False,
            )
            entities = _filter_entities_for_sport(sub_entities, sport)

    if sport == "basketball" and is_wnba_story(text, sub_text):
        # "wnba" contains "nba", and the title's bare city would read as the NBA club (#403).
        entities = without_nba_clubs(entities)
        league = "WNBA"
    else:
        league = _detect_league(text, sport, url=url, shared_context=f"{text} {sub_text}")

    # League gap from subtitle: when title produced no league, try subtitle.
    if league is None and sub_text:
        league = _detect_league(sub_text, sport, shared_context=f"{text} {sub_text}")

    # Entity-based league inference: Deni Avdija is an NBA player.
    # Titles that mention him without "NBA" (common in Hebrew news) still map to NBA.
    if sport == "basketball" and league is None and "Deni Avdija" in entities:
        league = "NBA"

    # Entity + Israeli context → Israeli Basketball League.
    # Example: "Maccabi sweeps Holon to set up Tel Aviv derby Finals" → Israeli Basketball League.
    if (
        sport == "basketball"
        and league is None
        and "Maccabi Tel Aviv Basketball" in entities
        and (_has(text, *_ISRAELI_BBALL_CONTEXT_KW) or _has(sub_text, *_ISRAELI_BBALL_CONTEXT_KW))
    ):
        league = "Israeli Basketball League"

    # Membership-derived league (issue #28): a resolved team/player still implies a
    # league even with no explicit competition keyword. Legacy DISPLAY field only —
    # primary_competition stays explicit-evidence-only in the facts stage.
    if league is None:
        league = _infer_league_from_membership(entities, sport)

    event_evidence = detect_article_event(text, sub_text or "", sport)
    event_type = event_evidence.event_type

    importance = _assign_importance(
        event_type, entities, league, event_certainty=event_evidence.certainty
    )
    confidence = _assign_confidence(sport, league, entities, event_type, source_id)
    tags = _collect_tags(sport, league, entities, event_type)
    if is_ambiguous_club:
        tags.append("ambiguous_club")

    return ClassificationResult(
        sport=sport,
        league=league,
        entities=entities,
        event_type=event_type,
        importance=importance,
        confidence=confidence,
        tags=tags,
        event_certainty=event_evidence.certainty,
    )
