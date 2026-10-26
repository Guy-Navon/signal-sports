// What "למה אצלך" shows (journey audit D6). A reader gets one Hebrew sentence the backend
// built from the step that actually decided the article (`reason_he`), or nothing at all;
// never the engine trace, which stays for ops (admin, local QA) and the Debug console.
import { condensedReason } from "@/components/feed/storyLabels";

/**
 * @param {{ showTrace: boolean, reason: string | null | undefined, reasoning: string[] | undefined }} p
 * @returns {null | { mode: "reader" | "trace", text: string, steps: string[] }}
 */
export function deskVoiceView({ showTrace, reason, reasoning }) {
  if (showTrace) {
    const text = condensedReason(reasoning);
    return text ? { mode: "trace", text, steps: (reasoning || []).slice(-4) } : null;
  }
  return reason ? { mode: "reader", text: reason, steps: [] } : null;
}
