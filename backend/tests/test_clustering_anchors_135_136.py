"""#135 (candidate-scoped evidence frequency) + #136 (story-identifying named anchors).

BOTH ARE DIAGNOSTIC-ONLY. Neither is wired into `match_pair`; neither may change default
clustering behavior. Only #126 may.

They share the adjudicated pair corpus and are asserted SEPARATELY and IN COMBINATION, so
neither silently absorbs the other:

    #135 asks: can evidence frequency identify useful tokens inside a VALID candidate
               population? (It restores the NAME. It does NOT remove the JUNK.)
    #136 asks: can we build the primitive that separates named story identity from arbitrary
               rarity? (It finds the names. It is NOT sufficient on its own.)
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.clustering.anchors import (
    Anchor,
    build_name_lexicon,
    generate_anchor_candidates,
    shared_anchor_candidates,
    shared_anchors,
    validate_anchors,
)
from app.clustering.candidate_scope import (
    CANDIDATE_GATES,
    candidate_population,
    in_candidate_population,
    scoped_evidence,
)
from app.clustering.config import DEFAULT_CONFIG as CFG
from app.clustering.contract import ClusterInput

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def cases():
    with (FIX / "feed_dedup_cases.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def _inp(raw):
    return ClusterInput(
        id=raw["id"], source=raw["source"], title=raw["title"],
        subtitle=raw.get("subtitle", ""),
        published_at=datetime.fromisoformat(raw["published_at"].replace("Z", "+00:00")),
        sport=raw["sport"], event_type=raw["event_type"],
        event_certainty=raw.get("event_certainty"),
        entity_ids=tuple(raw.get("entity_ids") or ()),
        primary_competition=raw.get("primary_competition"),
    )


def _group(cases, gid):
    return [_inp(a) for a in
            next(g for g in cases["duplicate_groups"] if g["id"] == gid)["articles"]]


def _art(i, title, sub="", state="signing", src="ynet_sport", hours=0):
    return ClusterInput(
        id=i, source=src, title=title, subtitle=sub,
        published_at=datetime(2026, 7, 12, 8, 0) + timedelta(hours=hours),
        sport="basketball", event_type=state, event_certainty="confirmed",
        entity_ids=("team:maccabi_tlv_bb",), primary_competition="comp:euroleague",
    )


# ══════════════════════════════════════════════════════════════════════════════
# #135 — candidate-scoped evidence frequency
# ══════════════════════════════════════════════════════════════════════════════

class TestTheCandidatePopulationIsDefinedByEXISTINGGates:
    """No new boundary is invented. Every gate below ALREADY runs in `match_pair` before
    similarity is computed — which is exactly why there is NO TEMPORAL CLIFF here: the
    population uses `within_time_window`, the same gate applied to the pair itself."""

    def test_the_gates_are_the_matchers_own(self):
        assert CANDIDATE_GATES == (
            "clusterable_event_state", "compatible_event_state", "not_in_play",
            "within_time_window", "sport_not_hard_rejected",
        )

    def test_an_incompatible_event_state_is_not_a_candidate(self):
        anchor = _art("a", "ים מדר חתם במכבי", state="signing")
        other = _art("b", "מדר: עוזב בראש מורם", state="news")
        assert not in_candidate_population(other, anchor, CFG)

    def test_an_out_of_window_article_is_not_a_candidate(self):
        anchor = _art("a", "ים מדר חתם במכבי", state="signing")
        far = _art("b", "ים מדר חתם במכבי", state="signing", hours=200)
        assert not in_candidate_population(far, anchor, CFG)

    def test_the_population_is_source_agnostic(self):
        """Deliberately NOT filtered by source. Source identity is a property of a PAIR. If the
        DF universe changed with the asking source, a token's frequency would not be a shared
        fact and the evidence would not be comparable."""
        anchor = _art("a", "ים מדר חתם במכבי", src="ynet_sport")
        same = _art("b", "ים מדר חתם במכבי", src="ynet_sport")
        assert in_candidate_population(same, anchor, CFG)


class TestTheNameIsRestoredAndTheTemplateIsNot:
    """THE #135 RESULT. On the live corpus: `מדר` goes df 13 → 4 and becomes discriminative,
    while `חתם` ('signed') goes 17 → 8 and correctly REMAINS a template word.

    Verifying that action templates stay generic is an ACCEPTANCE REQUIREMENT, not a happy
    accident: a mechanism that made every token discriminative would "fix" Madar by breaking
    everything."""

    def _pop(self):
        # A signing window: three reports of one signing, plus unrelated signings that also
        # say "חתם". This is the shape that makes מדר look common and חתם look identifying.
        arts = [
            _art("m1", 'ים מדר חתם במכבי ת"א', src="ynet_sport"),
            _art("m2", 'היקר בתולדותיה: ים מדר חתם רשמית במכבי ת"א', src="sport5_sport", hours=2),
            _art("m3", 'מכבי ת"א הציגה את ים מדר', src="walla_sport", hours=3),
            _art("o1", "ג'סטין לואיס חתם במכבי רמת גן", src="sport5_sport", hours=1),
            _art("o2", "גרג לי חתם בהפועל חולון", src="walla_sport", hours=4),
            _art("o3", "אור רויזמן חתם בהפועל כפר סבא", src="ynet_sport", hours=5),
            _art("o4", "ניר ברדע חתם לשנתיים בבני יהודה", src="sport5_sport", hours=6),
        ]
        return arts

    def test_the_subjects_name_becomes_discriminative(self):
        arts = self._pop()
        se = scoped_evidence(arts[0], arts, CFG)
        assert se.df.is_discriminative("מדר", CFG), (
            "the token that NAMES the story's subject must be usable as evidence"
        )

    def test_the_action_template_stays_non_discriminative(self):
        arts = self._pop()
        se = scoped_evidence(arts[0], arts, CFG)
        assert not se.df.is_discriminative("חתם", CFG), (
            "'חתם' (signed) is what EVERY signing says. If scoping made it identifying, the "
            "mechanism would be manufacturing evidence, not finding it."
        )

    def test_every_discriminative_token_is_explainable(self):
        """#135 requires recording WHY a token survived — a merge we cannot explain is a merge
        we cannot debug."""
        arts = self._pop()
        se = scoped_evidence(arts[0], arts, CFG)
        ex = se.explain("מדר", CFG)
        assert ex["df_scoped"] >= 1 and ex["population"] == len(candidate_population(
            arts[0], arts, CFG))
        assert ex["gates"] == list(CANDIDATE_GATES)

    def test_no_temporal_cliff_is_introduced(self):
        """The population is bounded by the SAME `within_time_window` gate the pair already
        passes. A pair admitted by the window cannot have its evidence judged against a
        different window, so no new discontinuity exists."""
        anchor = _art("a", "ים מדר חתם")
        just_in = _art("b", "ים מדר חתם", hours=23)
        just_out = _art("c", "ים מדר חתם", hours=25)
        from app.clustering.event_states import within_time_window

        assert in_candidate_population(just_in, anchor, CFG) is within_time_window(
            just_in.published_at, anchor.published_at, anchor.event_type, CFG)
        assert in_candidate_population(just_out, anchor, CFG) is within_time_window(
            just_out.published_at, anchor.published_at, anchor.event_type, CFG)


# ══════════════════════════════════════════════════════════════════════════════
# #136 — story-identifying named anchors
# ══════════════════════════════════════════════════════════════════════════════

class TestTheAnchorContract:
    """Stable by design: #137 folds spelling variants WITHOUT changing this shape, and
    taxonomy growth only ever fills in `entity_id`."""

    def test_an_anchor_carries_every_contracted_field(self):
        a = generate_anchor_candidates('מכבי ת"א נפרדה מזאק הנקינס')[0]
        assert isinstance(a, Anchor)
        for f in ("raw", "normalized", "anchor_type", "entity_id", "source",
                  "confidence", "evidence", "role"):
            assert hasattr(a, f), f

    def test_an_anchor_does_NOT_require_taxonomy_resolution(self):
        """The whole reason this layer exists: the taxonomy resolves ZERO Israeli players
        (3/257 corpus articles carry any player entity — LeBron and Deni)."""
        anchors = generate_anchor_candidates('ים מדר חתם במכבי ת"א')
        assert anchors, "Madar must anchor even though the taxonomy has never heard of him"
        assert all(a.entity_id is None for a in anchors if "מדר" in a.normalized)

    def test_the_extraction_source_is_recorded(self):
        """#137 and #124 both need to know WHERE the evidence lived."""
        anchors = generate_anchor_candidates("בדרך לרכש כפול: מכבי תל אביב נפרדה מאחד משחקניה",
                                  "הסנטר זאק הנקינס עוזב")
        assert any(a.source == "subtitle" for a in anchors)

    def test_prefix_stripping_ADDS_a_key_and_never_replaces_the_name(self):
        """Hebrew glues prepositions onto names, but stripping in place is destructive: the
        first letter of הנקינס, מכבי, ברצלונה and כריס is ALSO a prefix letter."""
        a = Anchor(raw="הנקינס", normalized="הנקינס", anchor_type="person", entity_id=None,
                   source="title", confidence="strong", evidence="t", role="unknown")
        assert "name:הנקינס" in a.keys(), "the real name must survive"

    def test_a_canonical_id_wins_when_available(self):
        a = Anchor(raw="עודד קטש", normalized="coach:oded_kattash", anchor_type="person",
                   entity_id="coach:oded_kattash", source="title", confidence="canonical",
                   evidence="taxonomy:coach", role="role_holder")
        assert a.keys() == frozenset({"coach:oded_kattash"})


