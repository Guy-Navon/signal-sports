import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { AppProvider } from '@/context/AppContext';
import AppLayout from '@/components/layout/AppLayout';
import Feed from '@/pages/Feed';
import Preferences from '@/pages/Preferences';
import Calibration from '@/pages/Calibration';
import Sources from '@/pages/Sources';
import Results from '@/pages/Results';
import Debug from '@/pages/Debug';
import PageNotFound from '@/lib/PageNotFound';
import { queryClientInstance } from '@/lib/query-client';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClientInstance}>
      <AppProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Feed />} />
              <Route path="preferences" element={<Preferences />} />
              <Route path="calibration" element={<Calibration />} />
              <Route path="sources" element={<Sources />} />
              <Route path="results" element={<Results />} />
              <Route path="debug" element={<Debug />} />
            </Route>
            <Route path="*" element={<PageNotFound />} />
          </Routes>
        </BrowserRouter>
      </AppProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
