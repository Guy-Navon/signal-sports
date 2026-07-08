"""
Calibration V2 dataset (issue #33) — the single versioned source of truth.

24 synthetic, fully-tagged examples designed factorially over
(scope × major/routine event) for NBA, EuroLeague, IBL, one secondary
domestic league (ACB), football and tennis — plus targeted contrast pairs:

- entity-vs-league: Maccabi signing vs generic IBL signing
  (``maccabi_vs_ibl``), Maccabi EuroLeague game vs generic EuroLeague game
  (``maccabi_vs_el``), Deni performances vs generic NBA results
  (``deni_vs_nba``).
- event-vs-scope: NBA interview vs NBA game/trade items, EuroLeague
  interview vs EuroLeague items, IBL schedule probe.

Tagging is canonical (comp:*/team:*/player:* ids). Entity-tagged items are
EXCLUDED from scope baselines by the estimator — they measure the entity,
not the league. Replaces both stale datasets (the 16-row backend seed and
the 43-headline frontend file).
"""
from dataclasses import dataclass, field
from typing import Optional

CALIBRATION_DATASET_VERSION = 2


@dataclass(frozen=True)
class CalibrationItem:
    id: str
    title: str
    sport: str
    competition_id: Optional[str] = None    # comp:* | None (sport-scoped)
    entity_ids: tuple[str, ...] = ()        # team:*/player:* — contrast items only
    event_type: str = "news"
    importance: str = "medium"
    contrast_group: Optional[str] = None    # links entity items to their baseline


