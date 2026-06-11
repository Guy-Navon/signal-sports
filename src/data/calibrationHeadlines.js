/**
 * Synthetic calibration headlines used to infer user preferences.
 * Each headline is pre-tagged with the same metadata fields used by real articles.
 * These titles are intentionally realistic but completely fictional.
 */

export const calibrationHeadlines = [
  // ── Maccabi Tel Aviv Basketball ──────────────────────────────
  {
    id: "cal_001",
    title: "מכבי ת״א בשלבי מו״מ מתקדמים עם גארד יורוליגי מסרביה",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "negotiation",
    importance: "high",
    tags: ["מכבי ת״א", "מו״מ", "יורוליג", "רכש"]
  },
  {
    id: "cal_002",
    title: "רשמי: מכבי ת״א חתמה על פורוורד אמריקאי לשלוש עונות",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "signing",
    importance: "high",
    tags: ["מכבי ת״א", "חתימה", "רכש"]
  },
  {
    id: "cal_003",
    title: "מכבי ת״א: שחקן הפיבוט המרכזי ייעדר חודש עקב פציעה בברך",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "injury",
    importance: "high",
    tags: ["מכבי ת״א", "פציעה"]
  },
  {
    id: "cal_004",
    title: "לפי דיווחים: מכבי ת״א בודקת סנטר ממוזמביק שמשחק ב-EuroLeague",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "candidate",
    importance: "medium",
    tags: ["מכבי ת״א", "מועמד", "יורוליג"]
  },
  {
    id: "cal_005",
    title: "מאמן מכבי ת״א בראיון לפני עונה: ״אנחנו מוכנים לאתגרי היורוליג״",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "interview",
    importance: "medium",
    tags: ["מכבי ת״א", "ראיון", "מאמן"]
  },
  {
    id: "cal_006",
    title: "מכבי ת״א מנצחת 88-75 בגביע ידידות לפני עונה",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "friendly_match",
    importance: "low",
    tags: ["מכבי ת״א", "ידידות", "תוצאה"]
  },

  // ── EuroLeague (non-Maccabi) ──────────────────────────────────
  {
    id: "cal_007",
    title: "ריאל מדריד גומרת עניין עם כוכב EuroLeague — מהלך קיץ ענקי",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Real Madrid Basketball"],
    eventType: "major_signing",
    importance: "high",
    tags: ["יורוליג", "ריאל מדריד", "רכש"]
  },
  {
    id: "cal_008",
    title: "פנרבצ׳ה מנצחת את CSKA מוסקבה 83-77 בסיבוב הרגיל ביורוליג",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Fenerbahce", "CSKA Moscow"],
    eventType: "match_result",
    importance: "medium",
    tags: ["יורוליג", "פנרבצ׳ה", "CSKA", "תוצאה"]
  },
  {
    id: "cal_009",
    title: "Final Four יורוליג: אולימפיאקוס עולה לגמר עם ניצחון 92-88",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Olympiacos"],
    eventType: "finals_result",
    importance: "very_high",
    tags: ["יורוליג", "Final Four", "גמר", "אולימפיאקוס"]
  },

  // ── Israeli Basketball (non-Maccabi) ──────────────────────────
  {
    id: "cal_010",
    title: "אלוף! הפועל ירושלים זוכה בגביע המדינה לכדורסל לאחר גמר דרמטי",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Hapoel Jerusalem Basketball"],
    eventType: "title_win",
    importance: "high",
    tags: ["כדורסל ישראלי", "הפועל ירושלים", "גביע", "אלוף"]
  },

  // ── NBA ───────────────────────────────────────────────────────
  {
    id: "cal_011",
    title: "הורנטס מנצחת את ויזארדס 112-104 בסיבוב הרגיל של ה-NBA",
    sport: "basketball",
    league: "NBA",
    entities: ["Charlotte Hornets", "Washington Wizards"],
    eventType: "regular_season_result",
    importance: "low",
    tags: ["NBA", "הורנטס", "ויזארדס", "תוצאה"]
  },
  {
    id: "cal_012",
    title: "דני אבדיה עשוי לעבור בטרייד לקבוצה ממזרח ה-NBA לפי דיווח",
    sport: "basketball",
    league: "NBA",
    entities: ["Deni Avdija", "Portland Trail Blazers"],
    eventType: "major_trade",
    importance: "high",
    tags: ["NBA", "דני אבדיה", "טרייד"]
  },
  {
    id: "cal_013",
    title: "דני אבדיה ייעדר שלושה משחקים בגלל נקע בקרסול",
    sport: "basketball",
    league: "NBA",
    entities: ["Deni Avdija"],
    eventType: "injury",
    importance: "medium",
    tags: ["NBA", "דני אבדיה", "פציעה"]
  },
  {
    id: "cal_014",
    title: "עסקת ענק ב-NBA: לייקרס וסלטיקס מסכמות על חילוף כוכבים היסטורי",
    sport: "basketball",
    league: "NBA",
    entities: ["Los Angeles Lakers", "Boston Celtics"],
    eventType: "star_trade",
    importance: "very_high",
    tags: ["NBA", "לייקרס", "סלטיקס", "טרייד", "כוכב"]
  },
  {
    id: "cal_015",
    title: "סלטיקס זוכים ב-NBA Finals אחרי ניצחון 107-99 במשחק 7",
    sport: "basketball",
    league: "NBA",
    entities: ["Boston Celtics", "Golden State Warriors"],
    eventType: "finals_result",
    importance: "very_high",
    tags: ["NBA", "פיינאלס", "סלטיקס", "אלוף"]
  },
  {
    id: "cal_016",
    title: "תצפית: 5 שחקנים שכדאי לעקוב אחריהם הלילה ב-NBA",
    sport: "basketball",
    league: "NBA",
    entities: [],
    eventType: "generic_preview",
    importance: "low",
    tags: ["NBA", "תצפית", "שחקנים"]
  },

  // ── European Domestic Basketball ──────────────────────────────
  {
    id: "cal_017",
    title: "ברצלונה מנצחת את ריאל מדריד 89-78 בגמר פלייאוף ה-ACB",
    sport: "basketball",
    league: "Spanish ACB",
    entities: ["FC Barcelona Basketball", "Real Madrid Basketball"],
    eventType: "playoff_result",
    importance: "high",
    tags: ["ACB", "ספרד", "ברצלונה", "ריאל מדריד", "פלייאוף"]
  },
  {
    id: "cal_018",
    title: "דרבי יוון: אולימפיאקוס מנצחת את פנתינאיקוס 95-88 בקרב ענקים",
    sport: "basketball",
    league: "Greek Basket League",
    entities: ["Olympiacos", "Panathinaikos"],
    eventType: "major_match_result",
    importance: "high",
    tags: ["יוון", "דרבי", "אולימפיאקוס", "פנתינאיקוס"]
  },
  {
    id: "cal_019",
    title: "LDLC ASVEL חותמת על שחקן EuroLeague לקראת העונה הצרפתית",
    sport: "basketball",
    league: "French LNB",
    entities: ["LDLC ASVEL"],
    eventType: "major_signing",
    importance: "medium",
    tags: ["LNB", "צרפת", "ASVEL", "חתימה"]
  },
  {
    id: "cal_020",
    title: "תצפית: מילאנו מול בולוניה — מי ינצח בסיבוב 24 של הליגה האיטלקית?",
    sport: "basketball",
    league: "Italian LBA",
    entities: ["Olimpia Milano"],
    eventType: "generic_preview",
    importance: "low",
    tags: ["LBA", "איטליה", "מילאנו", "תצפית"]
  },

  // ── Tennis ────────────────────────────────────────────────────
  {
    id: "cal_021",
    title: "אלקראז זוכה ברולאן גארוס ומוסיף גראנד סלאם שלישי לקולקציה",
    sport: "tennis",
    league: "Grand Slam",
    entities: ["Carlos Alcaraz"],
    eventType: "grand_slam_winner",
    importance: "very_high",
    tags: ["טניס", "גראנד סלאם", "אלקראז", "רולאן גארוס"]
  },
  {
    id: "cal_022",
    title: "אלקראז מנצח בסיבוב הראשון בוימבלדון 3-0 בסטים בקלות יחסית",
    sport: "tennis",
    league: "Grand Slam",
    entities: ["Carlos Alcaraz"],
    eventType: "early_round_result",
    importance: "low",
    tags: ["טניס", "וימבלדון", "אלקראז", "סיבוב ראשון"]
  },
  {
    id: "cal_023",
    title: "סקירה שבועית: מה מחכה לטניס העולמי בעונת הקיץ הקרובה",
    sport: "tennis",
    league: null,
    entities: [],
    eventType: "generic_news",
    importance: "low",
    tags: ["טניס", "סקירה", "עונה"]
  },

  // ── Football ─────────────────────────────────────────────────
  {
    id: "cal_024",
    title: "אמבפה חוזר ל-PSG — מגעים ראשוניים אושרו לפי דיווח צרפתי",
    sport: "football",
    league: "Ligue 1",
    entities: ["Kylian Mbappe", "Paris Saint-Germain"],
    eventType: "major_transfer",
    importance: "very_high",
    tags: ["כדורגל", "אמבפה", "PSG", "טרנספר"]
  },
  {
    id: "cal_025",
    title: "הפועל פתח תקווה ניצחת את בני יהודה 2-1 בסיבוב 18 של ליגת העל",
    sport: "football",
    league: "Israeli Premier League",
    entities: ["Hapoel Petah Tikva", "Bnei Yehuda"],
    eventType: "regular_season_result",
    importance: "low",
    tags: ["כדורגל", "ליגת על", "פתח תקווה", "בני יהודה"]
  },
  {
    id: "cal_026",
    title: "לו״ז מלא: כל משחקי ה-UEFA Champions League השבוע",
    sport: "football",
    league: null,
    entities: [],
    eventType: "schedule",
    importance: "very_low",
    tags: ["כדורגל", "צ׳מפיונס ליג", "לוח משחקים"]
  },

  // ── NBA — bonus ───────────────────────────────────────────────
  {
    id: "cal_027",
    title: "היסטוריה: שחקן NBA שובר שיא של 40 שנה עם 73 נקודות במשחק",
    sport: "basketball",
    league: "NBA",
    entities: ["Golden State Warriors"],
    eventType: "record",
    importance: "very_high",
    tags: ["NBA", "שיא", "היסטוריה", "73 נקודות"]
  },
  {
    id: "cal_028",
    title: "ניתוח: הפועל ת״א כדורסל — מה צפוי בסיבוב 25 של הליגה?",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Hapoel Tel Aviv Basketball"],
    eventType: "generic_preview",
    importance: "low",
    tags: ["כדורסל ישראלי", "הפועל ת״א", "תצפית"]
  }
];

export const UNIQUE_SPORTS = [...new Set(calibrationHeadlines.map(h => h.sport))];
