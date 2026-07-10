import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { requiresLoginRedirect } from "@/context/authView";

// Route guard (User Platform PR 3, #51). Only active under real enforcement:
// in local mode and backend-bypass mode it renders straight through, keeping
// the pre-auth UI pixel-identical. While the session bootstrap is in flight
// it renders nothing (one frame on a same-origin call) rather than flashing
// a login redirect at signed-in users.
export default function RequireSession() {
  const auth = useAuth();
  if (auth.status === "loading") return null;
  if (requiresLoginRedirect(auth)) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
