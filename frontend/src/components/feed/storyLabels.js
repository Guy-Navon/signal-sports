// Hebrew display labels for the edition's "kicker" system — the one quiet line
// that says what a story *is* (entity · event type) instead of a pile of chips.
// UI-layer only: raw engine/API values are never modified. Unknown values fall
// back gracefully (entity → league → sport; unknown event types are omitted).

export const SPORT_HE = {
  basketball: "כדורסל",
  football: "כדורגל",
  tennis: "טניס",
};

export const LEAGUE_HE = {
  EuroLeague: "יורוליג",
  EuroCup: "יורוקאפ",
  NBA: "NBA",
  "Israeli Basketball League": "ליגת ווינר סל",
  "Israeli Premier League": "ליגת העל",
  "Spanish ACB": "הליגה הספרדית",
  "Turkish BSL": "הליגה הטורקית",
  "Greek Basket League": "הליגה היוונית",
  "Italian LBA": "הליגה האיטלקית",
  "French LNB": "הליגה הצרפתית",
  "Grand Slam": "גראנד סלאם",
  Wimbledon: "ווימבלדון",
  "Champions League": "ליגת האלופות",
  Bundesliga: "בונדסליגה",
  "Ligue 1": "ליגה 1",
  "UEFA Conference League": "קונפרנס ליג",
};

export const ENTITY_HE = {
  "Maccabi Tel Aviv Basketball": "מכבי ת״א",
  "Hapoel Tel Aviv Basketball": "הפועל ת״א",
  "Hapoel Jerusalem Basketball": "הפועל ירושלים",
  "Bnei Herzliya": "בני הרצליה",
  "Deni Avdija": "דני אבדיה",
  "Oded Kattash": "עודד קטש",
  "Portland Trail Blazers": "פורטלנד",
  "Charlotte Hornets": "שארלוט",
  "Washington Wizards": "וושינגטון",
  "Boston Celtics": "בוסטון סלטיקס",
  "Miami Heat": "מיאמי היט",
  "Milwaukee Bucks": "מילווקי באקס",
  "Denver Nuggets": "דנבר נאגטס",
  "New York Knicks": "ניו יורק ניקס",
  "Real Madrid Basketball": "ריאל מדריד",
  "FC Barcelona Basketball": "ברצלונה",
  "Anadolu Efes": "אנאדולו אפס",
  Fenerbahce: "פנרבחצ׳ה",
  Panathinaikos: "פנאתינייקוס",
  Olympiacos: "אולימפיאקוס",
  "CSKA Moscow": "צסק״א מוסקבה",
  "Carlos Alcaraz": "קרלוס אלקראס",
  "Kylian Mbappe": "קיליאן אמבפה",
  "Real Madrid": "ריאל מדריד",
};

// Filler event types (generic news/previews/schedules) are omitted from the
// kicker on purpose — a kicker that says "חדשות" adds noise, not signal.
export const EVENT_TYPE_HE = {
  signing: "חתימה",
  major_signing: "חתימה בכירה",
  negotiation: "מו״מ",
  candidate: "מועמדות",
  rumor: "שמועה",
  injury: "פציעה",
  trade: "טרייד",
  major_trade: "טרייד גדול",
  star_trade: "טרייד כוכב",
  major_transfer: "העברת ענק",
  match_result: "תוצאה",
  major_match_result: "משחק גדול",
  match_summary: "סיכום משחק",
  regular_season_result: "עונה סדירה",
  playoff_result: "פלייאוף",
  finals_result: "גמר",
  final_four: "פיינל פור",
  title_win: "זכייה בתואר",
  record: "שיא",
  interview: "ריאיון",
  analysis: "ניתוח",
  opinion: "טור דעה",
  pre_match: "לקראת המשחק",
  friendly_match: "משחק ידידות",
  grand_slam_final: "גמר גראנד סלאם",
  grand_slam_winner: "זכייה בגראנד סלאם",
  early_round_result: "סיבוב מוקדם",
};

export function entityLabel(name) {
  return ENTITY_HE[name] || name;
}

/**
 * Compose the kicker line for a story: "מכבי ת״א · מו״מ".
 * Subject part: first *mapped* entity → league → sport (an unmapped English
 * entity name is skipped rather than shown raw in the Hebrew UI).
 * Event part: mapped event type, omitted for filler types.
 * Returns null when nothing meaningful can be said.
 */
export function buildKicker(item) {
  const mappedEntity = (item.entities || []).map((e) => ENTITY_HE[e]).find(Boolean);
  const subject = mappedEntity || LEAGUE_HE[item.league] || SPORT_HE[item.sport] || null;
  const event = EVENT_TYPE_HE[item.eventType] || null;
  const parts = [subject, event].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

/**
 * Distil the engine's reasoning chain into the "why you're seeing this" line.
 * Prefers the quoted topic label the engine emits (נושא: "..."), falling back
 * to the most specific non-final reasoning line.
 */
export function condensedReason(reasoning) {
  if (!reasoning || reasoning.length === 0) return null;
  for (const line of reasoning) {
    const m = line.match(/נושא:\s*"([^"]+)"/);
    if (m) return m[1].trim();
  }
  const meaningful = reasoning.filter((l) => !l.includes("החלטה סופית"));
  const finalLine = [...reasoning].reverse().find((l) => l.includes("החלטה סופית"));
  return (meaningful[meaningful.length - 1] || finalLine || reasoning[0]).trim();
}
