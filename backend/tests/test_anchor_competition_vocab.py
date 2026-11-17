"""The competition-vocabulary guard in clustering anchors (AUDIT_REPORT M1).

Competition words must never act as person anchors (the Bryant/Otooru false
merge). The vocabulary is loaded from facts.py; a broken import must be loud.
"""
import logging
import sys

from app.clustering import anchors


def test_competition_vocabulary_is_loaded():
    assert anchors._COMPETITIONS, "competition guard is empty: the false-merge guard is off"
    assert "יורוליג" in anchors._COMPETITIONS


def test_broken_import_logs_a_warning_and_falls_back(monkeypatch, caplog):
    # A None entry in sys.modules makes `from app.classification.facts import ...` raise ImportError.
    monkeypatch.setitem(sys.modules, "app.classification.facts", None)
    with caplog.at_level(logging.WARNING, logger=anchors.__name__):
        tokens = anchors._known_competition_tokens()
    assert tokens == frozenset()
    warnings = [r for r in caplog.records
                if r.levelno == logging.WARNING and r.name == anchors.__name__]
    assert warnings, "a failed competition-vocabulary import must be logged"
    assert "competition" in warnings[0].getMessage().lower()