class TestAnchorsRecoverTheDuplicateGroups:
    def test_the_subtitle_only_hankins_card_anchors(self, cases):
        """THE hardest card: its TITLE names no player ('נפרדה מאחד משחקניה'). If the anchor
        layer cannot reach into the subtitle, the user's feed is not actually fixed."""
        arts = _group(cases, "dup_hankins_release")
        lex = build_name_lexicon(arts)
        ih = next(a for a in arts if a.source == "israel_hayom_sport")
        ynet = next(a for a in arts if a.source == "ynet_sport")
        assert "הנקינס" not in ih.title
        sa = shared_anchor_candidates(
            generate_anchor_candidates(ih.title, ih.subtitle, lex),
            generate_anchor_candidates(ynet.title, ynet.subtitle, lex))
        assert sa, "the subtitle-only card must still share an anchor CANDIDATE"

    def test_a_lone_mention_anchors_via_the_candidate_population(self, cases):
        """sport5 writes 'נפרדה מהנקינס' — a LONE token, no bigram partner. Within-article
        corroboration cannot help; the name is never introduced there. The window can: ynet
        introduces him properly, so the population knows the name.

        Note this mirrors #135 exactly — names and evidence frequency are both corroborated by
        the same candidate population. One idea, applied twice."""
        arts = _group(cases, "dup_hankins_release")
        sport5 = next(a for a in arts if a.source == "sport5_sport")
        alone = generate_anchor_candidates(sport5.title, sport5.subtitle)          # no lexicon
        with_pop = generate_anchor_candidates(sport5.title, sport5.subtitle,
                                   build_name_lexicon(arts))            # with the population
        assert len(with_pop) > len(alone)


