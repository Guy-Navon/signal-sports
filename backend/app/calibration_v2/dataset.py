"""
Calibration V2 dataset — the single versioned source of truth.

v3 (issue #80): coverage-driven expansion for the explicit-interests
milestone. Calibration's role is now nuance-within-declared-interests
(docs/INTERESTS.md), so EVERY selectable scope (taxonomy/policy.py) must be
calibratable:

- each selectable competition has ≥4 entity-less items spanning ≥3 event
  types and ≥2 importance levels (the estimator's support ≥2 with room for
  event deltas);
- entity contrast is no longer Maccabi/Deni-centric: 6 contrast entities
  (Maccabi TLV bb, Hapoel TLV bb, Lakers, Real Madrid bb, Maccabi Haifa fc,
  Deni Avdija), each paired with same-group baseline items;
- football is competition-tagged (Ligat ha'Al / Leumit) with sport-scoped
  probes kept for the sport baseline; tennis slams are tagged per
  tournament with the slam-vs-early-round pattern preserved.

The coverage contract is enforced by tests/test_calibration_coverage.py
(generated over the selectable-scope list — not hand-counted). Tagging is
canonical (comp:*/team:*/player:* ids). Entity-tagged items are EXCLUDED
from scope baselines by the estimator — they measure the entity, not the
league.

v2 responses are ignored at read time (get_responses filters by
dataset_version); unknown ids are ignored by inference (version-drift
fail-safe).
"""
from dataclasses import dataclass
from typing import Optional

