import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { legacyPreferencesTarget } from "./preferencesRoutes";

export default function LegacyPreferencesRedirect() {
  const { pathname, search, hash } = useLocation();
  return <Navigate replace to={legacyPreferencesTarget(pathname, search, hash)} />;
}
