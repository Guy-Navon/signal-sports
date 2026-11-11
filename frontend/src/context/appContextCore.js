// The app context object and the hooks feed components read it through. Kept
// apart from AppContext.jsx (the provider, which pulls in the API client, auth
// and results) so a bundle that renders the feed without a provider — the
// public read-only demo, #458 — does not ship any of that code.
import { createContext, useContext } from "react";

export const AppContext = createContext(null);

// Safe outside the provider (capture harness, isolated renders): opens are then not recorded.
const NOOP = () => {};
export function useArticleOpened() {
  return useContext(AppContext)?.noteArticleOpened ?? NOOP;
}

// Whether the engine trace may be shown (ops: admin, local, bypass). Safe outside the
// provider (capture harness, isolated renders), where the trace shows as before.
export function useEngineTraceVisible() {
  const ctx = useContext(AppContext);
  return ctx ? Boolean(ctx.qaSurfaceAllowed) : true;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