CALIBRATION_DATASET_VERSION = 3


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
        id="cal3_nba_role_signing",
        title="קבוצת NBA מחתימה שחקן רוטציה בחוזה לשנתיים",
        sport="basketball", competition_id="comp:nba",
        event_type="signing", importance="medium",
        contrast_group="lakers_vs_nba",
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
    CalibrationItem(
        id="cal3_nba_lakers_signing",
        title="הלייקרס מחתימים כוכב חופשי בחוזה ענק",
        sport="basketball", competition_id="comp:nba",
        entity_ids=("team:la_lakers",),
        event_type="signing", importance="high",
        contrast_group="lakers_vs_nba",
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
        contrast_group="real_vs_el",
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
    CalibrationItem(
        id="cal3_el_real_signing",
        title="ריאל מדריד מחתימה סנטר דומיננטי לקראת עונת היורוליג",
        sport="basketball", competition_id="comp:euroleague",
        entity_ids=("team:real_madrid_bb",),
        event_type="signing", importance="high",
        contrast_group="real_vs_el",
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
        contrast_group="hapoel_vs_ibl",
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
    CalibrationItem(
        id="cal3_ibl_hapoel_game",
        title="הפועל תל אביב גוברת על הפועל ירושלים במשחק צמרת",
        sport="basketball", competition_id="comp:ibl",
        entity_ids=("team:hapoel_tlv_bb",),
        event_type="match_result", importance="high",
        contrast_group="hapoel_vs_ibl",
    ),
    # ── EuroCup (comp:eurocup) ───────────────────────────────────────────────
    CalibrationItem(
        id="cal3_ec_title",
        title="אלופת היורוקאפ הוכתרה אחרי סדרת גמר צמודה",
        sport="basketball", competition_id="comp:eurocup",
        event_type="title_win", importance="high",
    ),
    CalibrationItem(
        id="cal3_ec_routine",
        title="מחזור ביורוקאפ: תוצאות הערב מכל המגרשים",
        sport="basketball", competition_id="comp:eurocup",
        event_type="match_result", importance="low",
    ),
    CalibrationItem(
        id="cal3_ec_signing",
        title="קבוצת יורוקאפ מחתימה פורוורד בליטי מנוסה",
        sport="basketball", competition_id="comp:eurocup",
        event_type="signing", importance="medium",
    ),
    CalibrationItem(
        id="cal3_ec_playoff",
        title="הפתעה בפלייאוף היורוקאפ: המועמדת הגדולה הודחה",
        sport="basketball", competition_id="comp:eurocup",
        event_type="playoff_result", importance="high",
    ),
    # ── Spanish ACB (comp:acb) ───────────────────────────────────────────────
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
    CalibrationItem(
        id="cal3_acb_signing",
        title="קבוצה בליגה הספרדית מחתימה גארד אמריקאי",
        sport="basketball", competition_id="comp:acb",
        event_type="signing", importance="medium",
    ),
    CalibrationItem(
        id="cal3_acb_interview",
        title="מאמן בליגה הספרדית מסכם: \"עונה של בנייה\"",
        sport="basketball", competition_id="comp:acb",
        event_type="interview", importance="low",
    ),
    # ── Turkish BSL (comp:bsl) ───────────────────────────────────────────────
    CalibrationItem(
        id="cal3_bsl_title",
        title="אליפות טורקיה בכדורסל הוכרעה במשחק חמישי סוער",
        sport="basketball", competition_id="comp:bsl",
        event_type="title_win", importance="high",
    ),
    CalibrationItem(
        id="cal3_bsl_routine",
        title="מחזור בליגה הטורקית בכדורסל: כל התוצאות",
        sport="basketball", competition_id="comp:bsl",
        event_type="match_result", importance="very_low",
    ),
    CalibrationItem(
        id="cal3_bsl_signing",
        title="קבוצה טורקית מחתימה סנטר אמריקאי מה-G ליג",
        sport="basketball", competition_id="comp:bsl",
        event_type="signing", importance="medium",
    ),
    CalibrationItem(
        id="cal3_bsl_schedule",
        title="נקבעו מועדי הפלייאוף בליגה הטורקית בכדורסל",
        sport="basketball", competition_id="comp:bsl",
        event_type="schedule", importance="very_low",
    ),
    # ── Greek Basket League (comp:greek_basket) ──────────────────────────────
    CalibrationItem(
        id="cal3_gr_title",
        title="אליפות יוון בכדורסל הוכרעה בסדרת גמר לוהטת",
        sport="basketball", competition_id="comp:greek_basket",
        event_type="title_win", importance="high",
    ),
    CalibrationItem(
        id="cal3_gr_derby",
        title="פנאתינייקוס גוברת על אולימפיאקוס בדרבי היווני הגדול",
        sport="basketball", competition_id="comp:greek_basket",
        event_type="major_match_result", importance="high",
    ),
    CalibrationItem(
        id="cal3_gr_routine",
        title="מחזור בליגה היוונית בכדורסל: תוצאות הערב",
        sport="basketball", competition_id="comp:greek_basket",
        event_type="match_result", importance="very_low",
    ),
    CalibrationItem(
        id="cal3_gr_signing",
        title="קבוצה יוונית מחתימה פורוורד לשעבר ביורוליג",
        sport="basketball", competition_id="comp:greek_basket",
        event_type="signing", importance="medium",
    ),
    # ── Italian LBA (comp:lba) ───────────────────────────────────────────────
    CalibrationItem(
        id="cal3_lba_title",
        title="אליפות איטליה בכדורסל: המנצחת הוכתרה בגמר מותח",
        sport="basketball", competition_id="comp:lba",
        event_type="title_win", importance="high",
    ),
    CalibrationItem(
        id="cal3_lba_routine",
        title="מחזור בליגה האיטלקית בכדורסל: כל התוצאות",
        sport="basketball", competition_id="comp:lba",
        event_type="match_result", importance="very_low",
    ),
    CalibrationItem(
        id="cal3_lba_signing",
        title="קבוצה איטלקית מחתימה רכז ותיק מהיורוליג",
        sport="basketball", competition_id="comp:lba",
        event_type="signing", importance="medium",
    ),
    CalibrationItem(
        id="cal3_lba_playoff",
        title="הדחה מפתיעה בפלייאוף האיטלקי בכדורסל",
        sport="basketball", competition_id="comp:lba",
        event_type="playoff_result", importance="high",
    ),
    # ── French LNB (comp:lnb) ────────────────────────────────────────────────
    CalibrationItem(
        id="cal3_lnb_title",
        title="אליפות צרפת בכדורסל הוכרעה: המחזיקה הודחה מהכתר",
        sport="basketball", competition_id="comp:lnb",
        event_type="title_win", importance="high",
    ),
    CalibrationItem(
        id="cal3_lnb_routine",
        title="מחזור בליגה הצרפתית בכדורסל: תוצאות הלילה",
        sport="basketball", competition_id="comp:lnb",
        event_type="match_result", importance="very_low",
    ),
    CalibrationItem(
        id="cal3_lnb_signing",
        title="קבוצה צרפתית מחתימה כישרון צעיר מהאקדמיה",
        sport="basketball", competition_id="comp:lnb",
        event_type="signing", importance="medium",
    ),
    CalibrationItem(
        id="cal3_lnb_negotiation",
        title="מגעים מתקדמים בצרפת: כוכב הליגה קרוב להארכת חוזה",
        sport="basketball", competition_id="comp:lnb",
        event_type="negotiation", importance="medium",
    ),
    # ── Israeli Premier League football (comp:ligat_haal) ────────────────────
    CalibrationItem(
        id="cal2_fb_routine",
        title="ליגת העל בכדורגל: טבריה ניצחה את ריינה 1-0",
        sport="football", competition_id="comp:ligat_haal",
        event_type="match_result", importance="low",
        contrast_group="haifa_vs_ligat",
    ),
    CalibrationItem(
        id="cal3_fb_derby",
        title="דרבי סוער בליגת העל הוכרע בדקה ה-90",
        sport="football", competition_id="comp:ligat_haal",
        event_type="major_match_result", importance="high",
    ),
    CalibrationItem(
        id="cal3_fb_signing",
        title="קבוצת ליגת העל מחתימה חלוץ זר לקראת העונה",
        sport="football", competition_id="comp:ligat_haal",
        event_type="signing", importance="medium",
    ),
    CalibrationItem(
        id="cal3_fb_title",
        title="אליפות ליגת העל הוכרעה במחזור האחרון בדרמה אדירה",
        sport="football", competition_id="comp:ligat_haal",
        event_type="title_win", importance="very_high",
    ),
    CalibrationItem(
        id="cal3_fb_haifa_derby",
        title="מכבי חיפה מנצחת בדרבי הצפון ומתבססת בצמרת",
        sport="football", competition_id="comp:ligat_haal",
        entity_ids=("team:maccabi_haifa_fc",),
        event_type="match_result", importance="high",
        contrast_group="haifa_vs_ligat",
    ),
    # ── Israeli Liga Leumit football (comp:leumit_fc) ────────────────────────
    CalibrationItem(
        id="cal3_lm_routine",
        title="מחזור בליגה הלאומית: כל התוצאות מהמגרשים",
        sport="football", competition_id="comp:leumit_fc",
        event_type="match_result", importance="very_low",
    ),
    CalibrationItem(
        id="cal3_lm_promotion",
        title="הוכרע: העולה החדשה לליגת העל אחרי עונה מטורפת בלאומית",
        sport="football", competition_id="comp:leumit_fc",
        event_type="title_win", importance="high",
    ),
    CalibrationItem(
        id="cal3_lm_signing",
        title="קבוצה בליגה הלאומית מחתימה קשר ותיק מליגת העל",
        sport="football", competition_id="comp:leumit_fc",
        event_type="signing", importance="low",
    ),
    CalibrationItem(
        id="cal3_lm_schedule",
        title="פורסם לוח המשחקים המלא של הליגה הלאומית",
        sport="football", competition_id="comp:leumit_fc",
        event_type="schedule", importance="very_low",
    ),
    # ── Football, sport-scoped probes (world football stays sport-level) ─────
    CalibrationItem(
        id="cal2_fb_mbappe",
        title="רשמי: אמבפה חותם בריאל מדריד בעסקת ענק היסטורית",
        sport="football",
        event_type="major_transfer", importance="very_high",
    ),
    CalibrationItem(
        id="cal2_fb_ucl_title",
        title="אלופת אירופה הוכרעה: דרמה בגמר הצ'מפיונס ליג",
        sport="football",
        event_type="title_win", importance="very_high",
    ),
    # ── Wimbledon (comp:wimbledon) ───────────────────────────────────────────
    CalibrationItem(
        id="cal3_tn_wim_winner",
        title="הזוכה בווימבלדון הוכתר אחרי גמר בלתי נשכח",
        sport="tennis", competition_id="comp:wimbledon",
        event_type="grand_slam_winner", importance="very_high",
    ),
    CalibrationItem(
        id="cal2_tn_gs_final",
        title="נקבע הגמר הגדול של ווימבלדון: שני הטובים בעולם ייפגשו",
        sport="tennis", competition_id="comp:wimbledon",
        event_type="grand_slam_final", importance="high",
    ),
    CalibrationItem(
        id="cal2_tn_early_round",
        title="אלקראס מעפיל לסיבוב השלישי בווימבלדון בניצחון קליל",
        sport="tennis", competition_id="comp:wimbledon",
        event_type="early_round_result", importance="low",
    ),
    CalibrationItem(
        id="cal3_tn_wim_schedule",
        title="פורסם סדר היום המלא של רבע גמר ווימבלדון",
        sport="tennis", competition_id="comp:wimbledon",
        event_type="schedule", importance="very_low",
    ),
    # ── Roland Garros (comp:roland_garros) ───────────────────────────────────
    CalibrationItem(
        id="cal2_tn_gs_winner",
        title="אלקראס זוכה ברולאן גארוס אחרי גמר בן חמישה מערכות",
        sport="tennis", competition_id="comp:roland_garros",
        event_type="grand_slam_winner", importance="very_high",
    ),
    CalibrationItem(
        id="cal3_tn_rg_final",
        title="גמר רולאן גארוס נקבע: קרב צמרת על החימר בפריז",
        sport="tennis", competition_id="comp:roland_garros",
        event_type="grand_slam_final", importance="high",
    ),
    CalibrationItem(
        id="cal3_tn_rg_early",
        title="הפתעה קלה בסיבוב השני של רולאן גארוס",
        sport="tennis", competition_id="comp:roland_garros",
        event_type="early_round_result", importance="low",
    ),
    CalibrationItem(
        id="cal3_tn_rg_schedule",
        title="לוח המשחקים ליום שלישי ברולאן גארוס פורסם",
        sport="tennis", competition_id="comp:roland_garros",
        event_type="schedule", importance="very_low",
    ),
    # ── US Open (comp:us_open) ───────────────────────────────────────────────
    CalibrationItem(
        id="cal3_tn_us_winner",
        title="אלוף חדש באליפות ארה\"ב הפתוחה אחרי גמר דרמטי בניו יורק",
        sport="tennis", competition_id="comp:us_open",
        event_type="grand_slam_winner", importance="very_high",
    ),
    CalibrationItem(
        id="cal3_tn_us_final",
        title="נקבע גמר אליפות ארה\"ב הפתוחה: מפגש בין שני דורות",
        sport="tennis", competition_id="comp:us_open",
        event_type="grand_slam_final", importance="high",
    ),
    CalibrationItem(
        id="cal3_tn_us_early",
        title="תוצאות הסיבוב הראשון באליפות ארה\"ב הפתוחה",
        sport="tennis", competition_id="comp:us_open",
        event_type="early_round_result", importance="low",
    ),
    CalibrationItem(
        id="cal3_tn_us_schedule",
        title="סדר היום באליפות ארה\"ב הפתוחה: המשחקים הבולטים הלילה",
        sport="tennis", competition_id="comp:us_open",
        event_type="schedule", importance="very_low",
    ),
    # ── Australian Open (comp:australian_open) ───────────────────────────────
    CalibrationItem(
        id="cal3_tn_au_winner",
        title="הזוכה באליפות אוסטרליה הפתוחה הוכתר במלבורן",
        sport="tennis", competition_id="comp:australian_open",
        event_type="grand_slam_winner", importance="very_high",
    ),
    CalibrationItem(
        id="cal3_tn_au_final",
        title="גמר אליפות אוסטרליה נקבע: שיא צפייה צפוי במלבורן",
        sport="tennis", competition_id="comp:australian_open",
        event_type="grand_slam_final", importance="high",
    ),
    CalibrationItem(
        id="cal3_tn_au_early",
        title="ניצחון שגרתי בסיבוב השני של אליפות אוסטרליה",
        sport="tennis", competition_id="comp:australian_open",
        event_type="early_round_result", importance="low",
    ),
    CalibrationItem(
        id="cal3_tn_au_schedule",
        title="פורסם לוח המשחקים ליום הרביעי של אליפות אוסטרליה",
        sport="tennis", competition_id="comp:australian_open",
        event_type="schedule", importance="very_low",
    ),
    # ── Tennis, sport-scoped probes ──────────────────────────────────────────
    CalibrationItem(
        id="cal3_tn_atp_routine",
        title="טורניר ATP 250: תוצאות היום הראשון",
        sport="tennis",
        event_type="match_result", importance="very_low",
    ),
    CalibrationItem(
        id="cal3_tn_ranking",
        title="עדכון דירוג ה-ATP: תזוזות בצמרת העולמית",
        sport="tennis",
        event_type="news", importance="low",
    ),
)

assert len(CALIBRATION_ITEMS) == 73

_BY_ID = {item.id: item for item in CALIBRATION_ITEMS}


def item_by_id(item_id: str) -> Optional[CalibrationItem]:
    return _BY_ID.get(item_id)
