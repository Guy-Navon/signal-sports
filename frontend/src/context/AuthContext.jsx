import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  AUTH_EXPIRED_EVENT,
  authLogin,
  authLogout,
  authSignup,
  getAuthSession,
} from "@/api/client";
import { deriveAuthView } from "@/context/authView";

const DATA_MODE = /** @type {any} */ (import.meta).env?.VITE_DATA_MODE || "local";

const AuthContext = createContext(null);

// The auth shell (User Platform PR 3, issue #51). Bootstraps once from
// GET /api/auth/session and exposes { authEnforced, user, onboarding }.
// Runtime-adaptive: in local mode or when the backend reports
// auth_enforced=false (bypass), the app renders exactly the pre-auth UI and
// this provider is a passive no-op shell. Must live inside BrowserRouter
// (it navigates on logout/session-expiry).
export function AuthProvider({ children }) {
  const isBackendMode = DATA_MODE === "backend";
  const [bootstrap, setBootstrap] = useState(null);
  const [bootstrapped, setBootstrapped] = useState(!isBackendMode);
  const [bootstrapError, setBootstrapError] = useState(false);
  const sessionRequest = useRef(0);
  const navigate = useNavigate();
  const location = useLocation();

  const view = useMemo(
    () => deriveAuthView(isBackendMode && !bootstrapped ? "backend" : DATA_MODE,
      bootstrapped ? bootstrap : null),
    [bootstrap, bootstrapped, isBackendMode],
  );

  const refreshSession = useCallback(async () => {
    if (!isBackendMode) return null;
    const requestId = ++sessionRequest.current;
    try {
      const payload = await getAuthSession();
      if (requestId !== sessionRequest.current) return null;
      setBootstrap(payload);
      setBootstrapError(false);
      return payload;
    } catch {
      if (requestId !== sessionRequest.current) return null;
      // Connectivity failure is not permission to enter the bypass UI.
      setBootstrap({ auth_enforced: true, user: null, onboarding: null });
      setBootstrapError(true);
      return null;
    } finally {
      if (requestId === sessionRequest.current) setBootstrapped(true);
    }
  }, [isBackendMode]);

  useEffect(() => {
    refreshSession();
  }, [refreshSession]);

  // Session expiry: any 401 from an authenticated (non-auth-route) API call.
  useEffect(() => {
    if (!isBackendMode) return undefined;
    const onExpired = () => {
      sessionRequest.current += 1;
      setBootstrap((prev) =>
        prev && prev.auth_enforced
          ? { ...prev, user: null, onboarding: null }
          : prev,
      );
      if (bootstrap?.auth_enforced && location.pathname !== "/login") {
        navigate("/login", { replace: true, state: { expired: true } });
      }
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [isBackendMode, bootstrap, location.pathname, navigate]);

  const login = useCallback(
    async (email, password) => {
      await authLogin(email, password);
      await refreshSession();
    },
    [refreshSession],
  );

  const signup = useCallback(
    async ({ email, password, displayName }) => {
      await authSignup({ email, password, displayName });
      await refreshSession();
    },
    [refreshSession],
  );

  const logout = useCallback(async () => {
    try {
      await authLogout();
    } finally {
      const payload = await refreshSession();
      if (payload?.auth_enforced) {
        navigate("/login", { replace: true });
      }
    }
  }, [navigate, refreshSession]);

  const value = useMemo(
    () => ({
      status: view.mode === "loading" ? "loading" : "ready",
      mode: view.mode,
      authEnforced: view.authEnforced,
      user: view.user,
      onboarding: view.onboarding,
      login,
      signup,
      logout,
      refreshSession,
    }),
    [view, login, signup, logout, refreshSession],
  );

  if (bootstrapError) {
    return (
      <main dir="rtl" className="min-h-screen flex flex-col items-center justify-center gap-4 p-6">
        <p role="alert">לא ניתן להתחבר לשרת. נסו שוב בעוד רגע.</p>
        <button type="button" onClick={refreshSession} className="underline">ניסיון נוסף</button>
      </main>
    );
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
