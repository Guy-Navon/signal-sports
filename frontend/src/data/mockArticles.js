// Mock articles dataset - at least 35 articles covering all required scenarios
// All dates relative to 2026-06-11

export const mockArticles = [
  // ============================================================
  // MACCABI TEL AVIV BASKETBALL - cluster: negotiation (3 sources)
  // ============================================================
  {
    id: "article_001",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=1",
    title: "דיווח: מכבי ת״א במו״מ עם גארד יורוליג",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T08:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "negotiation",
    importance: "high",
    confidence: 0.92,
    tags: ["מכבי ת״א", "יורוליג", "רכש", "מו״מ"],
    clusterId: "cluster_maccabi_negotiation_001"
  },
  {
    id: "article_002",
    source: "one",
    sourceDisplayName: "ONE",
    url: "https://www.one.co.il/Article/1",
    title: "אחד: מכבי ת״א בשלבי משא ומתן עם שחקן מיורוליג",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T08:30:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "negotiation",
    importance: "high",
    confidence: 0.88,
    tags: ["מכבי ת״א", "יורוליג", "רכש", "מו״מ"],
    clusterId: "cluster_maccabi_negotiation_001"
  },
  {
    id: "article_003",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/3",
    title: "מכבי ת״א בודקת גארד ששיחק ביורוליג העונה",
    originalTitle: "Maccabi Tel Aviv monitoring EuroLeague guard",
    translatedTitle: "מכבי ת״א בודקת גארד ששיחק ביורוליג העונה",
    language: "en",
    publishedAt: "2026-06-11T09:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "candidate",
    importance: "medium",
    confidence: 0.82,
    tags: ["מכבי ת״א", "יורוליג", "מועמד"],
    clusterId: "cluster_maccabi_negotiation_001"
  },

  // ============================================================
  // MACCABI TEL AVIV - SIGNING
  // ============================================================
  {
    id: "article_004",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=4",
    title: "רשמי: מכבי ת״א חתמה על קנטר מצרפת",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-10T14:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "signing",
    importance: "high",
    confidence: 0.97,
    tags: ["מכבי ת״א", "חתימה", "רכש"],
    clusterId: null
  },

  // ============================================================
  // MACCABI TEL AVIV - INJURY
  // ============================================================
  {
    id: "article_005",
    source: "one",
    sourceDisplayName: "ONE",
    url: "https://www.one.co.il/Article/5",
    title: "פציעה: שחקן מכבי ת״א יהיה מחוץ לפעילות שלושה שבועות",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T07:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "injury",
    importance: "high",
    confidence: 0.95,
    tags: ["מכבי ת״א", "פציעה"],
    clusterId: null
  },

  // ============================================================
  // MACCABI TEL AVIV - CANDIDATE RUMOR
  // ============================================================
  {
    id: "article_006",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/6",
    title: "מכבי ת״א מתעניינת בפורוורד סרבי שפיתח בוטה בסרביה",
    originalTitle: "Maccabi Tel Aviv interested in Serbian forward from the Adriatic League",
    translatedTitle: "מכבי ת״א מתעניינת בפורוורד סרבי שפיתח בוטה בסרביה",
    language: "en",
    publishedAt: "2026-06-10T11:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "candidate",
    importance: "medium",
    confidence: 0.75,
    tags: ["מכבי ת״א", "מועמד", "רכש"],
    clusterId: null
  },

  // ============================================================
  // ODED KATASH INTERVIEW
  // ============================================================
  {
    id: "article_007",
    source: "walla",
    sourceDisplayName: "וואלה ספורט",
    url: "https://sport.walla.co.il/article/7",
    title: "קטש: ״הקבוצה מוכנה לאתגרי העונה הבאה, נפתיע״",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-09T16:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball", "Oded Katash"],
    eventType: "interview",
    importance: "medium",
    confidence: 0.90,
    tags: ["מכבי ת״א", "קטש", "ראיון"],
    clusterId: null
  },

  // ============================================================
  // MACCABI FRIENDLY MATCH RESULT
  // ============================================================
  {
    id: "article_008",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=8",
    title: "מכבי ת״א ניצחה בגביע הידידות 82-74 מול פנתרוס",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-08T20:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "friendly_match",
    importance: "low",
    confidence: 0.85,
    tags: ["מכבי ת״א", "משחק ידידות", "תוצאה"],
    clusterId: null
  },

  // ============================================================
  // MACCABI MATCH SUMMARY
  // ============================================================
  {
    id: "article_009",
    source: "israel_hayom",
    sourceDisplayName: "ישראל היום ספורט",
    url: "https://www.israelhayom.co.il/sport/article/9",
    title: "סיכום: מכבי ת״א שוברת שיא ניצחונות בבית עם 91-78 על הפועל ירושלים",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-07T22:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "match_summary",
    importance: "medium",
    confidence: 0.92,
    tags: ["מכבי ת״א", "סיכום משחק", "ליגה"],
    clusterId: null
  },

  // ============================================================
  // EUROLEAGUE MAJOR TRANSFER
  // ============================================================
  {
    id: "article_010",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/10",
    title: "ריאל מדריד גומרת עניין עם סנטר של אנדולו אפס - מהלך ענק",
    originalTitle: "Real Madrid finalizing deal for Anadolu Efes center – major EuroLeague move",
    translatedTitle: "ריאל מדריד גומרת עניין עם סנטר של אנדולו אפס - מהלך ענק",
    language: "en",
    publishedAt: "2026-06-11T10:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Real Madrid Basketball", "Anadolu Efes"],
    eventType: "major_signing",
    importance: "high",
    confidence: 0.88,
    tags: ["יורוליג", "ריאל מדריד", "רכש", "חתימה"],
    clusterId: null
  },

  // ============================================================
  // EUROLEAGUE REGULAR RESULT
  // ============================================================
  {
    id: "article_011",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/11",
    title: "פנרבצ׳ה מנצחת את ולנסיה 89-75 בסיבוב הרגיל",
    originalTitle: "Fenerbahce beats Valencia 89-75 in regular season",
    translatedTitle: "פנרבצ׳ה מנצחת את ולנסיה 89-75 בסיבוב הרגיל",
    language: "en",
    publishedAt: "2026-06-09T21:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Fenerbahce", "Valencia Basket"],
    eventType: "match_result",
    importance: "medium",
    confidence: 0.90,
    tags: ["יורוליג", "פנרבצ׳ה", "תוצאה"],
    clusterId: null
  },

  // ============================================================
  // EUROLEAGUE PLAYOFF RESULT
  // ============================================================
  {
    id: "article_012",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/12",
    title: "אולימפיאקוס עולה לחצי גמר יורוליג אחרי ניצחון דרמטי",
    originalTitle: "Olympiacos advances to EuroLeague semis in dramatic fashion",
    translatedTitle: "אולימפיאקוס עולה לחצי גמר יורוליג אחרי ניצחון דרמטי",
    language: "en",
    publishedAt: "2026-06-06T22:30:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Olympiacos"],
    eventType: "playoff_result",
    importance: "high",
    confidence: 0.95,
    tags: ["יורוליג", "פלייאוף", "אולימפיאקוס"],
    clusterId: null
  },

  // ============================================================
  // ISRAELI BASKETBALL - REGULAR RESULT
  // ============================================================
  {
    id: "article_013",
    source: "ynet",
    sourceDisplayName: "ינט ספורט",
    url: "https://www.ynet.co.il/sport/article/13",
    title: "הפועל תל אביב מנצחת את בני הרצליה 88-80 בסיבוב 22",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-08T21:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Hapoel Tel Aviv Basketball", "Bnei Herzliya"],
    eventType: "match_result",
    importance: "medium",
    confidence: 0.88,
    tags: ["כדורסל ישראלי", "הפועל ת״א", "תוצאה"],
    clusterId: null
  },

  // ============================================================
  // ISRAELI BASKETBALL - TITLE WIN
  // ============================================================
  {
    id: "article_014",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=14",
    title: "אלופה! מכבי ת״א זוכה בגביע המדינה לכדורסל",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-05T22:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "title_win",
    importance: "very_high",
    confidence: 0.99,
    tags: ["מכבי ת״א", "אלופה", "גביע"],
    clusterId: null
  },

  // ============================================================
  // NBA - REGULAR SEASON: HORNETS VS WIZARDS
  // Expected: feed for Guy, HIDDEN for Casual Deni Fan
  // ============================================================
  {
    id: "article_015",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/15",
    title: "הורנטס מנצחת את ויזארדס 112-104 בסיבוב הרגיל",
    originalTitle: "Hornets beat Wizards 112-104 in regular season",
    translatedTitle: "הורנטס מנצחת את ויזארדס 112-104 בסיבוב הרגיל",
    language: "en",
    publishedAt: "2026-06-10T03:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Charlotte Hornets", "Washington Wizards"],
    eventType: "regular_season_result",
    importance: "low",
    confidence: 0.95,
    tags: ["NBA", "הורנטס", "ויזארדס", "תוצאה"],
    clusterId: null
  },

  // ============================================================
  // NBA - STAR TRADE
  // Expected: push for Guy, feed for Casual Deni Fan (if no Deni - actually hidden)
  // ============================================================
  {
    id: "article_016",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/16",
    title: "ענקי NBA: לייקרס וסלטיקס בעסקת חליפין ענקית",
    originalTitle: "Lakers and Celtics agree on blockbuster trade deal",
    translatedTitle: "ענקי NBA: לייקרס וסלטיקס בעסקת חליפין ענקית",
    language: "en",
    publishedAt: "2026-06-11T06:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Los Angeles Lakers", "Boston Celtics"],
    eventType: "star_trade",
    importance: "very_high",
    confidence: 0.93,
    tags: ["NBA", "לייקרס", "סלטיקס", "טרייד"],
    clusterId: null
  },

  // ============================================================
  // NBA - DENI AVDIJA TRADE RUMOR
  // Expected: push for BOTH profiles
  // ============================================================
  {
    id: "article_017",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/17",
    title: "דני אבדיה עשוי לעבור בעסקת חליפין לקבוצה מהמזרח",
    originalTitle: "Deni Avdija could be moved in trade to Eastern Conference team",
    translatedTitle: "דני אבדיה עשוי לעבור בעסקת חליפין לקבוצה מהמזרח",
    language: "en",
    publishedAt: "2026-06-11T11:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Deni Avdija", "Portland Trail Blazers"],
    eventType: "major_trade",
    importance: "high",
    confidence: 0.85,
    tags: ["NBA", "דני אבדיה", "טרייד"],
    clusterId: null
  },

  // ============================================================
  // NBA - FINALS RESULT
  // Expected: high_feed for Guy, feed for Casual Deni Fan
  // ============================================================
  {
    id: "article_018",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/18",
    title: "סלטיקס זוכים ב-NBA Finals לאחר ניצחון 106-98 במשחק 7",
    originalTitle: "Celtics win NBA Finals after 106-98 victory in Game 7",
    translatedTitle: "סלטיקס זוכים ב-NBA Finals לאחר ניצחון 106-98 במשחק 7",
    language: "en",
    publishedAt: "2026-06-04T04:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Boston Celtics", "Denver Nuggets"],
    eventType: "finals_result",
    importance: "very_high",
    confidence: 0.99,
    tags: ["NBA", "פיינאלס", "סלטיקס", "אלוף"],
    clusterId: null
  },

  // ============================================================
  // NBA - RECORD BREAKING PERFORMANCE
  // ============================================================
  {
    id: "article_019",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/19",
    title: "היסטוריה: שחקן NBA שובר שיא של 40 שנה עם 73 נקודות במשחק",
    originalTitle: "History: NBA player breaks 40-year record with 73 points in a game",
    translatedTitle: "היסטוריה: שחקן NBA שובר שיא של 40 שנה עם 73 נקודות במשחק",
    language: "en",
    publishedAt: "2026-06-03T04:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Golden State Warriors"],
    eventType: "record",
    importance: "very_high",
    confidence: 0.99,
    tags: ["NBA", "שיא", "היסטוריה"],
    clusterId: null
  },

  // ============================================================
  // NBA - GENERIC PREVIEW (should be low_feed for Guy, hidden for Casual Deni Fan)
  // ============================================================
  {
    id: "article_020",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/20",
    title: "תצפית: 5 המפתחות לניצחון לייקרס מול קינגס הלילה",
    originalTitle: "Preview: 5 keys to Lakers victory over Kings tonight",
    translatedTitle: "תצפית: 5 המפתחות לניצחון לייקרס מול קינגס הלילה",
    language: "en",
    publishedAt: "2026-06-11T14:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Los Angeles Lakers", "Sacramento Kings"],
    eventType: "generic_preview",
    importance: "low",
    confidence: 0.80,
    tags: ["NBA", "תצפית", "לייקרס"],
    clusterId: null
  },

  // ============================================================
  // SPANISH ACB - MAJOR PLAYOFF RESULT
  // ============================================================
  {
    id: "article_021",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/21",
    title: "ברצלונה לגביע ACB: מנצחת את מדריד 85-78 בגמר הספרדי",
    originalTitle: "Barcelona wins ACB title: defeats Madrid 85-78 in Spanish final",
    translatedTitle: "ברצלונה לגביע ACB: מנצחת את מדריד 85-78 בגמר הספרדי",
    language: "en",
    publishedAt: "2026-06-07T21:00:00Z",
    sport: "basketball",
    league: "Spanish ACB",
    entities: ["FC Barcelona Basketball", "Real Madrid Basketball"],
    eventType: "playoff_result",
    importance: "high",
    confidence: 0.95,
    tags: ["ACB", "ברצלונה", "מדריד", "פלייאוף"],
    clusterId: null
  },

  // ============================================================
  // SPANISH ACB - GENERIC REGULAR SEASON RESULT (hidden for Guy)
  // ============================================================
  {
    id: "article_022",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/22",
    title: "לא מרגש: ואלנסיה מנצחת את ביתה 79-71 בסיבוב 18",
    originalTitle: "Valencia beats Betis 79-71 in ACB round 18",
    translatedTitle: "ואלנסיה מנצחת את ביתה 79-71 בסיבוב 18",
    language: "en",
    publishedAt: "2026-06-09T20:00:00Z",
    sport: "basketball",
    league: "Spanish ACB",
    entities: ["Valencia Basket"],
    eventType: "regular_season_result",
    importance: "low",
    confidence: 0.85,
    tags: ["ACB", "ספרד", "תוצאה"],
    clusterId: null
  },

  // ============================================================
  // TURKISH BSL - TITLE WIN
  // ============================================================
  {
    id: "article_023",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/23",
    title: "אפס אסטנבול: אלוף טורקיה לאחר ניצחון 91-87 על פנרבצ׳ה",
    originalTitle: "Anadolu Efes: Turkish champion after 91-87 win over Fenerbahce",
    translatedTitle: "אפס אסטנבול: אלוף טורקיה לאחר ניצחון 91-87 על פנרבצ׳ה",
    language: "en",
    publishedAt: "2026-06-06T21:00:00Z",
    sport: "basketball",
    league: "Turkish BSL",
    entities: ["Anadolu Efes"],
    eventType: "title_win",
    importance: "high",
    confidence: 0.98,
    tags: ["BSL", "טורקיה", "אפס", "אלוף"],
    clusterId: null
  },

  // ============================================================
  // GREEK LEAGUE - MAJOR DERBY RESULT
  // ============================================================
  {
    id: "article_024",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/24",
    title: "דרבי יוון: אולימפיאקוס מנצחת את פנתינאיקוס 98-87 במשחק מטורף",
    originalTitle: "Greek Derby: Olympiacos beats Panathinaikos 98-87 in a wild game",
    translatedTitle: "דרבי יוון: אולימפיאקוס מנצחת את פנתינאיקוס 98-87 במשחק מטורף",
    language: "en",
    publishedAt: "2026-06-08T20:00:00Z",
    sport: "basketball",
    league: "Greek Basket League",
    entities: ["Olympiacos", "Panathinaikos"],
    eventType: "major_match_result",
    importance: "high",
    confidence: 0.90,
    tags: ["יוון", "דרבי", "אולימפיאקוס", "פנתינאיקוס"],
    clusterId: null
  },

  // ============================================================
  // ITALIAN LBA - GENERIC PREVIEW (hidden for Guy)
  // ============================================================
  {
    id: "article_025",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/25",
    title: "תצפית: מילאנו מול בולוניה - מי ינצח את הסיבוב הבא?",
    originalTitle: "Preview: Milano vs Bologna - who wins the next round?",
    translatedTitle: "תצפית: מילאנו מול בולוניה - מי ינצח את הסיבוב הבא?",
    language: "en",
    publishedAt: "2026-06-11T12:00:00Z",
    sport: "basketball",
    league: "Italian LBA",
    entities: ["Olimpia Milano"],
    eventType: "generic_preview",
    importance: "low",
    confidence: 0.80,
    tags: ["LBA", "איטליה", "מילאנו", "תצפית"],
    clusterId: null
  },

  // ============================================================
  // FRENCH LNB - MAJOR SIGNING
  // ============================================================
  {
    id: "article_026",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/26",
    title: "LDLC ASVEL חותמת על כוכב יורוליג לעונה הבאה",
    originalTitle: "LDLC ASVEL signs EuroLeague star for next season",
    translatedTitle: "LDLC ASVEL חותמת על כוכב יורוליג לעונה הבאה",
    language: "en",
    publishedAt: "2026-06-10T10:00:00Z",
    sport: "basketball",
    league: "French LNB",
    entities: ["LDLC ASVEL"],
    eventType: "major_signing",
    importance: "high",
    confidence: 0.85,
    tags: ["LNB", "צרפת", "ASVEL", "חתימה"],
    clusterId: null
  },

  // ============================================================
  // TENNIS - ALCARAZ WINS GRAND SLAM (high_feed for Guy)
  // ============================================================
  {
    id: "article_027",
    source: "ynet",
    sourceDisplayName: "ינט ספורט",
    url: "https://www.ynet.co.il/sport/article/27",
    title: "אלקראז זוכה בגראנד סלאם השלישי שלו בקריירה - ניצחון מדהים",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-09T17:00:00Z",
    sport: "tennis",
    league: "Grand Slam",
    entities: ["Carlos Alcaraz"],
    eventType: "grand_slam_winner",
    importance: "very_high",
    confidence: 0.99,
    tags: ["טניס", "אלקראז", "גראנד סלאם"],
    clusterId: null
  },

  // ============================================================
  // TENNIS - ALCARAZ EARLY ROUND (hidden for Guy)
  // ============================================================
  {
    id: "article_028",
    source: "ynet",
    sourceDisplayName: "ינט ספורט",
    url: "https://www.ynet.co.il/sport/article/28",
    title: "אלקראז מנצח בסיבוב הראשון בוימבלדון 3-0 בסטים",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-08T15:00:00Z",
    sport: "tennis",
    league: "Wimbledon",
    entities: ["Carlos Alcaraz"],
    eventType: "early_round_result",
    importance: "low",
    confidence: 0.92,
    tags: ["טניס", "אלקראז", "וימבלדון"],
    clusterId: null
  },

  // ============================================================
  // TENNIS - GENERIC ARTICLE (hidden for Guy)
  // ============================================================
  {
    id: "article_029",
    source: "ynet",
    sourceDisplayName: "ינט ספורט",
    url: "https://www.ynet.co.il/sport/article/29",
    title: "סקירה שבועית: מה מחכה לטניס העולמי בחודשים הקרובים",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-07T10:00:00Z",
    sport: "tennis",
    league: null,
    entities: [],
    eventType: "generic_news",
    importance: "low",
    confidence: 0.70,
    tags: ["טניס", "סקירה"],
    clusterId: null
  },

  // ============================================================
  // FOOTBALL - ISRAELI MINOR RESULT (low_feed or hidden for Guy)
  // ============================================================
  {
    id: "article_030",
    source: "one",
    sourceDisplayName: "ONE",
    url: "https://www.one.co.il/Article/30",
    title: "הפועל פתח תקווה ניצחת את מ.ס. אשדוד 2-1",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-10T20:00:00Z",
    sport: "football",
    league: "Israeli Premier League",
    entities: ["Hapoel Petah Tikva", "MS Ashdod"],
    eventType: "regular_season_result",
    importance: "low",
    confidence: 0.90,
    tags: ["כדורגל", "ליגת על", "תוצאה"],
    clusterId: null
  },

  // ============================================================
  // FOOTBALL - MACCABI TLV FOOTBALL IMPORTANT MATCH
  // ============================================================
  {
    id: "article_031",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=31",
    title: "מכבי ת״א כדורגל מכשירה ריגול עם ריאל מדריד בגביע אירופה",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-09T19:00:00Z",
    sport: "football",
    league: "UEFA Conference League",
    entities: ["Maccabi Tel Aviv FC"],
    eventType: "major_match_result",
    importance: "high",
    confidence: 0.90,
    tags: ["כדורגל", "מכבי ת״א", "אירופה"],
    clusterId: null
  },

  // ============================================================
  // FOOTBALL - BUNDESLIGA: BAYERN VS DORTMUND (regular result - lower for Guy)
  // ============================================================
  {
    id: "article_032",
    source: "walla",
    sourceDisplayName: "וואלה ספורט",
    url: "https://sport.walla.co.il/article/32",
    title: "ביכנה: ביירן מינכן מנצחת את דורטמונד 3-1 בדרבי גרמני",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-08T18:00:00Z",
    sport: "football",
    league: "Bundesliga",
    entities: ["Bayern Munich", "Borussia Dortmund"],
    eventType: "major_match_result",
    importance: "high",
    confidence: 0.92,
    tags: ["כדורגל", "בונדסליגה", "ביירן", "דורטמונד"],
    clusterId: null
  },

  // ============================================================
  // FOOTBALL - MBAPPE TRANSFER NEWS
  // ============================================================
  {
    id: "article_033",
    source: "walla",
    sourceDisplayName: "וואלה ספורט",
    url: "https://sport.walla.co.il/article/33",
    title: "אמבפה עשוי לחזור לPSG - מגעים ראשונים לפי דיווח",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T09:00:00Z",
    sport: "football",
    league: "Ligue 1",
    entities: ["Kylian Mbappe", "Paris Saint-Germain"],
    eventType: "major_transfer",
    importance: "high",
    confidence: 0.80,
    tags: ["כדורגל", "אמבפה", "PSG", "טרנספר"],
    clusterId: null
  },

  // ============================================================
  // YNET OPINION COLUMN
  // ============================================================
  {
    id: "article_034",
    source: "ynet",
    sourceDisplayName: "ינט ספורט",
    url: "https://www.ynet.co.il/sport/article/34",
    title: "דעה: הכדורסל הישראלי על פרשת דרכים - מה הטעות הגדולה?",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-10T08:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: [],
    eventType: "opinion",
    importance: "medium",
    confidence: 0.75,
    tags: ["כדורסל ישראלי", "דעה", "ניתוח"],
    clusterId: null
  },

  // ============================================================
  // WALLA - MATCH SUMMARY
  // ============================================================
  {
    id: "article_035",
    source: "walla",
    sourceDisplayName: "וואלה ספורט",
    url: "https://sport.walla.co.il/article/35",
    title: "סיכום: מכבי חיפה - הפועל באר שבע 2-2, דרמה בדקה האחרונה",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-07T22:30:00Z",
    sport: "football",
    league: "Israeli Premier League",
    entities: ["Maccabi Haifa", "Hapoel Beer Sheva"],
    eventType: "match_summary",
    importance: "medium",
    confidence: 0.88,
    tags: ["כדורגל", "מכבי חיפה", "הפועל ב״ש"],
    clusterId: null
  },

  // ============================================================
  // ONE - INJURY REPORT
  // ============================================================
  {
    id: "article_036",
    source: "one",
    sourceDisplayName: "ONE",
    url: "https://www.one.co.il/Article/36",
    title: "חדשות לא טובות: כוכב NBA ייעדר 6 שבועות בגלל פציעת ברך",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T07:30:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Milwaukee Bucks"],
    eventType: "injury",
    importance: "high",
    confidence: 0.90,
    tags: ["NBA", "פציעה"],
    clusterId: null
  },

  // ============================================================
  // SPORT5 - NEGOTIATION REPORT
  // ============================================================
  {
    id: "article_037",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=37",
    title: "ספורט 5: מכבי ת״א מסיימת מו״מ עם קנטר נוסף מיורוליג",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T11:30:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "negotiation",
    importance: "high",
    confidence: 0.88,
    tags: ["מכבי ת״א", "מו״מ", "יורוליג", "רכש"],
    clusterId: null
  },

  // ============================================================
  // ISRAEL HAYOM - ANALYSIS ARTICLE
  // ============================================================
  {
    id: "article_038",
    source: "israel_hayom",
    sourceDisplayName: "ישראל היום ספורט",
    url: "https://www.israelhayom.co.il/sport/article/38",
    title: "ניתוח: למה מכבי ת״א הם המועמד הראשי לאליפות הליגה הישראלית",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-09T12:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "analysis",
    importance: "medium",
    confidence: 0.82,
    tags: ["מכבי ת״א", "ניתוח", "כדורסל ישראלי"],
    clusterId: null
  },

  // ============================================================
  // EUROHOOPS - ENGLISH REPORT ABOUT MACCABI
  // ============================================================
  {
    id: "article_039",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/39",
    title: "מכבי ת״א בונה כוח לעונת יורוליג: שלושה רכישות כבר בקיץ",
    originalTitle: "Maccabi Tel Aviv building EuroLeague squad: three signings already this summer",
    translatedTitle: "מכבי ת״א בונה כוח לעונת יורוליג: שלושה רכישות כבר בקיץ",
    language: "en",
    publishedAt: "2026-06-10T14:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "analysis",
    importance: "medium",
    confidence: 0.88,
    tags: ["מכבי ת״א", "יורוליג", "רכש", "ניתוח"],
    clusterId: null
  },

  // ============================================================
  // GENERIC PRE-MATCH ARTICLE (should be hidden for everyone)
  // ============================================================
  {
    id: "article_040",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=40",
    title: "השידור הערב: מכבי ת״א מול הפועל ת״א - ערוץ 10, 20:00",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T15:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball", "Hapoel Tel Aviv Basketball"],
    eventType: "schedule",
    importance: "very_low",
    confidence: 0.95,
    tags: ["מכבי ת״א", "שידור", "לו״ז"],
    clusterId: null
  },

  // ============================================================
  // EXTRA: DENI AVDIJA GAME PERFORMANCE
  // Expected: high_feed for both profiles
  // ============================================================
  {
    id: "article_041",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/41",
    title: "דני אבדיה עם 34 נקודות ו-12 ריבאונד בניצחון הבלייזרס",
    originalTitle: "Deni Avdija drops 34 points and 12 rebounds in Blazers win",
    translatedTitle: "דני אבדיה עם 34 נקודות ו-12 ריבאונד בניצחון הבלייזרס",
    language: "en",
    publishedAt: "2026-06-11T05:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Deni Avdija", "Portland Trail Blazers"],
    eventType: "regular_season_result",
    importance: "high",
    confidence: 0.95,
    tags: ["NBA", "דני אבדיה", "בלייזרס"],
    clusterId: null
  },

  // ============================================================
  // NBA — BROAD-INTEREST (NO DENI)
  // article_042: Guy→feed, Casual Deni Fan→hidden
  // ============================================================
  {
    id: "article_042",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/42",
    title: "גולדן סטייט ווריירס מנצחת את מילווקי באקס 118-112 בסיבוב הרגיל",
    originalTitle: "Golden State Warriors defeat Milwaukee Bucks 118-112 in regular season",
    translatedTitle: "גולדן סטייט ווריירס מנצחת את מילווקי באקס 118-112 בסיבוב הרגיל",
    language: "en",
    publishedAt: "2026-06-10T03:30:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Golden State Warriors", "Milwaukee Bucks"],
    eventType: "regular_season_result",
    importance: "medium",
    confidence: 0.95,
    tags: ["NBA", "גולדן סטייט", "מילווקי", "תוצאה"],
    clusterId: null
  },

  // article_043: NBA superstar injury (non-Deni)
  // Guy→feed, Casual Deni Fan→hidden
  {
    id: "article_043",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/43",
    title: "מכה ל-NBA: כוכב מילווקי באקס ייעדר חצי עונה לאחר פציעת ברך",
    originalTitle: "Blow to NBA: Milwaukee Bucks star out for half a season with knee injury",
    translatedTitle: "מכה ל-NBA: כוכב מילווקי באקס ייעדר חצי עונה לאחר פציעת ברך",
    language: "en",
    publishedAt: "2026-06-09T08:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Milwaukee Bucks"],
    eventType: "injury",
    importance: "high",
    confidence: 0.92,
    tags: ["NBA", "מילווקי", "פציעה", "כוכב"],
    clusterId: null
  },

  // article_044: NBA playoff (non-Deni teams)
  // Guy→high_feed, Casual Deni Fan→hidden
  {
    id: "article_044",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/44",
    title: "סלטיקס עולות לגמר NBA לאחר ניצחון 4-2 בסדרה על מיאמי היט",
    originalTitle: "Celtics advance to NBA Finals after 4-2 series win over Miami Heat",
    translatedTitle: "סלטיקס עולות לגמר NBA לאחר ניצחון 4-2 בסדרה על מיאמי היט",
    language: "en",
    publishedAt: "2026-06-06T04:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Boston Celtics", "Miami Heat"],
    eventType: "playoff_result",
    importance: "high",
    confidence: 0.99,
    tags: ["NBA", "פלייאוף", "סלטיקס", "מיאמי"],
    clusterId: null
  },

  // article_045: NBA mid-level signing (non-star)
  // Guy→feed, Casual Deni Fan→hidden
  {
    id: "article_045",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/45",
    title: "מיאמי היט חותמת על גארד חינם בן 27 לחיזוק הסגל לעונה הבאה",
    originalTitle: "Miami Heat sign 27-year-old free agent guard to bolster next season roster",
    translatedTitle: "מיאמי היט חותמת על גארד חינם בן 27 לחיזוק הסגל לעונה הבאה",
    language: "en",
    publishedAt: "2026-06-09T10:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Miami Heat"],
    eventType: "signing",
    importance: "low",
    confidence: 0.88,
    tags: ["NBA", "מיאמי", "חתימה", "חינמי"],
    clusterId: null
  },

  // ============================================================
  // NBA — DENI-SPECIFIC
  // article_046: Deni serious injury
  // Guy→push (entity-specific rule, injury is push-eligible), Casual Deni Fan→push
  // ============================================================
  {
    id: "article_046",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/46",
    title: "פציעה: דני אבדיה ייעדר שישה שבועות לאחר ניתוח בקרסול",
    originalTitle: "Injury: Deni Avdija to miss six weeks following ankle surgery",
    translatedTitle: "פציעה: דני אבדיה ייעדר שישה שבועות לאחר ניתוח בקרסול",
    language: "en",
    publishedAt: "2026-06-10T06:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Deni Avdija", "Portland Trail Blazers"],
    eventType: "injury",
    importance: "high",
    confidence: 0.96,
    tags: ["NBA", "דני אבדיה", "פציעה", "ניתוח"],
    clusterId: null
  },

  // article_047: Deni career-high performance
  // Guy→high_feed (entity boost), Casual Deni Fan→feed
  {
    id: "article_047",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/47",
    title: "דני אבדיה עם 35 נקודות ו-11 ריבאונד: הופעת קריירה עבור הישראלי",
    originalTitle: "Deni Avdija drops career-high 35 points and 11 rebounds in Blazers win",
    translatedTitle: "דני אבדיה עם 35 נקודות ו-11 ריבאונד: הופעת קריירה עבור הישראלי",
    language: "en",
    publishedAt: "2026-06-09T05:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Deni Avdija", "Portland Trail Blazers"],
    eventType: "regular_season_result",
    importance: "high",
    confidence: 0.97,
    tags: ["NBA", "דני אבדיה", "שיא אישי", "בלייזרס"],
    clusterId: null
  },

  // ============================================================
  // NBA — NON-DENI MAJOR TRADE
  // Guy→high_feed, Casual Deni Fan→hidden
  // ============================================================
  {
    id: "article_048",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/48",
    title: "מהלך NBA: מיאמי היט ומינסוטה מחליפות שחקן מרכזי בעסקת שלושה שחקנים",
    originalTitle: "NBA move: Miami Heat and Minnesota Timberwolves exchange key player in three-man deal",
    translatedTitle: "מהלך NBA: מיאמי היט ומינסוטה מחליפות שחקן מרכזי בעסקת שלושה שחקנים",
    language: "en",
    publishedAt: "2026-06-08T12:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Miami Heat", "Minnesota Timberwolves"],
    eventType: "major_trade",
    importance: "medium",
    confidence: 0.82,
    tags: ["NBA", "מיאמי", "מינסוטה", "עסקה"],
    clusterId: null
  },

  // ============================================================
  // NOISE ARTICLES — hidden for Guy and Casual Deni Fan
  // article_049: NBA schedule listing
  // ============================================================
  {
    id: "article_049",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/49",
    title: "לו״ז NBA הלילה: שמונה משחקים בסיבוב 78 — מדריך הצפייה",
    originalTitle: "NBA tonight: eight games in round 78 — viewing guide",
    translatedTitle: "לו״ז NBA הלילה: שמונה משחקים בסיבוב 78 — מדריך הצפייה",
    language: "en",
    publishedAt: "2026-06-11T16:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: [],
    eventType: "schedule",
    importance: "very_low",
    confidence: 0.90,
    tags: ["NBA", "לוח משחקים", "שידור"],
    clusterId: null
  },

  // article_050: NBA pre-match lineup (hidden via importanceFallback very_low)
  {
    id: "article_050",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/50",
    title: "לפני המשחק: ההרכב הראשי הצפוי של פניקס סאנז מול שארלוט הורנטס",
    originalTitle: "Preview: Expected starting lineup of Phoenix Suns vs Charlotte Hornets",
    translatedTitle: "לפני המשחק: ההרכב הראשי הצפוי של פניקס סאנז מול שארלוט הורנטס",
    language: "en",
    publishedAt: "2026-06-11T17:00:00Z",
    sport: "basketball",
    league: "NBA",
    entities: ["Phoenix Suns", "Charlotte Hornets"],
    eventType: "pre_match",
    importance: "very_low",
    confidence: 0.88,
    tags: ["NBA", "הרכב", "סאנז", "הורנטס"],
    clusterId: null
  },

  // article_051: Football schedule listing
  {
    id: "article_051",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=51",
    title: "לו״ז המשחקים: כל מפגשי UEFA Champions League השבוע — ערוצים ושעות",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T10:00:00Z",
    sport: "football",
    league: "Champions League",
    entities: [],
    eventType: "schedule",
    importance: "very_low",
    confidence: 0.95,
    tags: ["כדורגל", "צ׳מפיונס ליג", "לוח משחקים", "שידור"],
    clusterId: null
  },

  // ============================================================
  // EUROLEAGUE — REGULAR AND MAJOR CONTENT
  // article_052: Regular season result (non-Maccabi) — Guy→feed
  // ============================================================
  {
    id: "article_052",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/52",
    title: "יורוליג סיבוב 28: ריאל מדריד מנצחת את ברצלונה 87-82 בנסיעה",
    originalTitle: "EuroLeague round 28: Real Madrid defeats Barcelona 87-82 on the road",
    translatedTitle: "יורוליג סיבוב 28: ריאל מדריד מנצחת את ברצלונה 87-82 בנסיעה",
    language: "en",
    publishedAt: "2026-06-08T22:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Real Madrid Basketball", "FC Barcelona Basketball"],
    eventType: "match_result",
    importance: "medium",
    confidence: 0.92,
    tags: ["יורוליג", "ריאל מדריד", "ברצלונה", "תוצאה"],
    clusterId: null
  },

  // article_053: EuroLeague player interview — Guy→feed
  {
    id: "article_053",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/53",
    title: "ראיון: כוכב פנרבצ׳ה על עתיד קריירתו ועונת EuroLeague הבאה",
    originalTitle: "Interview: Fenerbahce star on his career future and the next EuroLeague season",
    translatedTitle: "ראיון: כוכב פנרבצ׳ה על עתיד קריירתו ועונת EuroLeague הבאה",
    language: "en",
    publishedAt: "2026-06-07T14:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Fenerbahce"],
    eventType: "interview",
    importance: "medium",
    confidence: 0.85,
    tags: ["יורוליג", "פנרבצ׳ה", "ראיון", "כוכב"],
    clusterId: null
  },

  // article_054: EuroLeague Final Four — Guy→high_feed
  {
    id: "article_054",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/54",
    title: "היסטוריה! פנרבצ׳ה עולה לגמר Final Four יורוליג בניצחון 92-87 על CSKA",
    originalTitle: "Historic! Fenerbahce reaches EuroLeague Final Four final with 92-87 win over CSKA",
    translatedTitle: "היסטוריה! פנרבצ׳ה עולה לגמר Final Four יורוליג בניצחון 92-87 על CSKA",
    language: "en",
    publishedAt: "2026-06-05T21:30:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Fenerbahce", "CSKA Moscow"],
    eventType: "final_four",
    importance: "very_high",
    confidence: 0.99,
    tags: ["יורוליג", "Final Four", "פנרבצ׳ה", "CSKA"],
    clusterId: null
  },

  // article_055: EuroLeague major injury — Guy→feed
  {
    id: "article_055",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/55",
    title: "מכה ל-EuroLeague: כוכב אולימפיאקוס ייעדר עד סוף העונה לאחר ניתוח",
    originalTitle: "EuroLeague blow: Olympiacos star out for remainder of season after surgery",
    translatedTitle: "מכה ל-EuroLeague: כוכב אולימפיאקוס ייעדר עד סוף העונה לאחר ניתוח",
    language: "en",
    publishedAt: "2026-06-06T10:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Olympiacos"],
    eventType: "injury",
    importance: "high",
    confidence: 0.93,
    tags: ["יורוליג", "אולימפיאקוס", "פציעה", "ניתוח"],
    clusterId: null
  },

  // ============================================================
  // MACCABI — HIGH PRIORITY
  // article_056: Official signing — Guy→PUSH
  // ============================================================
  {
    id: "article_056",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=56",
    title: "רשמי: מכבי ת״א חתמה על חיזוק שני לעונת יורוליג — שחקן מהליגה הספרדית",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T13:00:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "signing",
    importance: "high",
    confidence: 0.97,
    tags: ["מכבי ת״א", "חתימה", "רכש", "יורוליג"],
    clusterId: null
  },

  // article_057: Maccabi playoff win — Guy→high_feed
  {
    id: "article_057",
    source: "one",
    sourceDisplayName: "ONE",
    url: "https://www.one.co.il/Article/57",
    title: "מכבי ת״א מסיימת 3-0 בחצי גמר הליגה הישראלית ועולה לגמר",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-04T21:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "playoff_result",
    importance: "high",
    confidence: 0.98,
    tags: ["מכבי ת״א", "פלייאוף", "חצי גמר", "ליגה ישראלית"],
    clusterId: null
  },

  // ============================================================
  // MACCABI — LOW-VALUE CONTENT (hidden for everyone)
  // article_058: Broadcast schedule — Guy→hidden
  // ============================================================
  {
    id: "article_058",
    source: "sport5",
    sourceDisplayName: "ספורט 5",
    url: "https://www.sport5.co.il/articles.aspx?FolderID=1&docID=58",
    title: "השידור מחר: מכבי ת״א מול מנורה מיקס — ספורט 5 בשעה 20:30",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-11T18:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "schedule",
    importance: "very_low",
    confidence: 0.95,
    tags: ["מכבי ת״א", "שידור", "לו״ז"],
    clusterId: null
  },

  // article_059: Maccabi pre-match lineup — Guy→hidden
  {
    id: "article_059",
    source: "walla",
    sourceDisplayName: "וואלה ספורט",
    url: "https://sport.walla.co.il/article/59",
    title: "לפני הדרבי: ההרכב הצפוי של מכבי ת״א מול הפועל ת״א הערב",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-10T09:00:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Maccabi Tel Aviv Basketball", "Hapoel Tel Aviv Basketball"],
    eventType: "pre_match",
    importance: "very_low",
    confidence: 0.90,
    tags: ["מכבי ת״א", "הרכב", "הפועל ת״א", "לפני המשחק"],
    clusterId: null
  },

  // ============================================================
  // ISRAELI BASKETBALL — REGULAR AND PLAYOFF
  // article_060: Playoff (non-Maccabi) — Guy→high_feed
  // ============================================================
  {
    id: "article_060",
    source: "ynet",
    sourceDisplayName: "ינט ספורט",
    url: "https://www.ynet.co.il/sport/article/60",
    title: "הפועל ירושלים עולה לגמר הליגה הישראלית עם ניצחון 3-1 בחצי גמר",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-07T21:30:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Hapoel Jerusalem Basketball"],
    eventType: "playoff_result",
    importance: "high",
    confidence: 0.96,
    tags: ["כדורסל ישראלי", "הפועל ירושלים", "פלייאוף", "גמר"],
    clusterId: null
  },

  // article_061: Israeli basketball regular season (small match) — Guy→feed
  {
    id: "article_061",
    source: "ynet",
    sourceDisplayName: "ינט ספורט",
    url: "https://www.ynet.co.il/sport/article/61",
    title: "בני אילת מנצחת את הפועל חולון 91-88 בסיבוב 23 של הליגה הישראלית",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-09T21:30:00Z",
    sport: "basketball",
    league: "Israeli Basketball League",
    entities: ["Bnei Eilat", "Hapoel Holon"],
    eventType: "regular_season_result",
    importance: "medium",
    confidence: 0.88,
    tags: ["כדורסל ישראלי", "בני אילת", "חולון", "תוצאה"],
    clusterId: null
  },

  // ============================================================
  // EUROPEAN DOMESTIC BASKETBALL — MAJOR GAMES
  // article_062: ACB title win — Guy→high_feed
  // ============================================================
  {
    id: "article_062",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/62",
    title: "ריאל מדריד כדורסל: אלוף ספרד ACB לאחר ניצחון 94-87 בגמר",
    originalTitle: "Real Madrid Basketball: ACB Spanish champions after 94-87 final victory",
    translatedTitle: "ריאל מדריד כדורסל: אלוף ספרד ACB לאחר ניצחון 94-87 בגמר",
    language: "en",
    publishedAt: "2026-06-06T22:00:00Z",
    sport: "basketball",
    league: "Spanish ACB",
    entities: ["Real Madrid Basketball"],
    eventType: "title_win",
    importance: "high",
    confidence: 0.98,
    tags: ["ACB", "ספרד", "ריאל מדריד", "אלוף"],
    clusterId: null
  },

  // article_063: Turkish BSL derby — Guy→feed
  {
    id: "article_063",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/63",
    title: "דרבי איסטנבול ב-BSL: פנרבצ׳ה מנצחת את אנדולו אפס 94-91 בנסיעה",
    originalTitle: "Istanbul derby in BSL: Fenerbahce defeats Anadolu Efes 94-91 on the road",
    translatedTitle: "דרבי איסטנבול ב-BSL: פנרבצ׳ה מנצחת את אנדולו אפס 94-91 בנסיעה",
    language: "en",
    publishedAt: "2026-06-08T19:00:00Z",
    sport: "basketball",
    league: "Turkish BSL",
    entities: ["Fenerbahce", "Anadolu Efes"],
    eventType: "major_match_result",
    importance: "high",
    confidence: 0.90,
    tags: ["BSL", "טורקיה", "דרבי", "פנרבצ׳ה", "אפס"],
    clusterId: null
  },

  // ============================================================
  // EUROPEAN DOMESTIC BASKETBALL — LOW-VALUE NOISE
  // article_064: LNB generic preview — Guy→low_feed (NBA topic rule), noise
  // ============================================================
  {
    id: "article_064",
    source: "sportando",
    sourceDisplayName: "Sportando",
    url: "https://sportando.basketball/article/64",
    title: "תצפית LNB: לה מאן מול מונפלייה בסיבוב 26 של הליגה הצרפתית",
    originalTitle: "LNB preview: Le Mans vs Montpellier in round 26 of the French league",
    translatedTitle: "תצפית LNB: לה מאן מול מונפלייה בסיבוב 26 של הליגה הצרפתית",
    language: "en",
    publishedAt: "2026-06-11T11:00:00Z",
    sport: "basketball",
    league: "French LNB",
    entities: ["Le Mans Sarthe Basket", "Montpellier Herault Basket"],
    eventType: "generic_preview",
    importance: "low",
    confidence: 0.80,
    tags: ["LNB", "צרפת", "לה מאן", "מונפלייה", "תצפית"],
    clusterId: null
  },

  // article_065: Greek league schedule broadcast — Guy→hidden
  {
    id: "article_065",
    source: "eurohoops",
    sourceDisplayName: "Eurohoops",
    url: "https://www.eurohoops.net/article/65",
    title: "לו״ז ליגה יוונית: כל משחקי סיבוב 25 ושידורים זמינים",
    originalTitle: "Greek basketball league schedule: all round 25 fixtures and available broadcasts",
    translatedTitle: "לו״ז ליגה יוונית: כל משחקי סיבוב 25 ושידורים זמינים",
    language: "en",
    publishedAt: "2026-06-09T09:00:00Z",
    sport: "basketball",
    league: "Greek Basket League",
    entities: [],
    eventType: "schedule",
    importance: "very_low",
    confidence: 0.90,
    tags: ["ליגה יוונית", "לוח משחקים", "שידור"],
    clusterId: null
  },

  // ============================================================
  // TENNIS — GRAND SLAM FINAL
  // article_066: Guy→feed, Casual Deni Fan→hidden
  // ============================================================
  {
    id: "article_066",
    source: "ynet",
    sourceDisplayName: "ינט ספורט",
    url: "https://www.ynet.co.il/sport/article/66",
    title: "ויימבלדון: אלקראז מגיע לגמר לאחר ניצחון מרהיב בחמישה סטים בחצי גמר",
    originalTitle: null,
    translatedTitle: null,
    language: "he",
    publishedAt: "2026-06-07T16:00:00Z",
    sport: "tennis",
    league: "Wimbledon",
    entities: ["Carlos Alcaraz"],
    eventType: "grand_slam_final",
    importance: "high",
    confidence: 0.99,
    tags: ["טניס", "ויימבלדון", "אלקראז", "גמר", "חצי גמר"],
    clusterId: null
  }
];

// ============================================================
// STORY CLUSTERS
// ============================================================
export const mockClusters = [
  {
    id: "cluster_maccabi_negotiation_001",
    clusterTitle: "מכבי ת״א במו״מ עם גארד יורוליג",
    primaryArticleId: "article_001",
    articleIds: ["article_001", "article_002", "article_003"],
    sources: ["sport5", "one", "sportando"],
    sourceDisplayNames: ["ספורט 5", "ONE", "Sportando"],
    entities: ["Maccabi Tel Aviv Basketball"],
    eventType: "negotiation",
    sport: "basketball",
    league: "EuroLeague",
    tags: ["מכבי ת״א", "יורוליג", "רכש", "מו״מ"],
    importance: "high",
    firstSeenAt: "2026-06-11T08:00:00Z",
    lastUpdatedAt: "2026-06-11T09:00:00Z",
    decision: null // will be computed by scoring engine
  }
];