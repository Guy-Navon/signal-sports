// Display-only headline parsing (#593). The source title and feed decisions stay intact.
// A mark between Hebrew letters belongs to an acronym, never a quote boundary.
const mark = '(?!(?<=[א-ת])["“”״](?=[א-ת]))["“”״]';
const contextFirst = new RegExp(`^(.+?):\\s*${mark}(.+)${mark}\\s*$`);
const quoteFirst = new RegExp(`^${mark}(.+?)${mark}\\s*:\\s*(.+)$`);
const quoteOnly = new RegExp(`^${mark}(.+)${mark}$`);

/**
 * Split only complete, anchored quotes; keep the contents verbatim.
 * @param {string} title
 * @returns {{ kind: "quote", context: string|null, quote: string } | { kind: "plain" }}
 */
export function headlineParts(title) {
  const after = contextFirst.exec(title);
  if (after) return { kind: "quote", context: after[1], quote: after[2] };
  const before = quoteFirst.exec(title);
  if (before) return { kind: "quote", context: before[2], quote: before[1] };
  const only = quoteOnly.exec(title);
  if (only) return { kind: "quote", context: null, quote: only[1] };
  return { kind: "plain" };
}

/**
 * Scores and numbers followed by a supported unit, with lossless plain spans.
 * @param {string} text
 * @returns {Array<{ text: string, emphasis: boolean }>}
 */
export function emphasisedNumbers(text) {
  const numbers = /(?<![\d:])\d+:\d+(?![\d:])|(?<![\d.])\d+\s+(?:(?:אלף|מיליון)(?:\s+(?:שקל|דולר|יורו))?|שקל|דולר|יורו|נקודות|ריבאונדים|אסיסטים|שערים|דקות)(?![\p{L}\p{N}])/gu;
  const segments = [];
  let end = 0;
  for (const match of text.matchAll(numbers)) {
    const start = match.index;
    if (start > end) segments.push({ text: text.slice(end, start), emphasis: false });
    segments.push({ text: match[0], emphasis: true });
    end = start + match[0].length;
  }
  if (end < text.length) segments.push({ text: text.slice(end), emphasis: false });
  return segments;
}
