"""#410: an injury story about the OPPONENT of a followed team is not that team's injury.

"השחקן שייעדר מול מכבי תל אביב" is a Red Star player missing the game against
Maccabi. Maccabi is named only as the opponent ("מול/נגד <team>"), so it is not the
injured subject, and Guy's ``always_push:injury`` for Maccabi must not fire. The
story stays visible at its normal tier.
"""
from datetime import datetime, timezone

import pytest

from app.classification.attention_evidence import attention_evidence
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.models.article import Article
from app.models.profile_v2 import OverrideRule
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2

MACCABI = "team:maccabi_tlv_bb"
DENI = "player:deni_avdija"

_EXAMPLE_TITLE = 'השחקן שייעדר מול מכבי תל אביב: "אפילו לא יודע את כל השמות"'
_EXAMPLE_SUBTITLE = (
    "כריסטיאן קולוקו הצטרף לכוכב האדום בלגרד כמחליף לג'ונתן מוטלי, אבל עדיין צריך להתאקלם"
    ' • המאמן איבון נבארו: "קשה להתכונן אליהם, הם משחקים כדורסל שונה"'
)


def _profile(user_id):
    """The seed profile plus the injury push rules the seed dropped (#423), so the subject
    logic stays tested in case the owner turns injury pushes back on."""
    profile = next(p for p in SEED_PROFILES if p.user_id == user_id).model_copy(deep=True)
    targets = [("player", DENI)] + ([("team", MACCABI)] if user_id == "guy" else [])
    profile.profile_v2.overrides.extend(
        OverrideRule(kind="always_push", scope=scope, target_id=target, event_type="injury")
        for scope, target in targets
    )
    return profile


def _scored(title, entity_ids, user_id="guy", subtitle=""):
    evidence = attention_evidence(title, subtitle, "injury", entity_ids)
    article = Article(
        id="t410", source="test", source_display_name="test", url="https://example.com/410",
        title=title, subtitle=subtitle, published_at=datetime.now(timezone.utc),
        sport="basketball", event_type="injury", importance="high", taxonomy_version=1,
        entity_ids=entity_ids, classification_trace={"attention": evidence},
    )
    return evidence, score_article_v2(article, _profile(user_id))


@pytest.mark.parametrize("title", [
    _EXAMPLE_TITLE,
    'יחסר נגד מכבי ת"א: הגארד של ולנסיה נפצע בברך',
    "Valencia guard injured, out for the game against Maccabi Tel Aviv",
])
def test_team_named_only_as_the_opponent_is_not_the_injured_subject(title):
    evidence, result = _scored(title, [MACCABI])
    assert evidence["development"] == "current_injury"
    assert MACCABI not in evidence["subject_entity_ids"]
    assert result.decision != "push"
    assert result.decision != "hidden"  # still a Maccabi-relevant story, just not a buzz


def test_reported_row_through_the_ingestion_path_is_not_pushed():
    cfg = get_source_config("israel_hayom_sport")
    article, _, _ = ingestion_service._normalise(
        RawSourceItem(source_id="israel_hayom_sport",
                      url="https://www.israelhayom.co.il/sport/world-basketball/article/21712311",
                      title=_EXAMPLE_TITLE, published_at=None, summary=_EXAMPLE_SUBTITLE),
        cfg, llm_available=False,
    )
    assert article.event_type == "injury"
    assert MACCABI in article.entity_ids  # the fact that Maccabi is involved is kept
    assert MACCABI not in article.classification_trace["attention"]["subject_entity_ids"]
    decision = score_article_v2(article, _profile("guy")).decision
    assert decision not in ("push", "hidden")


