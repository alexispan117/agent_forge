import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import ErrorBoundary from '@/components/ErrorBoundary';
import Sidebar from '@/components/Sidebar';
import Toaster from '@/components/Toaster';
import { useSettingsStore } from '@/store/settingsStore';
import { useWorkflowStore } from '@/store/workflowStore';

/**
 * 全局布局：左侧导航 + 右侧内容区（无顶栏）。
 * 同时负责 SSE 连接的生命周期：跟随设置开关，卸载时关闭。
 */
export default function Layout() {
  const sseEnabled = useSettingsStore((s) => s.sseEnabled);
  const connectSSE = useWorkflowStore((s) => s.connectSSE);
  const disconnectSSE = useWorkflowStore((s) => s.disconnectSSE);

  useEffect(() => {
    if (sseEnabled) {
      connectSSE();
    } else {
      disconnectSSE();
    }
    return () => disconnectSSE();
  }, [sseEnabled, connectSSE, disconnectSSE]);

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="content">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
      <Toaster />
    </div>
  );
}
