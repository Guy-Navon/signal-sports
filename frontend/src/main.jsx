import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import { AuthProvider } from '@/context/AuthContext';
import AppShell from '@/components/shell/AppShell';
import RequireSession from '@/components/shell/RequireSession';
import Feed from '@/pages/Feed';
import Preferences from '@/pages/Preferences';
import Calibration from '@/pages/Calibration';
import Sources from '@/pages/Sources';
import Results from '@/pages/Results';
import Debug from '@/pages/Debug';
import LlmQa from '@/pages/LlmQa';
import Login from '@/pages/Login';
import Signup from '@/pages/Signup';
import PageNotFound from '@/lib/PageNotFound';
import { queryClientInstance } from '@/lib/query-client';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClientInstance}>
      <BrowserRouter>
        <AuthProvider>
          {/* AppProvider consumes AuthContext for the consumer/QA data split
              (User Platform PR 5, #53) — it must sit below AuthProvider. */}
          <AppProvider>
            <Routes>
              {/* Auth pages: product-styled routes OUTSIDE both AppShell groups
                  (PageNotFound precedent). Redirect away in local/bypass modes. */}
              <Route path="login" element={<Login />} />
              <Route path="signup" element={<Signup />} />

              {/* Session guard: pass-through in local/bypass; login-gate under
                  enforcement (User Platform PR 3). */}
              <Route element={<RequireSession />}>
                <Route element={<AppShell area="product" />}>
                  <Route index element={<Feed />} />
                  <Route path="preferences" element={<Preferences />} />
                  <Route path="calibration" element={<Calibration />} />
                  <Route path="results" element={<Results />} />
                </Route>
                <Route element={<AppShell area="ops" />}>
                  <Route path="sources" element={<Sources />} />
                  <Route path="debug" element={<Debug />} />
                  <Route path="llm-qa" element={<LlmQa />} />
                </Route>
              </Route>
              <Route path="*" element={<PageNotFound />} />
            </Routes>
          </AppProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
