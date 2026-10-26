"""
#259 — Israeli-league basketball people: a mention gives sport and team evidence.

The week-sample analysis (docs/qa/WEEK_SAMPLE_2026-10_DEV_RESULTS.md) and #345 found Maccabi
and Hapoel Tel Aviv basketball stories hidden because the club name is cross-sport and nothing
else in the text proved the sport. Player and coach names do: they follow the coach and
executive precedent (#229) — the mention emits the CLUB, and the person is not followable.

Every alias is word-bounded: the resolver is a raw substring scanner, and short surnames sit
inside other words ("בריסט" in "בריסטול", "מדר" in "מדריד", "ים מדר" across "שחקנים מדרגים").
"""

import pytest

from app.api.routes_taxonomy import build_catalog
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.taxonomy import ENTITIES, validate_registry
from app.taxonomy.policy import scope_target_selectable
from app.taxonomy.resolver import resolve_entities

MACCABI, HAPOEL = "team:maccabi_tlv_bb", "team:hapoel_tlv_bb"
NEW_PEOPLE = [e for e in ENTITIES.values() if e.implies_team]


def _ingest(title: str, subtitle: str = "", source_id: str = "walla_sport"):
    item = RawSourceItem(source_id=source_id, url="https://sports.walla.co.il/item/9259",
                         title=title, published_at=None, summary=subtitle)
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(source_id))
    return article


def _ids(text: str) -> list[str]:
    return [e.id for e in resolve_entities(text.lower()).resolved]


class TestRegistry:
    def test_batch_is_israeli_basketball_with_a_club(self):
        assert len(NEW_PEOPLE) >= 20
        for e in NEW_PEOPLE:
            assert e.sport == "basketball"
            assert e.team_id in (MACCABI, HAPOEL)
            assert e.kind in ("player", "coach")
        assert validate_registry() == []

    def test_every_alias_is_word_bounded(self):
        for e in NEW_PEOPLE:
            assert set(e.word_bounded_aliases) == set(e.aliases), e.id

    def test_people_ride_on_their_club_and_are_not_followable(self):
        listed = {p.id for p in build_catalog().people}
        for e in NEW_PEOPLE:
            assert e.id not in listed
            assert not scope_target_selectable("player", e.id)


class TestMentionImpliesTheClub:
    def test_surname_in_title(self):
        # corpus title (Maccabi's Oshae Brissett)
        a = _ingest('בריסט: "חשוב לנו לשחק נגד יריבות חזקות"')
        assert a.entity_ids == [MACCABI]
        assert a.sport == "basketball"

    def test_player_in_subtitle_resolves_the_cross_sport_club(self):
        a = _ingest('מכבי ת"א מרוצה מהזכייה', "ים מדר קלע 20 נקודות והוביל את הצהובים")
        assert MACCABI in a.entity_ids
        assert a.sport == "basketball"

    def test_backtick_spelling_and_conjunction_prefix(self):
        # corpus title: a backtick where the geresh belongs, and the ו prefix
        a = _ingest('פגישה על הפרק: מו"מ הפועל וג`ייקוב טופין')
        assert HAPOEL in a.entity_ids

    def test_backtick_spelling_of_an_existing_executive(self):
        # focused #345 set, rated push: "ג`ייסון" never matched "ג'ייסון לוין"
        a = _ingest('ג`ייסון לוין בראיון בלעדי: "המטרה - להחזיר את מכבי ת"א לגדולתה"',
                    "צפו באחד מבעלי מכבי ת\"א בראיון לערוץ הספורט.", source_id="sport5_sport")
        assert MACCABI in a.entity_ids

    def test_hapoel_coach(self):
        a = _ingest("עם מסר לדימיטריס איטודיס: הפועל תל אביב ניצחה במחזור הפתיחה")
        assert HAPOEL in a.entity_ids
        assert a.sport == "basketball"


class TestCollisionsStayUnresolved:
    @pytest.mark.parametrize("text", [
        "סאות'המפטון ופרץ הביסו 1:4 את בריסטול ועיסאת",       # corpus: Bristol, not Brissett
        "דורשת הכרעה: האולטימטום שהציבה ריאל מדריד לוויניסיוס",  # corpus: Madrid, not Madar
        "השחקנים מדרגים את המאמן",                              # "ים מדר" across two words
        "מתקפה גזענית על קייטלין קלארק",                         # corpus: Caitlin Clark, not Jimmy
        "השחקן הורד מהסגל לקראת המשחק",                          # "הורד" is a Hebrew verb
        "המדריך של העונה",                                       # "מדר" inside a word
    ], ids=["bristol", "madrid", "across_words", "caitlin_clark", "verb_horad", "inside_word"])
    def test_no_new_person_resolves(self, text):
        new_ids = {e.id for e in NEW_PEOPLE}
        assert not new_ids & set(_ids(text))


