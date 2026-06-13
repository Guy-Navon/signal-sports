"""
Tests for app.translation.prompt_builder.

Verifies the system prompt content without making any API calls.
"""

from app.translation.prompt_builder import SYSTEM_PROMPT, build_messages


class TestSystemPromptContent:
    def test_prompt_is_non_empty(self):
        assert len(SYSTEM_PROMPT) > 200

    def test_localization_instruction_present(self):
        assert "not literal translation" in SYSTEM_PROMPT

    def test_editor_framing_present(self):
        assert "Israeli sports editor" in SYSTEM_PROMPT

    def test_no_added_facts_instruction(self):
        assert "Do not add facts" in SYSTEM_PROMPT

    def test_return_only_headline_instruction(self):
        assert "Return ONLY" in SYSTEM_PROMPT or "Return only" in SYSTEM_PROMPT

    # ── Glossary terms ───────────────────────────────────────────────────────

    def test_glossary_accordo_present(self):
        assert "accordo" in SYSTEM_PROMPT

    def test_glossary_perimetro_present(self):
        assert "perimetro" in SYSTEM_PROMPT

    def test_glossary_panchina_present(self):
        assert "panchina" in SYSTEM_PROMPT

    def test_glossary_euroleague_hebrew_present(self):
        assert "יורוליג" in SYSTEM_PROMPT

    def test_glossary_eurocup_hebrew_present(self):
        assert "יורוקאפ" in SYSTEM_PROMPT

    def test_glossary_colpo_warning_present(self):
        # should warn not to use literal מכה
        assert "מכה" in SYSTEM_PROMPT

    def test_glossary_partenza_present(self):
        assert "partenza" in SYSTEM_PROMPT

    def test_glossary_ufficiale_present(self):
        assert "ufficiale" in SYSTEM_PROMPT

    # ── Few-shot examples ────────────────────────────────────────────────────

    def test_few_shot_asvel_example_present(self):
        assert "ASVEL" in SYSTEM_PROMPT
        assert "אסוול" in SYSTEM_PROMPT

    def test_few_shot_partizan_example_present(self):
        assert "Partizan" in SYSTEM_PROMPT
        assert "פרטיזן" in SYSTEM_PROMPT

    def test_few_shot_nba_draft_example_present(self):
        assert "NBA Draft" in SYSTEM_PROMPT

    def test_few_shot_giannis_example_present(self):
        assert "Giannis" in SYSTEM_PROMPT
        assert "יאניס" in SYSTEM_PROMPT


class TestBuildMessages:
    def test_returns_list(self):
        result = build_messages("Deni Avdija traded")
        assert isinstance(result, list)

    def test_single_user_message(self):
        result = build_messages("Some headline")
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_content_is_title(self):
        title = "Boston Celtics sign new guard"
        result = build_messages(title)
        assert result[0]["content"] == title

    def test_empty_title_allowed(self):
        result = build_messages("")
        assert result[0]["content"] == ""
