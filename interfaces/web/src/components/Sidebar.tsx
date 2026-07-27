import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { api } from '@/api/client';
import { useWorkflowStore, type SseStatus } from '@/store/workflowStore';

type HealthState = 'checking' | 'ok' | 'bad';

const HEALTH_POLL_MS = 10_000;

function DashboardIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </svg>
  );
}

function HistoryIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15.5 14" />
    </svg>
  );
}

function ServicesIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="4" width="20" height="6" rx="2" />
      <rect x="2" y="14" width="20" height="6" rx="2" />
      <line x1="6" y1="7" x2="6.01" y2="7" />
      <line x1="6" y1="17" x2="6.01" y2="17" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function HomeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9.5 12 3l9 6.5" />
      <path d="M5 10v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V10" />
      <path d="M9 21v-6h6v6" />
    </svg>
  );
}

const NAV_ITEMS = [
  { to: '/', label: '总控台', icon: <DashboardIcon />, end: true },
  { to: '/history', label: '历史', icon: <HistoryIcon />, end: false },
  { to: '/services', label: '服务', icon: <ServicesIcon />, end: false },
  { to: '/settings', label: '配置', icon: <SettingsIcon />, end: false },
];

const SSE_TEXT: Record<SseStatus, string> = {
  open: '实时流已连接',
  connecting: '实时流重连中…',
  closed: '实时流已关闭',
};

/** 左侧导航栏：Logo + 菜单 + 底部后端健康状态灯 */
export default function Sidebar() {
  const [health, setHealth] = useState<HealthState>('checking');
  const sseStatus = useWorkflowStore((s) => s.sseStatus);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        await api.health();
        if (!cancelled) setHealth('ok');
      } catch {
        if (!cancelled) setHealth('bad');
      }
    };
    void check();
    const timer = window.setInterval(() => void check(), HEALTH_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark">A</div>
        <div>
          <div className="sidebar-logo-name">AgentForge</div>
          <div className="sidebar-logo-sub">智能体编排平台</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <a href="/" className="nav-item nav-home" title="返回旧版主界面">
          <HomeIcon />
          返回主页
        </a>
        <div className="health-row">
          <span className={`dot ${health === 'ok' ? 'ok' : health === 'bad' ? 'bad' : 'checking'}`} />
          {health === 'ok' ? '后端服务正常' : health === 'bad' ? '后端服务异常' : '检测后端状态…'}
        </div>
        <div className="health-row">
          <span
            className={`dot ${sseStatus === 'open' ? 'ok' : sseStatus === 'connecting' ? 'checking' : 'idle'}`}
          />
          {SSE_TEXT[sseStatus]}
        </div>
      </div>
    </aside>
  );
}
