/**
 * #250: record that the reader opened an article's source, for the pilot's "was it
 * used?" question. Fire-and-forget: it never blocks or breaks navigation, never
 * enters the local feedback list, and has no learning effect on the server
 * (`article_opened` is a passive event, docs/FEEDBACK_LEARNING.md).
 *
 * @param {string | undefined} articleId
 * @param {{ enabled: boolean, send: (id: string, action: string) => Promise<unknown> }} opts
 * @returns {boolean} whether a request was sent
 */
export function recordArticleOpened(articleId, { enabled, send }) {
  if (!enabled || !articleId) return false;
  try {
    Promise.resolve(send(articleId, "article_opened")).catch(() => {});
  } catch {
    // a synchronous failure must not stop the link from opening
  }
  return true;
}
