"""
Tests for app.translation.translation_quality guardrails.

No external dependencies — no API calls.
"""

from app.translation.translation_quality import (
    latin_ratio,
    contains_model_explanation,
    looks_like_hebrew_translation,
)


class TestLatinRatio:
    def test_pure_hebrew_is_zero(self):
        assert latin_ratio("מכבי תל אביב") == 0.0

    def test_pure_latin_is_one(self):
        ratio = latin_ratio("Boston Celtics")
        assert ratio == 1.0

    def test_mixed_hebrew_latin(self):
        # "מכבי NBA" — some Hebrew letters, some Latin
        ratio = latin_ratio("מכבי NBA")
        assert 0.0 < ratio < 1.0

    def test_numbers_and_punctuation_ignored(self):
        # Digits and punctuation are not letters; should not affect ratio
        ratio = latin_ratio("123 !@#")
        assert ratio == 0.0

    def test_empty_string_is_zero(self):
        assert latin_ratio("") == 0.0

    def test_hebrew_with_latin_team_name(self):
        # Legitimate mixed headline: Hebrew text + Latin team abbreviation
        ratio = latin_ratio("בוסטון סלטיקס חתמה על NBA guard")
        assert ratio < 0.6  # Should still pass quality check


class TestContainsModelExplanation:
    def test_detects_here_is(self):
        assert contains_model_explanation("Here is the translation: מכבי") is True

    def test_detects_heres(self):
        assert contains_model_explanation("Here's the headline: text") is True

    def test_detects_hebrew_prefix(self):
        assert contains_model_explanation("הנה התרגום: מכבי תל אביב") is True

    def test_detects_translation_colon(self):
        assert contains_model_explanation("Translation: some text") is True

    def test_detects_translated_colon(self):
        assert contains_model_explanation("Translated: some text") is True

    def test_detects_hebrew_koteret(self):
        assert contains_model_explanation("הכותרת בעברית: מכבי") is True

    def test_valid_headline_not_detected(self):
        assert contains_model_explanation("מכבי תל אביב חתמה עם שחקן חדש") is False

    def test_valid_english_name_in_hebrew_not_detected(self):
        assert contains_model_explanation("בוסטון סלטיקס ודני אבדיה") is False

    def test_case_insensitive(self):
        assert contains_model_explanation("HERE IS the translation") is True
        assert contains_model_explanation("TRANSLATION: something") is True


class TestLooksLikeHebrewTranslation:
    # ── Should pass ───────────────────────────────────────────────────────────

    def test_normal_hebrew_headline_passes(self):
        assert looks_like_hebrew_translation(
            "מכבי תל אביב חתמה עם גארד יורוליג",
            "Maccabi Tel Aviv signs EuroLeague guard",
        ) is True

    def test_hebrew_with_latin_team_name_passes(self):
        # Mixed is fine as long as Hebrew dominates
        assert looks_like_hebrew_translation(
            "בוסטון סלטיקס חותמת על NBA guard",
            "Boston Celtics signs NBA guard",
        ) is True

    def test_hebrew_with_numbers_passes(self):
        assert looks_like_hebrew_translation(
            "מכבי עם 3 חתימות חדשות לעונה 2026",
            "Maccabi signs 3 new players for 2026 season",
        ) is True

    def test_short_headline_passes(self):
        assert looks_like_hebrew_translation(
            "דני אבדיה נסחר",
            "Deni Avdija traded",
        ) is True

    # ── Should fail ───────────────────────────────────────────────────────────

    def test_empty_string_fails(self):
        assert looks_like_hebrew_translation("", "Some original") is False

    def test_whitespace_only_fails(self):
        assert looks_like_hebrew_translation("   ", "Some original") is False

    def test_identical_to_original_fails(self):
        original = "Deni Avdija traded to Portland"
        assert looks_like_hebrew_translation(original, original) is False

    def test_model_adds_here_is_prefix_fails(self):
        assert looks_like_hebrew_translation(
            "Here is the Hebrew headline: מכבי תל אביב",
            "Maccabi Tel Aviv news",
        ) is False

    def test_hebrew_explanation_prefix_fails(self):
        assert looks_like_hebrew_translation(
            "הנה התרגום: מכבי תל אביב חתמה",
            "Maccabi Tel Aviv signed",
        ) is False

    def test_mostly_latin_output_fails(self):
        # Model returned basically the original English
        assert looks_like_hebrew_translation(
            "Maccabi Tel Aviv signs new EuroLeague guard",
            "Maccabi Tel Aviv signs new EuroLeague guard",
        ) is False

    def test_purely_latin_output_fails(self):
        assert looks_like_hebrew_translation(
            "Boston Celtics signed a new player",
            "Boston Celtics sign new player",
        ) is False

    def test_suspiciously_long_output_fails(self):
        original = "Deni"
        # 3× the length of original should be rejected
        very_long = "דני אבדיה נסחר לצוות חדש בעקבות עסקה גדולה שנחתמה היום בין הקבוצות"
        assert looks_like_hebrew_translation(very_long, original) is False

    def test_translation_colon_prefix_fails(self):
        assert looks_like_hebrew_translation(
            "Translation: מכבי תל אביב",
            "Maccabi Tel Aviv",
        ) is False
