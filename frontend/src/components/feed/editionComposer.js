// The edition composer: partitions the ranked visible feed into the edition's
// tiers. Items arrive pre-sorted (decision rank desc, then recency) from both
// data modes; the composer is a stable partition so the engine's prioritisation
// is preserved inside every tier.
//
//   lead      — the single top story (first push, else first high_feed),
//               framed as "הסיפור המרכזי"
//   bulletins — remaining push stories (rendered as מבזק strips)
//   editorial — high_feed stories ("במוקד" tier)
//   stream    — feed stories ("עוד מהפיד" rows)
//   briefs    — low_feed stories ("קריאה נוספת" digest)

export function composeEdition(items) {
  const push = [];
  const high = [];
  const stream = [];
  const briefs = [];

  for (const item of items) {
    const decision = item.score?.decision;
    if (decision === "push") push.push(item);
    else if (decision === "high_feed") high.push(item);
    else if (decision === "feed") stream.push(item);
    else if (decision === "low_feed") briefs.push(item);
    // hidden / undecided items never reach the composer (getVisibleItems),
    // but tolerate them by dropping.
  }

  let lead = null;
  let bulletins = [];
  let editorial = high;

  if (push.length > 0) {
    [lead, ...bulletins] = push;
  } else if (high.length > 0) {
    [lead, ...editorial] = high;
  }

  return { lead, bulletins, editorial, stream, briefs };
}
