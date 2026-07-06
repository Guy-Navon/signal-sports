"""
ArticleFacts consistency-validation stage (issue #28).

Turns a completed classification (the deterministic rules result, optionally
merged with an LLM proposal) into validated, evidence-backed facts:

  - ``primary_competition`` / ``article_competitions`` — competitions the article
    is *explicitly about* (competition keyword in title/subtitle/URL). Reach from
    mere team membership is NEVER persisted here — that is computed at scoring
    time (issue #29).
  - ``entity_ids`` — canonical taxonomy ids (``team:*`` / ``player:*`` / ``coach:*``).
  - ``classification_trace`` — deterministic evidence hits, LLM gate decision +
    reason, LLM raw proposal, normalization actions, and every conflict, each as
    ``{field, candidates, winner, rule}``.

Architecture contract (Intelligence Architecture v2):
  - THE LLM REDUCES UNCERTAINTY; IT DOES NOT DEFINE TRUTH. Deterministic evidence
    (source URL hint > explicit sport keywords, title over subtitle > competition
    keywords > entity-derived sport > LLM proposal) is weighted above the LLM.
  - Abstention is a success mode: an unresolvable sport/entity/competition triangle
    collapses to ``sport=unknown`` with the entity dropped-with-record.
  - Invariants enforced here: no persisted entity whose taxonomy sport differs from
    the article sport; no persisted competition whose sport differs from the
    article sport. Every auto-resolution or drop is recorded in the trace.
  - The LLM-disabled path produces the same schema (fewer resolved fields, more
    abstentions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.classification.llm_result import LLMClassificationResult
from app.ingestion.classifier import (
    ClassificationResult,
    _BASKETBALL_CTX_KW,
    _FOOTBALL_CTX_KW,
    _FOOTBALL_MACCABI_KW,
    _TENNIS_KW,
)
from app.taxonomy import (
    COMPETITIONS,
    TAXONOMY_VERSION,
    entity_by_legacy_name,
    legacy_sport,
    resolve_mention,
)


# ── Competition evidence keywords ─────────────────────────────────────────────
# Explicit competition NAMES only — never club names (a club → competition is a
# membership relation, resolved at scoring time, not explicit article evidence).

_COMPETITION_KEYWORDS: dict[str, tuple[str, ...]] = {
    # basketball
    "comp:eurocup": ("eurocup", "euro cup", "fiba europe cup", "יורוקאפ"),
    "comp:euroleague": ("euroleague", "יורוליג", "היורוליג"),
    "comp:nba": ("nba", "אן.בי.איי", "אן בי איי"),
    "comp:ibl": (
        "ליגת ווינר", "ווינר סל", "ליגת העל בכדורסל", "ליגת העל סל",
        "winner league", "ligat winner", "israeli basketball league",
        "super league basketball",
    ),
    "comp:acb": ("acb", "liga acb"),
    "comp:bsl": ("bsl", "turkish basketball"),
    "comp:greek_basket": ("greek basket", "basket league", "greek league"),
    "comp:lba": ("lba", "lega basket", "italian basketball"),
    "comp:lnb": ("lnb", "pro a", "french basketball"),
    # football
    "comp:ligat_haal": ("ליגת העל", "israeli premier league", "ligat haal"),
    "comp:ucl": ("champions league", "ליגת האלופות"),
    "comp:epl": ("premier league",),
    "comp:la_liga": ("la liga", "לה ליגה"),
    "comp:bundesliga": ("bundesliga", "בונדסליגה"),
    # tennis (tournaments)
    "comp:wimbledon": ("wimbledon", "וימבלדון"),
    "comp:roland_garros": ("roland garros", "french open", "רולאן גארוס"),
    "comp:us_open": ("us open",),
    "comp:australian_open": ("australian open", "אליפות אוסטרליה"),
}

# (competition_id, keyword) pairs, longest keyword first so a longer competition
# name claims its span before a shorter name contained inside it
# ("ליגת העל סל" (IBL) beats "ליגת העל" (Ligat ha'Al)).
_COMP_KEYWORD_PAIRS: list[tuple[str, str]] = sorted(
    ((cid, kw) for cid, kws in _COMPETITION_KEYWORDS.items() for kw in kws),
    key=lambda p: len(p[1]),
    reverse=True,
)

_COMP_ID_BY_DISPLAY: dict[str, str] = {c.display_en: c.id for c in COMPETITIONS.values()}


# ── Sport-evidence weights (issue #28 evidence order) ─────────────────────────
_W_SOURCE_HINT = 100
_W_TITLE_KEYWORD = 80
_W_SUBTITLE_KEYWORD = 60
_W_COMPETITION_KEYWORD = 55
_W_ENTITY_DERIVED = 40
_W_LLM = 20

_EXPLICIT_SPORT_SOURCES = frozenset(
    {"source_url_hint", "title_keyword", "subtitle_keyword", "competition_keyword"}
)


@dataclass
class ArticleFacts:
    """Validated facts + trace ready to persist on an Article."""
    sport: str
    league: Optional[str]
    entities: list[str]
    primary_competition: Optional[str]
    article_competitions: list[str]
    entity_ids: list[str]
    conflicts: list[dict] = field(default_factory=list)
    trace: dict = field(default_factory=dict)
    taxonomy_version: int = TAXONOMY_VERSION


# ── Keyword helpers ───────────────────────────────────────────────────────────

def _first_keyword(text: str, keywords) -> Optional[str]:
    for kw in keywords:
        if kw in text:
            return kw
    return None


def _overlaps(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    s, e = span
    return any(s < te and ts < e for ts, te in taken)


def _scan_competitions(text: str) -> list[str]:
    """Return explicit competition ids mentioned in ``text`` (longest-match, ordered)."""
    if not text:
        return []
    taken: list[tuple[int, int]] = []
    hits: list[tuple[int, str]] = []  # (position, comp_id)
    seen: set[str] = set()
    for comp_id, kw in _COMP_KEYWORD_PAIRS:
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx == -1:
                break
            span = (idx, idx + len(kw))
            if not _overlaps(span, taken):
                taken.append(span)
                if comp_id not in seen:
                    seen.add(comp_id)
                    hits.append((idx, comp_id))
            start = idx + 1
    hits.sort(key=lambda h: h[0])
    return [comp_id for _, comp_id in hits]


# ── Sport evidence ────────────────────────────────────────────────────────────

def _collect_sport_evidence(
    title_l: str,
    sub_l: str,
    source_sport_hint: Optional[str],
    competition_ids: list[str],
    entities: list[str],
    llm_raw: Optional[LLMClassificationResult],
) -> list[dict]:
    """Weighted sport-evidence candidates, strongest first. Bare club-family names
    are NOT sport evidence (removed entity→basketball bias)."""
    evidence: list[dict] = []

    if source_sport_hint:
        evidence.append({"sport": source_sport_hint, "source": "source_url_hint",
                         "weight": _W_SOURCE_HINT, "detail": source_sport_hint})

    _title_sets = (
        ("basketball", _BASKETBALL_CTX_KW),
        ("football", _FOOTBALL_CTX_KW + _FOOTBALL_MACCABI_KW),
        ("tennis", _TENNIS_KW),
    )
    for sport, kws in _title_sets:
        kw = _first_keyword(title_l, kws)
        if kw:
            evidence.append({"sport": sport, "source": "title_keyword",
                             "weight": _W_TITLE_KEYWORD, "detail": kw})
    for sport, kws in _title_sets:
        kw = _first_keyword(sub_l, kws)
        if kw:
            evidence.append({"sport": sport, "source": "subtitle_keyword",
                             "weight": _W_SUBTITLE_KEYWORD, "detail": kw})

    for cid in competition_ids:
        comp = COMPETITIONS.get(cid)
        if comp:
            evidence.append({"sport": comp.sport, "source": "competition_keyword",
                             "weight": _W_COMPETITION_KEYWORD, "detail": cid})

    entity_sports = {legacy_sport(e) for e in entities} - {None}
    if len(entity_sports) == 1:
        evidence.append({"sport": next(iter(entity_sports)), "source": "entity_derived",
                         "weight": _W_ENTITY_DERIVED, "detail": ",".join(entities)})

    if llm_raw is not None and llm_raw.sport and llm_raw.sport != "unknown":
        evidence.append({"sport": llm_raw.sport, "source": "llm",
                         "weight": _W_LLM, "detail": "llm_proposal"})

    evidence.sort(key=lambda e: e["weight"], reverse=True)
    return evidence


def _sport_has_explicit_support(evidence: list[dict], sport: str) -> bool:
    return any(
        e["sport"] == sport and e["source"] in _EXPLICIT_SPORT_SOURCES
        for e in evidence
    )


# ── Public API ────────────────────────────────────────────────────────────────

def build_article_facts(
    *,
    title: str,
    subtitle: Optional[str],
    url: str,
    source_id: str,
    source_sport_hint: Optional[str],
    result: ClassificationResult,
    llm_raw: Optional[LLMClassificationResult] = None,
    gate_should_call: Optional[bool] = None,
    gate_reason: Optional[str] = None,
    classified_by: str = "rules",
) -> ArticleFacts:
    """Validate a completed classification into evidence-backed ArticleFacts.

    ``result`` is the authoritative (rules-only or LLM-merged) classification.
    This stage never re-runs sport detection; it validates the sport/entity/
    competition triangle, records conflicts, and derives the persistable facts.
    """
    title_l = (title or "").lower()
    sub_l = (subtitle or "").lower()

    sport = result.sport
    league = result.league
    conflicts: list[dict] = []

    # ── Explicit competition evidence ────────────────────────────────────────
    # Article-level text only (title + subtitle). URLs are deliberately NOT scanned:
    # short competition tokens ("acb", "nba", "lnb", "bsl") would false-match slugs.
    explicit_comp_ids: list[str] = []
    for cid in _scan_competitions(title_l) + _scan_competitions(sub_l):
        if cid not in explicit_comp_ids:
            explicit_comp_ids.append(cid)

    sport_evidence = _collect_sport_evidence(
        title_l, sub_l, source_sport_hint, explicit_comp_ids, result.entities, llm_raw
    )

    # ── Entity validation (invariant: entity sport == article sport) ─────────
    kept_entities: list[str] = []
    dropped_entities: list[dict] = []
    for e in result.entities:
        e_sport = legacy_sport(e)
        if sport in ("basketball", "football") and e_sport is not None and e_sport != sport:
            dropped_entities.append({"entity": e, "entity_sport": e_sport, "article_sport": sport})
        else:
            kept_entities.append(e)

    # Abstention: entities were dropped for conflicting with a sport that has no
    # explicit support of its own — the article sport is not trustworthy. Collapse
    # to unknown rather than persist a guessed sport (abstention beats guessing).
    if dropped_entities and not _sport_has_explicit_support(sport_evidence, sport):
        conflicts.append({
            "field": "sport",
            "candidates": sport_evidence,
            "winner": "unknown",
            "rule": "abstain_unresolvable_entity_sport_conflict",
        })
        sport = "unknown"
        league = None
        kept_entities = []
        # Every dropped entity is part of the abstention.
        for d in dropped_entities:
            conflicts.append({
                "field": "entity", "candidates": [d["entity"]],
                "winner": None, "rule": "dropped_on_abstention",
            })
    else:
        for d in dropped_entities:
            conflicts.append({
                "field": "entity",
                "candidates": [f'{d["entity"]} (sport={d["entity_sport"]})'],
                "winner": sport,
                "rule": "entity_dropped_sport_conflict",
            })

    # ── Sport conflict recording (auto-resolved cases too) ───────────────────
    distinct_sports = {e["sport"] for e in sport_evidence}
    if sport != "unknown" and len(distinct_sports) > 1:
        winning = next((e for e in sport_evidence if e["sport"] == sport), None)
        conflicts.append({
            "field": "sport",
            "candidates": sport_evidence,
            "winner": sport,
            "rule": f'{winning["source"]}_outweighs' if winning else "weighted_evidence",
        })

    # ── Competition validation (invariant: competition sport == article sport) ─
    primary_competition: Optional[str] = None
    dropped_comps: list[dict] = []
    same_sport_comps = [
        cid for cid in explicit_comp_ids
        if sport == "unknown" or COMPETITIONS[cid].sport == sport
    ]
    for cid in explicit_comp_ids:
        if cid not in same_sport_comps:
            dropped_comps.append({"competition": cid, "competition_sport": COMPETITIONS[cid].sport,
                                  "article_sport": sport})
            conflicts.append({
                "field": "competition",
                "candidates": [f'{cid} (sport={COMPETITIONS[cid].sport})'],
                "winner": sport,
                "rule": "competition_dropped_sport_conflict",
            })

    # primary_competition = the (explicitly-evidenced) competition matching the
    # legacy league. When league is membership/context-inferred rather than
    # explicitly named, it is NOT in the explicit hits → primary stays None.
    if league is not None:
        league_cid = _COMP_ID_BY_DISPLAY.get(league)
        if league_cid in same_sport_comps:
            primary_competition = league_cid

    # Contract: league == display_en(primary_competition) when a primary is set.
    if primary_competition is not None:
        league = COMPETITIONS[primary_competition].display_en

    article_competitions = [cid for cid in same_sport_comps if cid != primary_competition]

    # ── entity_ids + normalization trace ─────────────────────────────────────
    entity_ids: list[str] = []
    alias_to_id: list[dict] = []
    for e in kept_entities:
        ent = entity_by_legacy_name(e)
        if ent is not None and ent.id not in entity_ids:
            entity_ids.append(ent.id)
            alias_to_id.append({"legacy_name": e, "id": ent.id})

    rejected_mentions: list[str] = []
    if llm_raw is not None:
        ctx = sport if sport in ("basketball", "football") else None
        for mention in llm_raw.entities:
            if resolve_mention(mention, ctx) is None:
                rejected_mentions.append(mention)

    # ── Trace assembly ────────────────────────────────────────────────────────
    llm_trace: Optional[dict] = None
    if gate_should_call is not None or llm_raw is not None:
        llm_trace = {
            "gate_should_call": gate_should_call,
            "gate_reason": gate_reason,
            "classified_by": classified_by,
            "proposal": None,
        }
        if llm_raw is not None:
            llm_trace["proposal"] = {
                "sport": llm_raw.sport,
                "league": llm_raw.league,
                "event_type": llm_raw.event_type,
                "importance": llm_raw.importance,
                "confidence": llm_raw.confidence,
                "entities": list(llm_raw.entities),
                "reason": llm_raw.reason,
            }

    trace = {
        "taxonomy_version": TAXONOMY_VERSION,
        "sport": {"final": sport, "evidence": sport_evidence},
        "competitions": {
            "primary": primary_competition,
            "article": article_competitions,
            "explicit_hits": explicit_comp_ids,
            "dropped": dropped_comps,
        },
        "entities": {
            "resolved_ids": entity_ids,
            "alias_to_id": alias_to_id,
            "dropped": dropped_entities,
            "rejected_llm_mentions": rejected_mentions,
        },
        "llm": llm_trace,
        "conflicts": conflicts,
    }

    return ArticleFacts(
        sport=sport,
        league=league,
        entities=kept_entities,
        primary_competition=primary_competition,
        article_competitions=article_competitions,
        entity_ids=entity_ids,
        conflicts=conflicts,
        trace=trace,
        taxonomy_version=TAXONOMY_VERSION,
    )
