from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.classification.event_evidence import validate_event_evidence
from app.classification.event_subjects import relocation_subject_ids
from app.ingestion.classifier import classify, detect_article_event
from app.ingestion.ingestion_service import _apply_post_facts_event_validation
from app.models.article import Article
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2
from scripts.apply_191_event_corrections import correction


TITLE = "דיווח דרמטי: דני אבדיה ופורטלנד עשויים לעבור לאוקלהומה"
SUBTITLE = "הכוכב הישראלי יעביר את ביתו ליעד חדש?"


def article(**changes):
    data = dict(id="rss_test", title=TITLE, subtitle=SUBTITLE, source="test",
                source_display_name="Test", url="https://example.com/test",
                published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                sport="basketball", event_type="news", importance="medium",
                entity_ids=["player:deni_avdija", "team:portland_blazers"],
                entities=["Deni Avdija", "Portland Trail Blazers"], taxonomy_version=1)
    return Article(**(data | changes))


def test_relocation_real_case_and_profile_separation():
    a = article()
    patch = correction(a)
    assert patch["event_type"] == "relocation"
    assert patch["event_certainty"] == "probable"
    updated = a.model_copy(update=patch)
    profiles = {p.user_id: p for p in SEED_PROFILES}
    result = score_article_v2(updated, profiles["casual_deni_fan"])
    assert result.decision == "push"
    assert result.matched_event_rule == "always_push:relocation"
    assert score_article_v2(updated, profiles["guy"]).decision == "feed"
    assert correction(updated) is None
    assert updated.sport == a.sport and updated.entity_ids == a.entity_ids


@pytest.mark.parametrize("text", [
    "השחקן עשוי לעבור ליוון ומחזיק בהצעה מקבוצה חדשה",
    "דני אבדיה יעביר את ביתו לשכונה חדשה",
    "אין לאן לעבור: הקבוצה נותרה ללא יעד",
    "הקבוצה תשפץ את האולם",
    "The team will not relocate",
])
def test_relocation_requires_franchise_move(text):
    assert not validate_event_evidence("relocation", text).valid


def test_relocation_scope_generalizes_and_excludes_possessive_player():
    assert validate_event_evidence("relocation", "The franchise plans to relocate").valid
    assert relocation_subject_ids("כאוס בקבוצה של דני אבדיה", ["player:deni_avdija"]) == []
    a = article(title="כאוס בקבוצה של דני אבדיה", subtitle="הבעלים שוקל להעביר את המועדון למדינה אחרת")
    updated = a.model_copy(update=correction(a))
    deni = next(p for p in SEED_PROFILES if p.user_id == "casual_deni_fan")
    assert score_article_v2(updated, deni).decision != "push"


@pytest.mark.parametrize("title,subtitle,event", [
    ("ההחלטה שאולי תגרום לדני אבדיה לעזוב", 'בארה"ב ניתחו את צירופו: חוזה חדש', "analysis"),
    ("הכוכב שיתף", "התארח בפודקאסט ושוחח על הקריירה", "interview"),
    ("הקשר יעבור ניתוח בגבו", "", "news"),
    ("בלי התייעצות התקבלה ההחלטה", "", "news"),
    ("השחקן חתם רשמית", "בראיון סיפר על החוזה", "signing"),
])
def test_editorial_routing_and_near_misses(title, subtitle, event):
    assert detect_article_event(title, subtitle, "basketball").event_type == event


def test_abstention_has_persistable_reason_without_changing_facts():
    result = classify("חדשות כלליות", source_id="eurohoops")
    facts = SimpleNamespace(sport="basketball", entities=[], entity_ids=[], league=None, trace={})
    _apply_post_facts_event_validation(result, facts=facts, title_lower="חדשות כלליות",
                                       subtitle_lower="", source_id="eurohoops")
    assert facts.trace["event"]["abstention_reason"] == "no_supported_event_with_positive_evidence"
    assert result.event_type == "news"


def test_correction_preserves_llm_facts_and_trace_history():
    a = article(classified_by="llm", classification_trace={"llm": {"proposal": {"sport": "basketball"}}})
    before = deepcopy(a.model_dump())
    changed = a.model_copy(update=correction(a))
    for field in ("sport", "entity_ids", "primary_competition", "classified_by", "confidence"):
        assert getattr(changed, field) == before[field]
    assert changed.classification_trace["llm"] == before["classification_trace"]["llm"]
