import { useSettingsStore } from '@/store/settingsStore';

const POLL_OPTIONS = [
  { value: 0, label: '关闭轮询' },
  { value: 1000, label: '1 秒' },
  { value: 2000, label: '2 秒' },
  { value: 3000, label: '3 秒（推荐）' },
  { value: 5000, label: '5 秒' },
  { value: 10000, label: '10 秒' },
];

const LOG_OPTIONS = [50, 100, 200, 500];

/** 配置页：本地偏好（SSE 开关 / 日志条数 / 轮询间隔），persist 到 localStorage */
export default function SettingsPage() {
  const sseEnabled = useSettingsStore((s) => s.sseEnabled);
  const maxLogs = useSettingsStore((s) => s.maxLogs);
  const pollIntervalMs = useSettingsStore((s) => s.pollIntervalMs);
  const setSseEnabled = useSettingsStore((s) => s.setSseEnabled);
  const setMaxLogs = useSettingsStore((s) => s.setMaxLogs);
  const setPollIntervalMs = useSettingsStore((s) => s.setPollIntervalMs);

  return (
    <div>
      <h1 className="page-title">配置</h1>
      <p className="page-desc">前端本地偏好设置，即时生效并保存在浏览器 localStorage</p>

      <section className="card settings-card">
        <div className="card-body">
          <div className="setting-row">
            <div className="setting-info">
              <div className="setting-name">SSE 实时事件流</div>
              <div className="setting-desc">
                通过 /stream 接收工作流与任务事件；关闭后仅依赖轮询更新
              </div>
            </div>
            <label className="switch">
              <input
                type="checkbox"
                checked={sseEnabled}
                onChange={(e) => setSseEnabled(e.target.checked)}
              />
              <span className="switch-track" />
            </label>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <div className="setting-name">实时日志最大条数</div>
              <div className="setting-desc">超出后自动丢弃最早的日志条目</div>
            </div>
            <select
              className="select"
              value={maxLogs}
              onChange={(e) => setMaxLogs(Number(e.target.value))}
            >
              {LOG_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n} 条
                </option>
              ))}
            </select>
          </div>

          <div className="setting-row">
            <div className="setting-info">
              <div className="setting-name">工作流轮询间隔</div>
              <div className="setting-desc">
                工作流未到达终态时的兜底刷新频率（SSE 正常时可设长一些）
              </div>
            </div>
            <select
              className="select"
              value={pollIntervalMs}
              onChange={(e) => setPollIntervalMs(Number(e.target.value))}
            >
              {POLL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="settings-note">
            说明：LLM 模式、Worker 地址等服务端配置由项目根目录的 <b>config.yaml</b>{' '}
            管理，前端不提供修改入口；修改后需重启后端服务生效。
          </div>
        </div>
      </section>
    </div>
  );
}
