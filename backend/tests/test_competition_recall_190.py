"""Entity-resolution recall fixes from the ground truth (issue #190).

The N05 measurement found 25 of Guy's 34 false-hides carrying no resolved
competition. The diagnosis was not the one the issue assumed: **24 of the 25 had
no resolved entity at all**, so competition inference had nothing to work from.

These tests pin the four causes that were fixed, and — just as importantly — pin
the abstentions that must NOT change. Every "must still abstain" case below is a
designed success mode (#58 invariant), not a remaining gap.
"""

import pytest

from app.taxonomy.entities import ENTITIES
from app.taxonomy.resolver import normalize_alias_text, resolve_entities


def _ids(text, sport=None):
    return {e.id for e in resolve_entities(text, sport_context=sport).resolved}


# ── clubs that were missing from the registry ─────────────────────────────────


class TestMissingClubs:
    def test_hapoel_galil_elyon_exists_and_is_not_galil_gilboa(self):
        """Two DIFFERENT clubs. The registry had only Gilboa, so "גליל עליון"
        resolved to nothing and every article about Elyon was hidden."""
        assert _ids("יעד חדש: רני בלגה הצטרף לגליל עליון", "basketball") == {
            "team:hapoel_galil_elyon"
        }
        assert _ids("הפועל גלבוע גליל שיחקה", "basketball") == {
            "team:hapoel_galil_gilboa"
        }

    def test_galil_elyon_resolves_without_sport_evidence(self):
        """All ten corpus mentions are basketball, so no guard is warranted."""
        assert _ids("דורי סהר סיכם בהפועל גליל עליון") == {"team:hapoel_galil_elyon"}

    def test_maccabi_ashdod_exists(self):
        assert _ids("רשמי. סנטר חתם באשדוד", "basketball") == {"team:maccabi_ashdod"}

    def test_ashdod_is_guarded_because_football_shares_the_bare_form(self):
        """M.S. Ashdod (football) is not in the registry, so the bare town name
        must abstain without sport evidence rather than claim basketball."""
        assert ENTITIES["team:maccabi_ashdod"].guarded is True
        assert _ids("גיא וייזינגר יצטרף לצוות האימון של מ.ס אשדוד") == set()

    def test_bare_eilat_resolves(self):
        """Nine corpus mentions of "אילת", all basketball."""
        assert _ids('ארון ווילר במו"מ עם אילת', "basketball") == {"team:hapoel_eilat"}


# ── hyphen normalization ──────────────────────────────────────────────────────


class TestHyphenNormalization:
    def test_hyphenated_and_spaced_forms_are_the_same_club(self):
        spaced = _ids("הפועל באר שבע תמשיך בליגת העל", "basketball")
        hyphenated = _ids("הפועל באר-שבע תמשיך בליגת העל", "basketball")
        assert spaced == hyphenated == {"team:hapoel_beer_sheva_bb"}

    @pytest.mark.parametrize("dash", ["-", "־", "–", "—"])
    def test_every_hyphen_class_character_folds(self, dash):
        assert _ids(f"הפועל באר{dash}שבע תמשיך", "basketball") == {
            "team:hapoel_beer_sheva_bb"
        }

    def test_normalization_preserves_length(self):
        """Span offsets feed the former-affiliation window and the overlap
        bookkeeping, so the fold must be character-for-character."""
        for raw in ["הפועל באר-שבע", "ex-Maccabi", "a–b—c־d"]:
            assert len(normalize_alias_text(raw)) == len(raw)

    def test_former_affiliation_still_detected_after_folding(self):
        """The adjacency window is offset-based; folding must not shift it."""
        res = resolve_entities("אקס הפועל באר-שבע חתם בקבוצה חדשה", "basketball")
        assert res.resolved == []
        assert res.former_affiliations


# ── the guard deadlock ────────────────────────────────────────────────────────


