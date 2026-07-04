"""Tests for subtitle extraction and cleaning (app.ingestion.subtitle)."""

import pytest

from app.ingestion.subtitle import clean_subtitle, extract_subtitle


# ── clean_subtitle ────────────────────────────────────────────────────────────

class TestCleanSubtitle:
    def test_strips_html_tags(self):
        assert clean_subtitle("<p>Hello world</p>") == "Hello world"

    def test_strips_nested_html(self):
        result = clean_subtitle('<div class="x"><span>מכבי <b>תל אביב</b></span></div>')
        assert result == "מכבי תל אביב"
        assert "<" not in result

    def test_unescapes_html_entities(self):
        assert clean_subtitle("גביע &amp; ליגה") == "גביע & ליגה"

    def test_unescapes_nbsp(self):
        result = clean_subtitle("שחקן&nbsp;חדש")
        assert "&nbsp;" not in result

    def test_collapses_whitespace(self):
        assert clean_subtitle("  hello   world  \n\t") == "hello world"

    def test_truncates_to_240_chars_default_when_no_sentence_end(self):
        long_text = "א" * 600  # no punctuation at all -> hard cut fallback
        result = clean_subtitle(long_text)
        assert result is not None
        assert len(result) == 240

    def test_custom_max_chars(self):
        result = clean_subtitle("abc" * 100, max_chars=10)
        assert result is not None
        assert len(result) == 10

    def test_empty_string_returns_none(self):
        assert clean_subtitle("") is None

    def test_whitespace_only_returns_none(self):
        assert clean_subtitle("   \n\t  ") is None

    def test_html_only_returns_none(self):
        assert clean_subtitle("<br><br><p></p>") is None

    def test_plain_text_unchanged(self):
        assert clean_subtitle("מכבי תל אביב זכתה") == "מכבי תל אביב זכתה"

    def test_short_text_under_budget_returned_whole(self):
        text = "משפט קצר אחד בלבד."
        assert clean_subtitle(text) == text

    def test_cuts_at_last_sentence_end_within_budget(self):
        # Two short sentences fit inside 240 chars; a third, long one does not.
        s1 = "משפט ראשון קצר."
        s2 = "משפט שני גם הוא קצר יחסית."
        s3 = "משפט שלישי ארוך במיוחד " + "שממשיך ומתמשך " * 20 + "עד שהוא חורג מהתקציב."
        result = clean_subtitle(f"{s1} {s2} {s3}")
        assert result == f"{s1} {s2}"

    def test_does_not_treat_a_decimal_point_as_a_sentence_end(self):
        # "1.88" must never be mistaken for a sentence boundary and split.
        first_sentence = "השחקן גובה 1.88 מטר ושוקל 95 קילו."
        filler = "משפט נוסף שממשיך הלאה בלי שום קשר. " * 10
        text = f"{first_sentence} {filler}"
        assert len(text) > 240  # sanity: truncation must actually trigger
        result = clean_subtitle(text)
        assert result is not None
        assert len(result) <= 240
        assert "1.88" in result  # decimal preserved intact, never split
        assert result.endswith(".")  # still ends at a clean sentence boundary

    def test_ignores_sentence_end_too_early_in_the_window(self):
        # A lone "מ." at position 1 shouldn't trigger a degenerate cut.
        text = "מ. " + ("תוכן ממשיך בלי סימני פיסוק נוספים " * 20)
        result = clean_subtitle(text)
        assert result is not None
        assert len(result) == 240

    def test_falls_back_to_hard_cut_when_no_sentence_boundary_exists(self):
        text = "מילה " * 100  # no terminal punctuation anywhere
        result = clean_subtitle(text)
        assert result is not None
        assert len(result) == 240


# ── extract_subtitle ──────────────────────────────────────────────────────────

class TestExtractSubtitle:
    class _Entry:
        """Minimal feedparser-like entry stub."""
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def test_uses_summary_field(self):
        entry = self._Entry(summary="<p>Test summary</p>")
        assert extract_subtitle(entry) == "Test summary"

    def test_falls_back_to_description(self):
        entry = self._Entry(description="fallback description")
        assert extract_subtitle(entry) == "fallback description"

    def test_falls_back_to_subtitle_attr(self):
        entry = self._Entry(subtitle="atom subtitle")
        assert extract_subtitle(entry) == "atom subtitle"

    def test_falls_back_to_content_value(self):
        entry = self._Entry(content=[{"value": "<p>content text</p>"}])
        assert extract_subtitle(entry) == "content text"

    def test_summary_takes_priority_over_description(self):
        entry = self._Entry(summary="from summary", description="from description")
        assert extract_subtitle(entry) == "from summary"

    def test_returns_none_when_nothing_available(self):
        entry = self._Entry()
        assert extract_subtitle(entry) is None

    def test_returns_none_for_empty_summary(self):
        entry = self._Entry(summary="")
        assert extract_subtitle(entry) is None

    def test_returns_none_for_whitespace_only_summary(self):
        entry = self._Entry(summary="   ")
        assert extract_subtitle(entry) is None

    def test_html_in_summary_is_cleaned(self):
        entry = self._Entry(summary="<b>חדשות ספורט</b> &mdash; <em>מכבי</em> מנצחת")
        result = extract_subtitle(entry)
        assert result is not None
        assert "<" not in result
        assert "&" not in result

    def test_long_summary_truncated_to_240(self):
        entry = self._Entry(summary="ב" * 600)
        result = extract_subtitle(entry)
        assert result is not None
        assert len(result) == 240

    def test_content_list_with_non_dict_item_skipped(self):
        entry = self._Entry(content=["not a dict"])
        assert extract_subtitle(entry) is None

    def test_empty_content_list_returns_none(self):
        entry = self._Entry(content=[])
        assert extract_subtitle(entry) is None
