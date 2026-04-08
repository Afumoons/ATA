import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/ui';
import { AuditTimelinePage } from './pages/AuditTimelinePage';
import { ExecutionDiagnosticsPage } from './pages/ExecutionDiagnosticsPage';
import { ManifestViewerPage } from './pages/ManifestViewerPage';
import { OverviewPage } from './pages/OverviewPage';
import { PoolOverviewPage } from './pages/PoolOverviewPage';

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/execution" element={<ExecutionDiagnosticsPage />} />
        <Route path="/pool" element={<PoolOverviewPage />} />
        <Route path="/manifest" element={<ManifestViewerPage />} />
        <Route path="/audit" element={<AuditTimelinePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
