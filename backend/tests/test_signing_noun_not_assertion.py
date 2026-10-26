"""The noun "ההחתמה" ("the signing") does not assert that a signing happened.

The signing cue "חתמה" ("she signed") is a substring match, so it fired inside the noun
forms החתמה / ההחתמה / החתמת / החתמות. A studio-episode teaser ("what did Avi Even say about
Madar's signing? watch the episode") became event_type=signing; with #353's sport and club
evidence it reached Guy's explicit Maccabi signing push rule (2026-10-26 notification replay).
Ten corpus articles carried "signing" only because of the noun; masking it moves them to
news or a better event (measured on the 2026-10-25 frozen copy). Real verbs still count.
"""
import pytest

from app.ingestion.classifier import detect_article_event


@pytest.mark.parametrize("title,subtitle", [
    ("מירוץ החימוש | השוק האירופי משתגע: מכבי, הפועל וירושלים עם אבי אבן באולפן",
     '"דאבל דריבל" על השוק האירופי. ומה אמר אבי אבן על ההחתמה של ים מדר ומקומו של רומן סורקין במכבי תל אביב החדשה? צפו בפרק'),
    ("חריג: התקרית של ההחתמה החדשה של העמק", ""),
    ("ברוכים הבאים לעידן הוולקאם: התופעה ששינתה את הכדורגל", "ההחתמות של הקיץ שינו את הליגה"),
])
def test_a_mentioned_signing_is_not_a_signing(title, subtitle):
    assert detect_article_event(title, subtitle, "basketball").event_type != "signing"


def test_on_the_verge_of_a_signing_is_not_a_completed_signing():
    # In the corpus its subtitle then routes it to negotiation; the title alone is news.
    ev = detect_article_event("בהמלצת שרי: מכבי חיפה על סף החתמה תמורת כחצי מיליון יורו", "", "football")
    assert ev.event_type != "signing"


@pytest.mark.parametrize("title", [
    "הפועל חולון חתמה עם הגארד האמריקאי",
    "רשמי: מכבי תל אביב החתימה את הסנטר",
    "דיוויד גרין חתם בעירוני קרית אתא",
    "אחרי שחתמה בגליל עליון: הגארד הגיעה לישראל",
])
def test_real_signing_verbs_still_count(title):
    assert detect_article_event(title, "", "basketball").event_type == "signing"