class TestExistingPlayersUnchanged:
    def test_deni_still_emits_himself_not_portland(self):
        a = _ingest("דני אבדיה קלע 26, פורטלנד ניצחה בסקרמנטו", source_id="ynet_sport")
        assert "player:deni_avdija" in a.entity_ids


class TestExplicitSportStillWins:
    def test_football_keyword_beats_a_basketball_name(self):
        # a football story that happens to name a basketball player: the explicit
        # football word decides, and the basketball club is not attached
        a = _ingest('שחקני הכדורגל של מכבי ת"א הגיעו לעודד את ים מדר', "השוער והבלמים ישבו ביציע")
        assert a.sport == "football"
        assert MACCABI not in (a.entity_ids or [])


class TestNationalTeamIsNotTheClub:
    """A player named in a national-team story proves basketball, not his club."""

    def test_national_team_story_gets_the_sport_but_not_the_club(self):
        a = _ingest("ים מדר הוביל את נבחרת ישראל לניצחון על ליטא")
        assert a.sport == "basketball"
        assert MACCABI not in (a.entity_ids or [])

    def test_with_a_prefix_too(self):
        a = _ingest("קולסון ובריסט לא יצטרפו לנבחרת בחלון הקרוב")
        assert MACCABI not in (a.entity_ids or [])

    def test_a_club_story_still_gets_the_club(self):
        a = _ingest("ים מדר קלע 20 נקודות בניצחון על אריס")
        assert MACCABI in a.entity_ids


class TestASubtitleOnlyPersonIsNotTheSubject:
    """Corpus: a gossip item about David Blatt names his son Tamir only in the subtitle,
    as the bride's brother and a Maccabi player LAST season. The person proves the sport;
    he does not make the article about his current club."""

    def test_incidental_subtitle_person_implies_no_club(self):
        a = _ingest('דיוויד בלאט נבהל מהצעת הנישואין לבתו: "הכל בסדר?"',
                    "אלה בלאט, בתו של המאמן האגדי ואחותו של כדורסלן מכבי תל אביב בעונה החולפת, "
                    "תמיר בלאט, אמרה כן להצעת הנישואין")
        assert HAPOEL not in (a.entity_ids or [])

    def test_a_subtitle_person_still_resolves_a_club_the_title_names(self):
        # the title names the (cross-sport) club; the subtitle person proves basketball
        a = _ingest('מכבי ת"א מרוצה מהזכייה', "ים מדר קלע 20 נקודות והוביל את הצהובים")
        assert MACCABI in a.entity_ids


class TestDeparturesDoNotInferTheRosterClub:
    """The roster says where a player is TODAY, not what a departure or transfer story is
    about. In departure/transfer context the roster club is not inferred: an unresolved club
    beats an unsupported association (owner decision, 2026-10-26). A club the text names is
    still attached, and ordinary current-club stories keep the roster club."""

    def test_signing_elsewhere_names_only_the_destination(self):
        a = _ingest("רשמי: ג'ימי קלארק חתם בפנאתינייקוס")
        assert "team:panathinaikos_bb" in a.entity_ids
        assert "team:maccabi_tlv_bb" not in a.entity_ids

    def test_an_agreement_abroad_names_only_the_club_abroad(self):
        a = _ingest("רומן סורקין סיכם באולימפיאקוס")
        assert a.entity_ids == ["team:olympiacos_bb"]

    def test_a_farewell_naming_the_old_club_keeps_only_that_club(self):
        a = _ingest('ים מדר נפרד מהפועל ת"א: "השנה לא הייתה קלה עבורי, עוזב בראש מורם"')
        assert a.entity_ids == ["team:hapoel_tlv_bb"]

    def test_a_farewell_naming_no_club_leaves_the_club_unresolved(self):
        a = _ingest('מדר: "עוזב בראש מורם. השנה לא הייתה קלה"', "הגארד נפרד מהפועל בדרך למכבי")
        assert a.sport == "basketball"
        assert a.entity_ids == []

    def test_a_signing_at_the_roster_club_keeps_it(self):
        a = _ingest("איפה לונדברג סיכם על חוזה חדש במכבי תל אביב")
        assert a.entity_ids == ["team:maccabi_tlv_bb"]

    def test_ordinary_current_club_stories_keep_the_roster_club(self):
        assert "team:maccabi_tlv_bb" in _ingest('בסימן שאלה: דניאל תייס ייעדר מול הפועל ת"א?').entity_ids
        assert _ingest('בריסט: "חשוב לנו לשחק נגד יריבות חזקות"').entity_ids == ["team:maccabi_tlv_bb"]
        assert _ingest("שכרו בפנים: בלייקני האריך חוזה בהפועל").entity_ids == ["team:hapoel_tlv_bb"]