CALIBRATION_ITEMS: tuple[CalibrationItem, ...] = (
    # ── NBA (comp:nba) ────────────────────────────────────────────────────────
    CalibrationItem(
        id="cal2_nba_star_trade",
        title="בלוקבאסטר ב-NBA: כוכב-על נסחר בעסקת ענק בין שלוש קבוצות",
        sport="basketball", competition_id="comp:nba",
        event_type="star_trade", importance="very_high",
    ),
    CalibrationItem(
        id="cal2_nba_routine_result",
        title="הורנטס מנצחים את הוויזארדס 105-112 במשחק ליגה שגרתי",
        sport="basketball", competition_id="comp:nba",
        event_type="regular_season_result", importance="low",
        contrast_group="deni_vs_nba",
    ),
    CalibrationItem(
        id="cal2_nba_finals",
        title="גמר ה-NBA הוכרע: האליפות נחתמה במשחק שביעי דרמטי",
        sport="basketball", competition_id="comp:nba",
        event_type="finals_result", importance="very_high",
    ),
    CalibrationItem(
        id="cal2_nba_interview",
        title="שחקן NBA בראיון: \"זאת העונה הכי טובה בקריירה שלי\"",
        sport="basketball", competition_id="comp:nba",
        event_type="interview", importance="low",
        contrast_group="event_interview_nba",
    ),
    CalibrationItem(
        id="cal2_nba_deni_big_game",
        title="דני אבדיה קורע את הרשתות: 32 נקודות בניצחון פורטלנד",
        sport="basketball", competition_id="comp:nba",
        entity_ids=("player:deni_avdija",),
        event_type="record", importance="high",
        contrast_group="deni_vs_nba",
    ),
    CalibrationItem(
        id="cal2_nba_deni_quiet_game",
        title="ערב שקט לדני אבדיה: 8 נקודות בלבד בניצחון של פורטלנד",
        sport="basketball", competition_id="comp:nba",
        entity_ids=("player:deni_avdija",),
        event_type="regular_season_result", importance="low",
        contrast_group="deni_vs_nba",
    ),
    # ── EuroLeague (comp:euroleague) ──────────────────────────────────────────
    CalibrationItem(
        id="cal2_el_title",
        title="הפיינל פור הוכרע: אלופת יורוליג חדשה הוכתרה",
        sport="basketball", competition_id="comp:euroleague",
        event_type="title_win", importance="very_high",
    ),
    CalibrationItem(
        id="cal2_el_routine_result",
        title="מחזור שגרתי ביורוליג: כל התוצאות מהערב",
        sport="basketball", competition_id="comp:euroleague",
        event_type="match_result", importance="low",
        contrast_group="maccabi_vs_el",
    ),
    CalibrationItem(
        id="cal2_el_signing",
        title="קבוצת יורוליג מחתימה גארד אמריקאי מה-NBA",
        sport="basketball", competition_id="comp:euroleague",
        event_type="signing", importance="medium",
    ),
    CalibrationItem(
        id="cal2_el_interview",
        title="מאמן ביורוליג בראיון לפני המחזור: \"נילחם על כל כדור\"",
        sport="basketball", competition_id="comp:euroleague",
        event_type="interview", importance="low",
        contrast_group="event_interview_el",
    ),
    CalibrationItem(
        id="cal2_el_maccabi_game",
        title="מכבי תל אביב פוגשת את ריאל מדריד במשחק צמרת ביורוליג",
        sport="basketball", competition_id="comp:euroleague",
        entity_ids=("team:maccabi_tlv_bb",),
        event_type="match_result", importance="high",
        contrast_group="maccabi_vs_el",
    ),
    # ── Israeli Basketball League (comp:ibl) ─────────────────────────────────
    CalibrationItem(
        id="cal2_ibl_maccabi_signing",
        title="מכבי תל אביב מחתימה רכז חדש לקראת העונה",
        sport="basketball", competition_id="comp:ibl",
        entity_ids=("team:maccabi_tlv_bb",),
        event_type="signing", importance="high",
        contrast_group="maccabi_vs_ibl",
    ),
    CalibrationItem(
        id="cal2_ibl_generic_signing",
        title="קבוצה בליגת ווינר סל מחתימה פורוורד אמריקאי",
        sport="basketball", competition_id="comp:ibl",
        event_type="signing", importance="medium",
        contrast_group="maccabi_vs_ibl",
    ),
    CalibrationItem(
        id="cal2_ibl_routine_result",
        title="מחזור בליגת ווינר סל: תוצאות כל המשחקים",
        sport="basketball", competition_id="comp:ibl",
        event_type="match_result", importance="low",
    ),
    CalibrationItem(
        id="cal2_ibl_playoff",
        title="דרמה בפלייאוף ליגת ווינר סל: הסדרה הוכרעה במשחק חמישי",
        sport="basketball", competition_id="comp:ibl",
        event_type="playoff_result", importance="high",
    ),
    CalibrationItem(
        id="cal2_ibl_schedule",
        title="פורסם לוח המשחקים של המחזור הבא בליגת ווינר סל",
        sport="basketball", competition_id="comp:ibl",
        event_type="schedule", importance="very_low",
        contrast_group="event_schedule_ibl",
    ),
    # ── Secondary domestic league (comp:acb) ─────────────────────────────────
    CalibrationItem(
        id="cal2_acb_title",
        title="אליפות ספרד בכדורסל הוכרעה בגמר דרמטי",
        sport="basketball", competition_id="comp:acb",
        event_type="title_win", importance="high",
    ),
    CalibrationItem(
        id="cal2_acb_routine",
        title="מחזור שגרתי בליגה הספרדית בכדורסל: תוצאות הערב",
        sport="basketball", competition_id="comp:acb",
        event_type="match_result", importance="very_low",
    ),
    # ── Football (sport-scoped) ───────────────────────────────────────────────
    CalibrationItem(
        id="cal2_fb_mbappe",
        title="רשמי: אמבפה חותם בריאל מדריד בעסקת ענק היסטורית",
        sport="football",
        event_type="major_transfer", importance="very_high",
    ),
    CalibrationItem(
        id="cal2_fb_routine",
        title="ליגת העל בכדורגל: טבריה ניצחה את ריינה 1-0",
        sport="football",
        event_type="match_result", importance="low",
    ),
    CalibrationItem(
        id="cal2_fb_ucl_title",
        title="אלופת אירופה הוכרעה: דרמה בגמר הצ'מפיונס ליג",
        sport="football",
        event_type="title_win", importance="very_high",
    ),
    # ── Tennis (sport-scoped) ─────────────────────────────────────────────────
    CalibrationItem(
        id="cal2_tn_gs_winner",
        title="אלקראס זוכה ברולאן גארוס אחרי גמר בן חמישה מערכות",
        sport="tennis",
        event_type="grand_slam_winner", importance="very_high",
    ),
    CalibrationItem(
        id="cal2_tn_early_round",
        title="אלקראס מעפיל לסיבוב השלישי בווימבלדון בניצחון קליל",
        sport="tennis",
        event_type="early_round_result", importance="low",
    ),
    CalibrationItem(
        id="cal2_tn_gs_final",
        title="נקבע הגמר הגדול של ווימבלדון: שני הטובים בעולם ייפגשו",
        sport="tennis",
        event_type="grand_slam_final", importance="high",
    ),
)

assert len(CALIBRATION_ITEMS) == 24

_BY_ID = {item.id: item for item in CALIBRATION_ITEMS}


def item_by_id(item_id: str) -> Optional[CalibrationItem]:
    return _BY_ID.get(item_id)
