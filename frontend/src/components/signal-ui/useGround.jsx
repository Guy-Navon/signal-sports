import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { DEFAULT_GROUND, normalizeGround, readGround, saveGround } from "./ground";
import "./signal-ui.css";
import "./ground-portals.css";

/** @typedef {{ ground: import("./ground").Ground, setGround: (value: string) => void }} GroundPreference */
const GroundContext = createContext(/** @type {GroundPreference | null} */ (null));
/** @type {GroundPreference} */
const DEFAULT_PREFERENCE = { ground: DEFAULT_GROUND, setGround: (_value) => {} };
const deviceStorage = () => window.localStorage;

export function GroundProvider({ children, initialGround = undefined }) {
  // The very first render already has the stored ground. An effect here would
  // allow a frame of white before dark/soft; no post-paint restoration is used.
  const [ground, updateGround] = useState(() => initialGround === undefined
    ? readGround(deviceStorage) : normalizeGround(initialGround));
  const setGround = useCallback((value) => updateGround(saveGround(value, deviceStorage)), []);
  const preference = useMemo(() => ({ ground, setGround }), [ground, setGround]);
  return <GroundContext.Provider value={preference}>{children}</GroundContext.Provider>;
}

// React context reaches portals even when their DOM is outside the shell.
// Consumers put these attributes on each .signal-ui root, including portals.
export function useGround() {
  return useConsumerGround() || DEFAULT_PREFERENCE;
}

// Shared primitives opt in only inside this provider. Ops has no provider,
// so it keeps its base palette and receives no Signal scope.
export function useConsumerGround() {
  return useContext(GroundContext);
}
