import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { AuthProvider } from '@/context/AuthContext';
import AppShell from '@/components/shell/AppShell';
import RequireSession from '@/components/shell/RequireSession';
import RequireOpsRole from '@/components/shell/RequireOpsRole';
import { queryClientInstance } from '@/lib/query-client';
import './index.css';

// Route-level splitting keeps the consumer feed independent from heavy QA and
// ops tooling. Every route retains the same URL and guard contract.
const Feed = React.lazy(() => import('@/pages/Feed'));
const Preferences = React.lazy(() => import('@/pages/Preferences'));
const Calibration = React.lazy(() => import('@/pages/Calibration'));
const InterestSelection = React.lazy(() => import('@/pages/InterestSelection'));
const Sources = React.lazy(() => import('@/pages/Sources'));
const Results = React.lazy(() => import('@/pages/Results'));
const Account = React.lazy(() => import('@/pages/Account'));
const Debug = React.lazy(() => import('@/pages/Debug'));
const LlmQa = React.lazy(() => import('@/pages/LlmQa'));
const Login = React.lazy(() => import('@/pages/Login'));
const Onboarding = React.lazy(() => import('@/pages/Onboarding'));
const Signup = React.lazy(() => import('@/pages/Signup'));
const PageNotFound = React.lazy(() => import('@/lib/PageNotFound'));

function RouteFallback() {
  return (
    <div className="grid min-h-[45vh] place-items-center bg-background text-foreground" aria-busy="true">
      <div className="flex items-center gap-3">
        <span className="h-2 w-2 animate-pulse bg-signal-push" />
        <span className="font-mono text-[10px] font-bold tracking-[0.14em] text-text-secondary">
          SIGNAL / LOADING
        </span>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClientInstance}>
      <BrowserRouter>
        <AuthProvider>
          {/* AppProvider consumes AuthContext for the consumer/QA data split
              (User Platform PR 5, #53) — it must sit below AuthProvider. */}
          <AppProvider>
            <React.Suspense fallback={<RouteFallback />}>
              <Routes>
              {/* Auth pages: product-styled routes OUTSIDE both AppShell groups
                  (PageNotFound precedent). Redirect away in local/bypass modes. */}
              <Route path="login" element={<Login />} />
              <Route path="signup" element={<Signup />} />

              {/* Session guard: pass-through in local/bypass; login-gate under
                  enforcement (User Platform PR 3). */}
              <Route element={<RequireSession />}>
                {/* Welcome (PR 4, #52): a full-canvas product moment outside
                    the shells, inside the session guard. */}
                <Route path="welcome" element={<Onboarding />} />
                <Route element={<AppShell area="product" />}>
                  <Route index element={<Feed />} />
                  <Route path="preferences" element={<Preferences />} />
                  <Route path="interests" element={<InterestSelection />} />
                  <Route path="calibration" element={<Calibration />} />
                  <Route path="results" element={<Results />} />
                  <Route path="account" element={<Account />} />
                </Route>
                {/* Ops console: admin-only under a consumer session (#54);
                    local/bypass keep today's open console. */}
                <Route element={<RequireOpsRole />}>
                  <Route element={<AppShell area="ops" />}>
                    <Route path="sources" element={<Sources />} />
                    <Route path="debug" element={<Debug />} />
                    <Route path="llm-qa" element={<LlmQa />} />
                  </Route>
                </Route>
              </Route>
              <Route path="*" element={<PageNotFound />} />
              </Routes>
            </React.Suspense>
          </AppProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
