// Honest feedback saves (#197). A thumbs-up used to say "נשמר" the moment it
// was tapped, while a failed request was swallowed: the reader believed the
// system had learned something it never received. The save now moves through
// pending → saved | failed, and only a confirmed save says "saved".
// Pure and node-tested; FeedbackControls renders it.

/** @typedef {"idle"|"pending"|"saved"|"failed"} FeedbackSaveStatus */

/**
 * Run one save and report each state. Never throws: the outcome is returned.
 * @param {() => Promise<unknown>} save
 * @param {(status: FeedbackSaveStatus) => void} onStatus
 * @returns {Promise<"saved"|"failed">}
 */
export async function runFeedbackSave(save, onStatus) {
  onStatus("pending");
  try {
    await save();
  } catch {
    onStatus("failed");
    return "failed";
  }
  onStatus("saved");
  return "saved";
}

/**
 * What the controls show for a status. null = the normal buttons.
 * @param {FeedbackSaveStatus} status
 */
export function feedbackSaveView(status) {
  switch (status) {
    case "pending":
      return { label: "שומר…", tone: "quiet", canRetry: false, busy: true };
    case "saved":
      return { label: "נשמר", tone: "ok", canRetry: false, busy: false };
    case "failed":
      return { label: "לא נשמר", tone: "error", canRetry: true, busy: false };
    default:
      return null;
  }
}
