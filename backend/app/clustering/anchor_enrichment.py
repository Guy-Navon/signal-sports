"""Anchor enrichment — the ingestion-time stage that makes pair clustering cheap (#141).

The required implementation shape:

    Validation runs ONCE, at ingestion or enrichment time.
    Pairwise clustering consumes persisted ACCEPTED anchors only.
    It must never invoke a model or morphological analyzer per pair.

So `enrich_article_anchors()` runs the pipeline — generate candidates → validate → keep the
accepted, story-identifying ones — and returns a small persistable record. `accepted_anchor_keys()`
is the ONLY thing the matcher calls, and it just reads that record.

A validator upgrade bumps `validator_version`; a guarded re-enrichment/backfill can then refresh
stored rows WITHOUT re-ingesting the articles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from app.clustering.anchor_contract import AnchorValidator
from app.clustering.anchor_normalization import transliteration_skeleton
from app.clustering.anchor_validators import is_future_verb_inflection
from app.clustering.anchors import _candidate_forms, build_name_lexicon, generate_candidates
from app.clustering.tokens import tokenize
from app.taxonomy.entities import ENTITIES


def _match_keys(anchor: str) -> frozenset[str]:
    """All forms an anchor may match on. Hebrew glues prepositions onto names, so sport5's
    'מהנקינס' must match ynet's 'הנקינס'. A stripped form is an ADDITIONAL key, never a
    replacement — stripping in place corrupts real names whose first letter is a prefix letter
    (הנקינס → נקינס). Canonical taxonomy ids are matched verbatim.

    #137: the transliteration skeleton joins as a NAMESPACED key ("translit:…"), so
    variant spellings of one foreign name (סטורנסקי / סטרונסקי — vav metathesis) meet on
    their shared skeleton. The namespace means a skeleton can only ever match another
    skeleton — an aggressive normalized form can never collide with somebody's RAW name.
    Scope holds by construction: only VALIDATED anchors reach this function, so
    normalization cannot convert an unvalidated candidate into trusted evidence."""
    if anchor.startswith(("player:", "coach:", "team:", "comp:")):
        return frozenset({anchor})
    # B2 (#364): a future-tense verb is not a name, even when it was stored as one
    # ("ייעדר"); drop it, keep the name part of "קורטואה ייעדר".
    parts = anchor.split()
    names = [p for p in parts if not is_future_verb_inflection(p)]
    if not names:
        return frozenset()
    if len(names) != len(parts):
        anchor = " ".join(names)
    keys = {anchor}
    for part in anchor.split():
        keys.update(_candidate_forms(part))
    keys.add(f"translit:{transliteration_skeleton(anchor)}")
    return frozenset(keys)


@dataclass(frozen=True)
class StoredAnchor:
    """One accepted, story-identifying anchor, as persisted on the article row."""

    anchor: str            # the matching key (canonical id, or normalized surface)
    role: str
    source: str            # title | subtitle
    validator_id: str
    reason_code: str

    def to_json(self) -> dict:
        return {
            "anchor": self.anchor, "role": self.role, "source": self.source,
            "validator_id": self.validator_id, "reason_code": self.reason_code,
        }


# Only these roles are story-identifying (a role-holder or opponent is not the subject).
_STORY_IDENTIFYING_ROLES = frozenset({"subject", "quoted", "unknown"})


def enrich_article_anchors(
    title: str,
    subtitle: str,
    validator: AnchorValidator,
    *,
    article_id: str = "",
    population: Optional[Sequence] = None,
    candidate_set_id: str = "",
) -> tuple[list[StoredAnchor], str]:
    """Generate → validate → keep. Returns (accepted story anchors, validator_version).

    `population` is the candidate set the name-lexicon is corroborated against (mirrors #135's
    candidate-scoped DF). None means no cross-article corroboration — title/subtitle only.
    """
    lexicon = build_name_lexicon(population) if population else None
    candidates = generate_candidates(
        title, subtitle, lexicon, article_id=article_id, candidate_set_id=candidate_set_id,
    )
    accepted: list[StoredAnchor] = []
    seen: set[str] = set()
    for c in candidates:
        if c.role not in _STORY_IDENTIFYING_ROLES:
            continue                       # role-holder / opponent: never story identity
        decision = validator.validate(c)
        if not decision.is_accepted:
            continue                       # rejected OR abstained — fail closed
        key = decision.normalized_anchor or c.normalized
        if key in seen:
            continue
        seen.add(key)
        accepted.append(StoredAnchor(
            anchor=key, role=c.role, source=c.source,
            validator_id=decision.validator_id, reason_code=decision.reason_code,
        ))
    return accepted, validator.validator_version


def accepted_anchor_keys(stored: Optional[list]) -> frozenset[str]:
    """The matcher's ONLY entry point. Pure read over persisted anchors — no model, no analyzer.

    Accepts either raw JSON dicts (from the DB) or StoredAnchor objects.
    """
    if not stored:
        return frozenset()
    keys: set[str] = set()
    for a in stored:
        anchor = a.anchor if isinstance(a, StoredAnchor) else (
            a.get("anchor") if isinstance(a, dict) else None)
        if anchor:
            keys |= _match_keys(anchor)
    return frozenset(keys)


def shared_stored_anchors(a, b) -> frozenset[str]:
    """Story anchors two articles share, from PERSISTED records. Deterministic and cheap."""
    return accepted_anchor_keys(a) & accepted_anchor_keys(b)


def _keys_with_titleness(stored) -> dict[str, bool]:
    """key -> "this key is backed by a TITLE-borne anchor on this side"."""
    out: dict[str, bool] = {}
    for x in stored or ():
        d = x.to_json() if isinstance(x, StoredAnchor) else (x if isinstance(x, dict) else None)
        if not d or not d.get("anchor"):
            continue
        title_borne = d.get("source") == "title"
        for k in _match_keys(d["anchor"]):
            out[k] = out.get(k, False) or title_borne
    return out


def shared_subject_anchors(a, b) -> frozenset[str]:
    """Shared anchors that are TITLE-borne on at least one side.

    The manual component review (#124) found the counterexample class: two
    unrelated multi-club negotiation ROUNDUPS merged on an incidental club
    mention ("אסטון") that appeared only in both SUBTITLES, at jaccard 0.016.
    A story's actual subject gets HEADLINED by at least one newsroom;
    incidental mentions live in subordinate clauses. Requiring title-ness on
    one side keeps every frozen must-merge (the hardest Hankins member names
    the player only in its subtitle — but its PEERS headline him) and kills
    the roundup bridge structurally, with no threshold.
    """
    ka, kb = _keys_with_titleness(a), _keys_with_titleness(b)
    return frozenset(k for k in ka.keys() & kb.keys() if ka[k] or kb[k])


def story_tokens_beyond_clubs(rare: Sequence[str], shared: frozenset[str]) -> tuple[str, ...]:
    """B1 (#364): the shared discriminative tokens that are NOT part of a shared club's name.

    A canonical club id appears in every story about that club, exactly like a competition, so
    on its own it does not say which story two articles share ("Red Star wants €250k for
    Glazer" / "Tsunami agrees with Maccabi Haifa"). A team-only rescue needs story-specific
    tokens beyond it (the matcher asks for the Tier C count); the club's own name ("נתניה",
    "בקליבלנד") does not count."""
    club_words: set[str] = set()
    for key in shared:
        ent = ENTITIES.get(key)
        if ent is not None:
            for alias in ent.aliases:
                club_words |= tokenize(alias)
    return tuple(t for t in rare if not (set(_candidate_forms(t)) | {t}) & club_words)


_PERSON_PREFIXES = ("player:", "coach:", "exec:")


def conflicting_clubs(a, b, shared: frozenset[str]) -> bool:
    """B3 (#364): True when a rescue that rests on a registered PERSON (a canonical player,
    coach or executive id) joins two stories naming different clubs. A name says who; when both
    articles also name canonical clubs and those clubs do not overlap — the person's own club
    aside — they report different developments ("Philadelphia courts LeBron" / "Portland tries
    to sign LeBron"). False when no registered person is shared, when the rescue already shares
    a club, or when either side names no club, so every other rescue is unchanged."""
    if not any(k.startswith(_PERSON_PREFIXES) for k in shared):
        return False
    if any(k.startswith("team:") for k in shared):
        return False
    own = {
        ENTITIES[k].team_id for k in shared
        if k.startswith(_PERSON_PREFIXES) and k in ENTITIES and ENTITIES[k].team_id
    }
    clubs_a = {s.get("anchor") for s in a if str(s.get("anchor", "")).startswith("team:")} - own
    clubs_b = {s.get("anchor") for s in b if str(s.get("anchor", "")).startswith("team:")} - own
    return bool(clubs_a) and bool(clubs_b) and not (clubs_a & clubs_b)


def hard_gate_population(anchor, peers: Sequence, cfg) -> list:
    """The candidate population an article's anchors are corroborated against.

    Exactly the peers pair evaluation will compare against — the hard-gate-compatible
    window (#135's candidate scoping). Shared by the ingestion stage and the guarded
    backfill so the two can never drift.
    """
    from app.clustering.event_states import (
        is_clusterable_state, is_in_play, states_compatible, within_time_window,
    )
    from app.clustering.matcher import sports_hard_reject

    if not is_clusterable_state(anchor.event_type):
        return []
    return [
        p for p in peers
        if is_clusterable_state(p.event_type)
        and states_compatible(p.event_type, anchor.event_type)
        and not is_in_play(p.title, p.subtitle)
        and within_time_window(p.published_at, anchor.published_at, anchor.event_type, cfg)
        and not sports_hard_reject(p, anchor)
    ]