class TestTheRequiredNegatives:
    """A shared anchor is NECESSARY, never SUFFICIENT."""

    def test_same_coach_unrelated_stories(self):
        """'הקבוצה של איטודיס' — a possessive marks the coach as a ROLE-HOLDER of the club,
        not the subject of the story. This construction bridged three unrelated articles.

        It never forms a bigram (של is vocabulary), so it arrives via the corroborated-single
        layer — which is exactly why role inference must run THERE too. It originally did not,
        and that was a real defect."""
        a = generate_anchor_candidates("הפועל ת\"א צפויה לצרף את סטורנסקי",
                            "צפוי להצטרף לקבוצה של איטודיס")
        b = generate_anchor_candidates("נשאר אדום: אלייז'ה בראיינט האריך חוזה",
                            "הקבוצה של איטודיס שמחה")
        lex = frozenset({"איטודיס"})
        a = generate_anchor_candidates("הפועל ת\"א צפויה לצרף את סטורנסקי",
                            "צפוי להצטרף לקבוצה של איטודיס", lex)
        b = generate_anchor_candidates("בראיינט האריך חוזה", "הקבוצה של איטודיס שמחה", lex)
        assert not shared_anchor_candidates(a, b), (
            "a coach is a club-level token, not a story anchor — and the GENERATOR itself must "
            "get this right, because role is grammatical context the validator cannot recover"
        )

    def test_a_role_holder_is_not_story_identifying(self):
        coach = Anchor(raw="איטודיס", normalized="איטודיס", anchor_type="person",
                       entity_id=None, source="subtitle", confidence="weak",
                       evidence="t", role="role_holder")
        assert not coach.is_story_identifying()

    def test_an_opponent_is_not_story_identifying(self):
        opp = Anchor(raw="ריאל מדריד", normalized="ריאל מדריד", anchor_type="club",
                     entity_id=None, source="title", confidence="strong",
                     evidence="t", role="opponent")
        assert not opp.is_story_identifying()

    def test_a_competition_can_never_be_a_person_anchor(self):
        """'יורוליג' is a KNOWN entity kind and is never what a story is about — every
        EuroLeague story shares it. Letting it act as an anchor merged Bryant's extension
        with Otooru's."""
        a = generate_anchor_candidates("נשאר אדום: בראיינט האריך חוזה", "אחרי עונת שיא ביורוליג")
        b = generate_anchor_candidates("ללא סעיף יציאה: אוטורו חתם על חוזה חדש",
                            "לאחר עונת השיא ביורוליג")
        assert "name:יורוליג" not in {k for x in a for k in x.keys()}

    def test_shared_template_language_without_a_named_subject(self):
        """The formulaic-negotiation pair — the ONLY one that survived containment."""
        a = generate_anchor_candidates('מצפון לדרום? ארון ווילר במו"מ עם אילת')
        b = generate_anchor_candidates('הפועל חולון במו"מ עם שני שחקנים')
        assert not shared_anchor_candidates(a, b), "במו\"מ / בשיחות is not an identity"


