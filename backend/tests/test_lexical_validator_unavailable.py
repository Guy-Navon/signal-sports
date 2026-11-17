"""The lexical anchor validator must not switch itself off silently (AUDIT_REPORT L5).

When wordfreq cannot be imported the validator abstains, which changes
clustering behavior; that has to leave one WARNING in the log per process.
"""

import logging
import sys

from app.clustering import anchor_validators
from app.clustering.anchor_validators import LexicalFrequencyValidator


def test_missing_wordfreq_logs_one_warning(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "wordfreq", None)  # makes `import wordfreq` raise
    monkeypatch.setattr(anchor_validators, "_lexical_unavailable_logged", False)

    with caplog.at_level(logging.WARNING, logger=anchor_validators.__name__):
        first = LexicalFrequencyValidator()
        second = LexicalFrequencyValidator()

    assert not first.available() and not second.available()
    assert first.validator_version == "unavailable"
    warnings = [r for r in caplog.records
                if r.levelno == logging.WARNING and "wordfreq" in r.getMessage()]
    assert len(warnings) == 1


def test_available_wordfreq_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger=anchor_validators.__name__):
        validator = LexicalFrequencyValidator()
    assert validator.available()
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
