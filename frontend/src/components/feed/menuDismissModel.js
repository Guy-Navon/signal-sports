// The thumbs-down menu's dismissal rules (journey audit D9). Pure and node-tested;
// FeedbackControls attaches the document listeners.

/**
 * @param {{ type: "keydown" | "pointerdown", key?: string, inside: boolean }} e
 * @returns {{ close: boolean, restoreFocus: boolean }}
 */
export function menuDismissAction({ type, key, inside }) {
  if (type === "keydown" && key === "Escape") return { close: true, restoreFocus: true };
  if (type === "pointerdown" && !inside) return { close: true, restoreFocus: false };
  return { close: false, restoreFocus: false };
}
