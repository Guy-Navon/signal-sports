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