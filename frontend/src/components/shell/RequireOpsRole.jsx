import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { canEnterOpsShell } from "@/context/dataRouting";

const DATA_MODE = /** @type {any} */ (import.meta).env?.VITE_DATA_MODE || "local";

// Ops-shell role boundary (#54 review, MEDIUM). Under a consumer session only
// admins may enter the console; non-admins are routed back to the product.
// Local mode and bypass keep today's open console. Defense in depth only —
// backend require_admin remains the authorization truth.
export default function RequireOpsRole() {
  const auth = useAuth();
  const view = {
    isBackendMode: DATA_MODE === "backend",
    authEnforced: auth.authEnforced,
    user: auth.user,
  };
  if (!canEnterOpsShell(view)) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