class TestGuardedFullNameExemption:
    def test_full_name_of_a_declaring_entity_resolves_without_sport_evidence(self):
        """The circular dependency: the entity needed sport evidence, and the
        article's sport was unknown BECAUSE nothing resolved."""
        assert ENTITIES["team:ironi_ness_ziona"].full_name_disambiguates is True
        assert _ids("ברייס בראון ימשיך לעונה שלישית בעירוני נס ציונה") == {
            "team:ironi_ness_ziona"
        }

    def test_short_form_of_the_same_club_still_needs_evidence(self):
        """"נס ציונה" alone really might be Sektzia Ness Ziona (football)."""
        assert _ids("משחק מול נס ציונה") == set()
        assert _ids("משחק מול נס ציונה", "basketball") == {"team:ironi_ness_ziona"}

    @pytest.mark.parametrize(
        "entity_id, text",
        [
            ("team:real_madrid_bb", "ריאל מדריד עם ניצחון גדול"),
            ("team:bayern_munich_bb", "באיירן מינכן ניצחה"),
            ("team:valencia_bb", "ולנסיה הפסידה"),
        ],
    )
    def test_european_multisport_clubs_are_NOT_exempt(self, entity_id, text):
        """These share their FULL name across football and basketball, so no part
        of the name proves the sport. The exemption is explicit metadata for
        exactly this reason — it must never be inferred from "is a full name"."""
        assert ENTITIES[entity_id].guarded is True
        assert ENTITIES[entity_id].full_name_disambiguates is False
        assert _ids(text) == set()
        assert _ids(text, "basketball") == {entity_id}

    def test_exemption_is_opt_in_across_the_whole_registry(self):
        """A future guarded entity must not silently inherit the exemption."""
        exempt = {e.id for e in ENTITIES.values() if e.full_name_disambiguates}
        # Maccabi Ashdod is guarded but deliberately does NOT declare the flag:
        # no corpus article names the club in full, so its display name is an
        # assumption rather than evidence. The guard alone resolves those rows.
        assert exempt == {"team:ironi_ness_ziona"}
        assert all(ENTITIES[eid].guarded for eid in exempt)


# ── abstentions that must survive ─────────────────────────────────────────────


class TestPreservedAbstentions:
    def test_bare_family_name_still_resolves_to_nothing(self):
        """"בהפועל" does not say WHICH Hapoel. Rated a false-hide by Guy, and
        still correctly hidden — a designed success mode, not a gap."""
        res = resolve_entities("בר טימור במשא ומתן על חוזה חדש בהפועל", "basketball")
        assert res.resolved == []
        assert "הפועל" in res.family_mentions

    def test_maccabi_tel_aviv_remains_cross_sport_ambiguous(self):
        """A different mechanism from `guarded`: both clubs are in the registry
        under the same full name, so evidence stays mandatory. #190 must not have
        widened this."""
        res = resolve_entities("מכבי תל אביב פספסה בענק")
        assert res.resolved == []
        assert [alias for alias, _ in res.ambiguous] == ["מכבי תל אביב"]
        assert _ids("מכבי תל אביב פספסה בענק", "basketball") == {"team:maccabi_tlv_bb"}


# ── the alias index must stay unambiguous ─────────────────────────────────────


def test_normalization_did_not_collapse_two_clubs_onto_one_alias():
    """Folding hyphens could merge two distinct aliases into one key. If that
    ever maps to two entities of the SAME sport, the resolver would start
    abstaining on names it used to know."""
    from app.taxonomy.resolver import _ALIAS_INDEX

    for alias, candidates in _ALIAS_INDEX.items():
        by_sport = {}
        for c in candidates:
            by_sport.setdefault(c.sport, []).append(c.id)
        for sport, ids in by_sport.items():
            assert len(ids) == 1, (
                f"alias {alias!r} maps to {len(ids)} {sport} entities ({ids}) — "
                "same-sport collision makes it permanently unresolvable"
            )