class TestSharedIdentityIsNotEnough:
    """The Diarra case, as a POSITIVE demonstration of the product policy.

    Both articles genuinely share the anchor `דיארה` — and they MUST NOT collapse, because
    they contradict each other. This is the empirical proof that a shared anchor cannot be
    sufficient: something else must still prevent the merge.
    """

    def test_the_material_update_pair_really_does_share_an_anchor(self):
        a = generate_anchor_candidates("עמדה במצוקה: אקס הפועל תל אביב מתרחק מהקבוצה",
                            "האדומים לא ירדו מטימוקו דיארה")
        b = generate_anchor_candidates("הפור נפל? דיווח: טיימוקו דיארה לא יחתום בהפועל תל אביב",
                            "הקשר ממאלי נמצא על סף חתימה בקאסימפשה")
        assert shared_anchor_candidates(a, b), (
            "they DO share the subject — which is exactly why 'shared anchor' cannot be the "
            "whole rule. Same subject, contradictory updates, must not collapse. This is an "
            "identity SUCCESS and a compatibility FAILURE; it belongs to the material-update "
            "stage, not to anchor extraction."
        )


class TestTheKnownGap:
    """HONEST: the name/not-name discriminator is not finished, and this records the gap
    rather than hiding it behind a hand-tuned stopword list.

    Three ordinary Hebrew words still extract as names on the live corpus — `אדום` (red),
    `שיא` (record), `הכל` (everything) — and they produce 3 over-merges. Adding those three
    words to fit this corpus would be the SAME mistake as hand-adding four player names to the
    taxonomy: it fits this corpus and fails the next.

    Closing it needs a real Hebrew common-word resource. That is a decision, not a patch.
    """

    def test_a_candidate_span_is_NOT_an_anchor(self):
        """THE VALIDATION BOUNDARY. The generator may propose 'נשאר אדום'. It may NOT make
        אדום clustering evidence."""
        cands = generate_anchor_candidates("נשאר אדום: אלייז'ה בראיינט האריך חוזה")
        assert cands, "the generator favours recall and proposes freely"
        assert validate_anchors(cands) == (), (
            "…and NOTHING heuristic is validated. אדום cannot over-merge — not because it was "
            "added to a stoplist (that would fit this corpus and fail the next), but because "
            "no validator has proven any of these spans name-like."
        )

    def test_the_validator_abstains_rather_than_guessing(self):
        """Abstention beats incorrect clustering. Passing candidates through would turn the
        frozen corpus green while leaving the abstraction broken."""
        a = generate_anchor_candidates("נשאר אדום: אלייז'ה בראיינט האריך חוזה")
        b = generate_anchor_candidates("גם דן אוטורו האריך חוזה", "נשאר אדום גם הוא")
        assert shared_anchor_candidates(a, b), (
            "the leak is REAL at candidate level: 'נשאר אדום' ('stayed red') is verb+adjective "
            "and the generator proposes it as a name in BOTH articles"
        )
        assert shared_anchors(a, b) == (), "…and it CANNOT reach merge evidence"

    def test_a_canonical_taxonomy_match_IS_validated(self):
        """Canonical matches need no further inference — they are already proven."""
        cands = generate_anchor_candidates("עודד קטש חתם במכבי תל אביב")
        canonical = [c for c in cands if c.confidence == "canonical"]
        assert canonical, "the taxonomy knows Kattash"
        assert validate_anchors(cands) == tuple(canonical)

    def test_the_leak_is_in_the_BIGRAM_RULE_itself(self):
        """The defect, located precisely — and NOT where I first assumed.

        I expected the leak to come from Layer 3 (lexicon corroboration of a lone mention).
        It does not. It comes from the BIGRAM RULE: "נשאר אדום" ("stayed red") is two adjacent
        tokens that are neither generic, nor domain vocabulary, nor a competition — so the rule
        calls it a name. `נשאר` is an ordinary Hebrew verb and `אדום` an ordinary adjective
        (here, the club's colour).

        This is the honest shape of the gap: **the bigram rule's premise — "two adjacent
        non-vocabulary tokens is a name" — holds only to the extent that the vocabulary is
        complete, and Hebrew is not a closed vocabulary.** Enumerating verbs and adjectives
        until this corpus passes is the same mistake as hand-adding four player names to the
        taxonomy. It needs a real lexical resource.
        """
        anchors = generate_anchor_candidates("נשאר אדום: אלייז'ה בראיינט האריך חוזה")
        names = {a.normalized for a in anchors}
        assert "נשאר אדום" in names, (
            "EXPECTED FAILURE, recorded on purpose: an ordinary verb+adjective pair extracts "
            "as a name. If this ever stops holding, the discriminator improved — retire this "
            "test deliberately and tighten TestTheRequiredNegatives."
        )
        assert "אלייז בראיינט" in names, "…while the REAL name is also found, correctly"

    def test_scoping_the_lexicon_trades_recall_for_precision(self):
        """Measured, not asserted from intuition (see scripts/clustering_diagnostics.py):

            corpus-wide lexicon    → must_merge 17/17, over-merges 3
            candidate-scoped lex.  → must_merge 15/17, over-merges 2

        Neither passes D6. Scoping is the contract, but it is not the fix — the fix is a real
        name/not-name discriminator, and hand-adding אדום/שיא/הכל to fit this corpus would be
        the same mistake as hand-adding four player names to the taxonomy.
        """
        arts = [
            _art("a", "נשאר אדום: אלייז'ה בראיינט האריך חוזה", src="ynet_sport"),
            _art("b", "אחרי בלייקני ובריאנט: גם דן אוטורו האריך חוזה", src="walla_sport",
                 hours=2),
        ]
        scoped = build_name_lexicon(candidate_population(arts[0], arts, CFG))
        assert isinstance(scoped, frozenset)
