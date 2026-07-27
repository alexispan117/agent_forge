import { useEffect } from 'react';
import StatusBadge from '@/components/StatusBadge';
import { useWorkflowStore } from '@/store/workflowStore';

/** 服务页：/api/agents/cards 完整卡片视图（能力徽章 + 工具列表 + input_schema 展开） */
export default function ServicesPage() {
  const agents = useWorkflowStore((s) => s.agents);
  const agentsLoading = useWorkflowStore((s) => s.agentsLoading);
  const agentsError = useWorkflowStore((s) => s.agentsError);
  const fetchAgents = useWorkflowStore((s) => s.fetchAgents);

  useEffect(() => {
    void fetchAgents();
  }, [fetchAgents]);

  return (
    <div>
      <h1 className="page-title">服务</h1>
      <p className="page-desc">A2A 服务发现：各 Worker 的 AgentCard、能力清单与工具签名</p>

      {agentsLoading && agents.length === 0 ? (
        <div className="service-grid">
          <div className="skeleton" style={{ height: 220 }} />
          <div className="skeleton" style={{ height: 220 }} />
          <div className="skeleton" style={{ height: 220 }} />
        </div>
      ) : agentsError && agents.length === 0 ? (
        <div className="inline-error">
          <span>{agentsError}</span>
          <button type="button" className="btn btn-ghost" onClick={() => void fetchAgents()}>
            重试
          </button>
        </div>
      ) : agents.length === 0 ? (
        <div className="card empty-state">未发现 Worker 服务</div>
      ) : (
        <div className="service-grid">
          {agents.map((agent) => (
            <section key={agent.name} className="card">
              <div className="card-body">
                <div className="service-head">
                  <span className={`dot ${agent.status === 'online' ? 'ok' : 'bad'}`} />
                  <span className="service-name">{agent.name}</span>
                  <span style={{ marginLeft: 'auto' }}>
                    <StatusBadge status={agent.status} />
                  </span>
                </div>

                <div className="service-endpoint">{agent.endpoint}</div>

                {agent.description && (
                  <p style={{ margin: '0 0 10px', fontSize: 12.5, color: 'var(--text-secondary)' }}>
                    {agent.description}
                  </p>
                )}

                {agent.status === 'offline' && agent.error && (
                  <p className="service-error-text">连接失败：{agent.error}</p>
                )}

                {agent.capabilities && agent.capabilities.length > 0 && (
                  <div className="cap-chips">
                    {agent.capabilities.map((cap) => (
                      <span key={cap} className="badge badge-indigo">
                        {cap}
                      </span>
                    ))}
                  </div>
                )}

                {agent.tools && agent.tools.length > 0 && (
                  <>
                    <div className="detail-section-title">工具列表（{agent.tools.length}）</div>
                    {agent.tools.map((tool) => (
                      <details key={tool.name} className="tool-item">
                        <summary>
                          <span className="tool-name">{tool.name}</span>
                          {tool.description && (
                            <span className="tool-desc" title={tool.description}>
                              {tool.description}
                            </span>
                          )}
                        </summary>
                        {tool.description && (
                          <div style={{ padding: '8px 12px 0', fontSize: 12, color: 'var(--text-secondary)' }}>
                            {tool.description}
                          </div>
                        )}
                        <pre className="tool-schema">
                          {tool.input_schema
                            ? JSON.stringify(tool.input_schema, null, 2)
                            : '无输入参数'}
                        </pre>
                      </details>
                    ))}
                  </>
                )}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
