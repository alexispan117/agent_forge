import { useMemo } from 'react';
import { useWorkflowStore } from '@/store/workflowStore';

/** 任务指标卡：总数 / 成功 / 降级 / 失败（从 task_tree 实时统计） */
export default function MetricCards() {
  const taskTree = useWorkflowStore((s) => s.taskTree);

  const stats = useMemo(() => {
    let done = 0;
    let degraded = 0;
    let failed = 0;
    for (const task of taskTree) {
      if (task.status === 'done') done += 1;
      else if (task.status === 'degraded') degraded += 1;
      else if (task.status === 'failed') failed += 1;
    }
    return { total: taskTree.length, done, degraded, failed };
  }, [taskTree]);

  const cards = [
    {
      key: 'total',
      label: '任务总数',
      value: stats.total,
      className: 'c-total',
      icon: (
        <svg className="metric-card-icon" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="8" y1="6" x2="21" y2="6" />
          <line x1="8" y1="12" x2="21" y2="12" />
          <line x1="8" y1="18" x2="21" y2="18" />
          <line x1="3" y1="6" x2="3.01" y2="6" />
          <line x1="3" y1="12" x2="3.01" y2="12" />
          <line x1="3" y1="18" x2="3.01" y2="18" />
        </svg>
      ),
    },
    {
      key: 'done',
      label: '成功',
      value: stats.done,
      className: 'c-done',
      icon: (
        <svg className="metric-card-icon" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      ),
    },
    {
      key: 'degraded',
      label: '降级',
      value: stats.degraded,
      className: 'c-degraded',
      icon: (
        <svg className="metric-card-icon" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      ),
    },
    {
      key: 'failed',
      label: '失败',
      value: stats.failed,
      className: 'c-failed',
      icon: (
        <svg className="metric-card-icon" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      ),
    },
  ];

  return (
    <div className="metric-grid">
      {cards.map((card) => (
        <div key={card.key} className={`metric-card ${card.className}`}>
          <div className="metric-card-top">
            {card.icon}
            {card.label}
          </div>
          <div className="metric-card-value">{card.value}</div>
        </div>
      ))}
    </div>
  );
}
