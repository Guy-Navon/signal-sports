// Is a pointer position on actual text? Used so a mouse drag over text keeps
// native selection while a drag over empty space can scroll.
//
// Hit test: the caret API (standard caretPositionFromPoint in Firefox and recent
// Chromium, caretRangeFromPoint in older Chromium and Safari) returns the text
// node nearest the point, even when the point is far from it, so the point must
// also fall inside one of that node's line boxes. Anything uncertain (no API, a
// throw, form fields, selectable shadow content) counts as text: no drag.

const SLOP = 1; // px of tolerance around a glyph box

const NATIVE_TEXT_TARGET = /^(INPUT|TEXTAREA|SELECT|OPTION)$/;

function caretNode(doc, x, y) {
  if (typeof doc.caretPositionFromPoint === "function") return doc.caretPositionFromPoint(x, y)?.offsetNode ?? null;
  if (typeof doc.caretRangeFromPoint === "function") return doc.caretRangeFromPoint(x, y)?.startContainer ?? null;
  return undefined; // unsupported
}

function insideRects(rects, x, y) {
  for (const r of rects) {
    if (x >= r.left - SLOP && x <= r.right + SLOP && y >= r.top - SLOP && y <= r.bottom + SLOP) return true;
  }
  return false;
}

/**
 * @param {Document} doc
 * @param {number} x clientX
 * @param {number} y clientY
 * @param {Element|null} [target] the event target, for form fields
 * @returns {boolean} true when on text, or when unsure
 */
export function pointIsOnText(doc, x, y, target = null) {
  try {
    if (target && NATIVE_TEXT_TARGET.test(target.tagName || "")) return true;
    if (!doc || !Number.isFinite(x) || !Number.isFinite(y)) return true;
    const node = caretNode(doc, x, y);
    if (node === undefined) return true;
    if (!node || node.nodeType !== 3 || !/\S/.test(node.nodeValue || "")) return false;
    const range = doc.createRange();
    range.selectNodeContents(node);
    return insideRects(Array.from(range.getClientRects()), x, y);
  } catch {
    return true;
  }
}
