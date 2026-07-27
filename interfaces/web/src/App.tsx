import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from '@/components/Layout';
import DashboardPage from '@/pages/DashboardPage';
import HistoryPage from '@/pages/HistoryPage';
import ServicesPage from '@/pages/ServicesPage';
import SettingsPage from '@/pages/SettingsPage';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="services" element={<ServicesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
