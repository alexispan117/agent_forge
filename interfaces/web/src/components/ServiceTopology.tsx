import { useEffect } from 'react';
import { useWorkflowStore } from '@/store/workflowStore';

/** 服务拓扑（精简版）：三个 Worker 的在线状态与工具数 */
export default function ServiceTopology() {
  const agents = useWorkflowStore((s) => s.agents);
  const agentsLoading = useWorkflowStore((s) => s.agentsLoading);
  const agentsError = useWorkflowStore((s) => s.agentsError);
  const fetchAgents = useWorkflowStore((s) => s.fetchAgents);

  useEffect(() => {
    void fetchAgents();
  }, [fetchAgents]);

  return (
    <section className="card">
      <div className="card-header">
        <div className="card-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="5" cy="6" r="2.2" />
            <circle cx="19" cy="6" r="2.2" />
            <circle cx="12" cy="18" r="2.2" />
            <path d="M6.8 7.3 10.5 16M17.2 7.3 13.5 16M7.2 6h9.6" />
          </svg>
          服务拓扑
        </div>
        <button type="button" className="log-clear-btn" onClick={() => void fetchAgents()}>
          刷新
        </button>
      </div>
      <div className="card-body">
        {agentsLoading && agents.length === 0 ? (
          <>
            <div className="skeleton skeleton-row" />
            <div className="skeleton skeleton-row" />
            <div className="skeleton skeleton-row" />
          </>
        ) : agentsError && agents.length === 0 ? (
          <div className="inline-error">
            <span>{agentsError}</span>
            <button type="button" className="btn btn-ghost" onClick={() => void fetchAgents()}>
              重试
            </button>
          </div>
        ) : agents.length === 0 ? (
          <div className="empty-state">未发现 Worker 服务</div>
        ) : (
          agents.map((agent) => (
            <div key={agent.name} className="agent-row">
              <span className={`dot ${agent.status === 'online' ? 'ok' : 'idle'}`} />
              <div className="agent-row-info">
                <div className="agent-row-name">{agent.name}</div>
                <div className="agent-row-desc" title={agent.description ?? agent.endpoint}>
                  {agent.status === 'online'
                    ? agent.description ?? agent.endpoint
                    : `离线 · ${agent.error ?? '连接失败'}`}
                </div>
              </div>
              {agent.status === 'online' && (
                <span className="badge badge-indigo">{agent.tools?.length ?? 0} 工具</span>
              )}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
