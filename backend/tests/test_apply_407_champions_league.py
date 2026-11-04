"""scripts/apply_407_champions_league.py corrects the 11 stored rows #407 reclassifies.

Id-listed, dry run by default. It rewrites only the facts #407 changes (sport, league,
competitions, entities, trace) and refuses a row whose rerun would also change something
else, or whose stored facts did not come from the rules path (a rules-only rerun would drop
LLM-assisted facts).
"""

import importlib.util
from pathlib import Path

from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config

_SPEC = importlib.util.spec_from_file_location(
    "apply_407", Path(__file__).resolve().parents[1] / "scripts" / "apply_407_champions_league.py"
)
apply_407 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(apply_407)

TITLE = "סאנוגו כיכב, הפועל חולון ניצחה לראשונה בליגת האלופות"
SUBTITLE = (
    "אחרי שהפסידה במחזור הפתיחה של ליגת האלופות וגם במחזור הפתיחה של ליגת העל, הפועל חולון "
    "התאוששה הערב (רביעי) עם ניצחון חוץ 84:86 על ספרטק סובוטיצה בסרביה."
)


def _rerun():
    item = RawSourceItem(source_id="walla_sport", url="https://sports.walla.co.il/item/3872248",
                         title=TITLE, published_at=None, summary=SUBTITLE)
    article, _, _ = ingestion_service._normalise(item, get_source_config("walla_sport"))
    return article


def _stored(**over):
    """The row as stored before #407 (verbatim facts of rss_fd09dded9f014f7025c7)."""
    row = dict(
        classified_by="rules", event_type="match_result", importance=_rerun().importance,
        sport="football", league="UEFA Champions League", primary_competition="comp:ucl",
        article_competitions=["comp:ligat_haal"], entity_ids=[], entities=[],
    )
    row.update(over)
    return row


def test_the_id_list_is_the_eleven_reclassified_rows():
    assert len(apply_407.ROW_IDS) == 11
    assert len(set(apply_407.ROW_IDS)) == 11
    assert all(i.startswith("rss_") for i in apply_407.ROW_IDS)
    assert "rss_fd09dded9f014f7025c7" in apply_407.ROW_IDS


def test_plans_only_the_facts_407_changes():
    plan = apply_407.plan_row(_stored(), _rerun())
    assert plan["status"] == "correct"
    assert set(plan["after"]) <= set(apply_407.REWRITTEN_FIELDS)
    assert plan["after"]["sport"] == "basketball"
    assert plan["after"]["primary_competition"] == "comp:bcl"
    assert plan["after"]["entity_ids"] == ["team:hapoel_holon"]
    assert plan["before"]["sport"] == "football"


def test_already_correct_row_is_a_no_op():
    a = _rerun()
    stored = _stored(sport=a.sport, league=a.league, primary_competition=a.primary_competition,
                     article_competitions=list(a.article_competitions),
                     entity_ids=list(a.entity_ids), entities=list(a.entities))
    assert apply_407.plan_row(stored, a)["status"] == "unchanged"


def test_refuses_a_row_with_llm_assisted_facts():
    plan = apply_407.plan_row(_stored(classified_by="llm"), _rerun())
    assert plan["status"] == "refused"
    assert "classified_by" in plan["reason"]


def test_refuses_when_the_rerun_would_change_the_event():
    plan = apply_407.plan_row(_stored(event_type="news"), _rerun())
    assert plan["status"] == "refused"
    assert "event_type" in plan["reason"]
