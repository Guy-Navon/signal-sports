import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { requiresLoginRedirect } from "@/context/authView";
import { onboardingRedirect } from "@/context/onboardingFlow";

// Route guard (User Platform PR 3 #51 + PR 4 #52). Only active under real
// enforcement: in local mode and backend-bypass mode it renders straight
// through, keeping the pre-auth UI pixel-identical. Under enforcement it
// (1) login-gates anonymous visitors and (2) routes not-yet-onboarded users
// into the derived onboarding state machine (welcome / resume-calibration).
export default function RequireSession() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "loading") return null;
  if (requiresLoginRedirect(auth)) {
    return <Navigate to="/login" replace />;
  }
  const target = onboardingRedirect(auth, location.pathname);
  if (target) {
    return <Navigate to={target} replace />;
  }
  return <Outlet />;
}
