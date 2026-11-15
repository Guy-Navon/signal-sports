// Short Hebrew display names for the 30 NBA teams, used by result rows and tiles.
// An explicit map, not a heuristic: "לוס אנג'לס" alone would collide for the Lakers
// and the Clippers. The popup keeps the full taxonomy names. Anything not listed
// falls back to the name the API supplied.
export const NBA_SHORT_NAMES = {
  "team:atlanta_hawks": "אטלנטה",
  "team:boston_celtics": "בוסטון",
  "team:brooklyn_nets": "ברוקלין",
  "team:charlotte_hornets": "שארלוט",
  "team:chicago_bulls": "שיקגו",
  "team:cleveland_cavaliers": "קליבלנד",
  "team:dallas_mavericks": "דאלאס",
  "team:denver_nuggets": "דנבר",
  "team:detroit_pistons": "דטרויט",
  "team:golden_state_warriors": "גולדן סטייט",
  "team:houston_rockets": "יוסטון",
  "team:indiana_pacers": "אינדיאנה",
  "team:la_clippers": "קליפרס",
  "team:la_lakers": "לייקרס",
  "team:memphis_grizzlies": "ממפיס",
  "team:miami_heat": "מיאמי",
  "team:milwaukee_bucks": "מילווקי",
  "team:minnesota_timberwolves": "מינסוטה",
  "team:new_orleans_pelicans": "ניו אורלינס",
  "team:ny_knicks": "ניו יורק",
  "team:okc_thunder": "אוקלהומה סיטי",
  "team:orlando_magic": "אורלנדו",
  "team:philadelphia_76ers": "פילדלפיה",
  "team:phoenix_suns": "פיניקס",
  "team:portland_blazers": "פורטלנד",
  "team:sacramento_kings": "סקרמנטו",
  "team:san_antonio_spurs": "סן אנטוניו",
  "team:toronto_raptors": "טורונטו",
  "team:utah_jazz": "יוטה",
  "team:washington_wizards": "וושינגטון",
};

export function shortTeamName(team) {
  if (!team) return "";
  return (team.id && NBA_SHORT_NAMES[team.id]) || team.name || "";
}
