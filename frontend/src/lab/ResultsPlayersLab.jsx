import React, { useState } from "react";
import { ResultsPlayersEditor } from "@/components/results/ResultsPlayersSetting";

// Canonical taxonomy examples; this lab does not call the user API or save data.
const PLAYERS = [
  { entity_id: "player:deni_avdija", name: "דני אבדיה", name_en: "Deni Avdija", aliases: ["אבדיה"] },
  { entity_id: "player:roman_sorkin", name: "רומן סורקין", name_en: "Roman Sorkin", aliases: ["סורקין"] },
  { entity_id: "player:yam_madar", name: "ים מדר", name_en: "Yam Madar", aliases: [] },
  { entity_id: "player:lebron_james", name: "לברון ג'יימס", name_en: "LeBron James", aliases: [] },
];
export default function ResultsPlayersLab() {
  const [selected, setSelected] = useState(["player:deni_avdija"]);
  const [saved, setSaved] = useState(false);
  return <main className="signal-ui sg-personalization sg-gutter" style={{ paddingBlock: 24 }}>
    <div className="sg-container"><h1>שחקנים בתוצאות — חלופת כיוונון</h1>
      <p className="sg-form-note">דוגמה לבחירת המיקום. הבחירה כאן נשארת במעבדה.</p>
      <ResultsPlayersEditor catalog={PLAYERS} selected={selected} onChange={(ids) => { setSelected(ids); setSaved(false); }}
        onSave={() => setSaved(true)} saved={saved} mode="calibration" />
    </div>
  </main>;
}