@pytest.mark.parametrize("title,entity_ids,user_id,subject", [
    # The followed team's own player, opponent named after מול: still a push.
    ("מכבי תל אביב: לונדברג נפצע וייעדר מול ולנסיה", [MACCABI], "guy", MACCABI),
    # Followed team named both as the subject and, later, in the opponent slot.
    ('מכבי ת"א: לונדברג נפצע, ולנסיה תשחק מול מכבי ת"א', [MACCABI], "guy", MACCABI),
    # Prefixed mention, followed team on the left of the marker.
    ("דאגה במכבי תל אביב: לונדברג נפצע מול ולנסיה", [MACCABI], "guy", MACCABI),
    # The followed team sits in the slot, but its OWN player is the one named as injured.
    ('הפועל ת"א נגד מכבי ת"א: לונדברג ייעדר', [MACCABI, "player:iffe_lundberg"], "guy", MACCABI),
    # Deni himself injured before a game against someone: push for both profiles.
    ("דני אבדיה ייעדר מול הסלטיקס", [DENI], "guy", DENI),
    ("דני אבדיה ייעדר מול הסלטיקס", [DENI], "casual_deni_fan", DENI),
])
def test_followed_scope_that_is_the_injured_subject_still_pushes(title, entity_ids, user_id, subject):
    evidence, result = _scored(title, entity_ids, user_id)
    assert subject in evidence["subject_entity_ids"]
    assert result.decision == "push"


def test_opponent_marker_must_sit_directly_before_the_name():
    # "מול" elsewhere in the title does not make the Maccabi mention an opponent slot.
    evidence = attention_evidence("מכבי תל אביב נפצעה מול הקהל: שחקן ייעדר", "", "injury", [MACCABI])
    assert MACCABI in evidence["subject_entity_ids"]


def test_a_shorter_alias_inside_an_opponent_slot_is_also_the_opponent():
    # "אבדיה" sits inside "מול דני אבדיה": the whole name is in the opponent slot.
    evidence = attention_evidence("השחקן ייעדר מול דני אבדיה ופורטלנד", "", "injury", [DENI])
    assert DENI not in evidence["subject_entity_ids"]


def test_opponent_rule_is_scoped_to_injury_events():
    # Signing/negotiation subjects are unchanged by #410.
    evidence = attention_evidence("השחקן שהבקיע מול מכבי תל אביב חתם בה", "", "signing", [MACCABI])
    assert MACCABI in evidence["subject_entity_ids"]


def test_subtitle_opponent_wording_does_not_take_a_title_subject_away():
    evidence = attention_evidence("מכבי תל אביב: לונדברג נפצע", "ולנסיה תשחק מול מכבי תל אביב", "injury", [MACCABI])
    assert MACCABI in evidence["subject_entity_ids"]


def test_a_named_player_of_another_team_does_not_rescue_the_opponent():
    # Red Star's player is named: Maccabi stays the opponent. Keeps the own-player
    # exception honest (it needs the followed team's own player, not any player).
    evidence = attention_evidence(
        "מיציץ' ייעדר מול מכבי תל אביב", "", "injury", [MACCABI, "player:vasilije_micic"])
    assert MACCABI not in evidence["subject_entity_ids"]


@pytest.mark.parametrize("title", [
    'הפועל ת"א נגד מכבי ת"א: לונדברג ייעדר',
    "ברצלונה מול מכבי תל אביב: ים מדר נפצע",
    'לקראת המשחק נגד מכבי ת"א: רומן סורקין נפצע',
    "Barcelona vs Maccabi Tel Aviv: Roman Sorkin injured",
])
def test_own_player_keeps_the_team_a_subject_through_the_ingestion_path(title):
    """The classifier swaps implies_team players for their club, so entity_ids has no player."""
    item = RawSourceItem(source_id="sport5_sport", url="https://example.test/own", title=title,
                         published_at=None, summary="")
    article, _ms, _gate = ingestion_service._normalise(
        item, get_source_config("sport5_sport"), llm_available=False)
    trace = article.classification_trace["attention"]
    assert MACCABI in trace["subject_entity_ids"]


def test_a_players_alias_inside_another_word_does_not_rescue_the_opponent():
    evidence = attention_evidence("ריאל מדריד ייעדר מול מכבי תל אביב", "", "injury", [MACCABI])
    assert MACCABI not in evidence["subject_entity_ids"]
