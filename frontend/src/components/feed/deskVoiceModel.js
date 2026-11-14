// What "למה אצלך" shows (journey audit D6). A reader gets one Hebrew sentence the backend
// built from the step that actually decided the article (`reason_he`), or nothing at all;
// never the engine trace, which stays in the Debug console for admins and local QA.

/**
 * @param {{ reason: string | null | undefined, showTrace?: boolean, reasoning?: string[] }} p
 * @returns {null | { mode: "reader", text: string, steps: string[] }}
 */
export function deskVoiceView({ reason }) {
  return reason ? { mode: "reader", text: reason, steps: [] } : null;
}
