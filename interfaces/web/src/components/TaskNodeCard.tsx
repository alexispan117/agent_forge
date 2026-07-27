import type { CSSProperties } from 'react';
import type { TaskNode } from '@/api/types';
import { agentText, TASK_STATUS_TEXT } from '@/utils/format';

/** Agent 类型徽章配色（未知类型使用默认 slate） */
const AGENT_COLORS: Record<string, string> = {
  analyst: '#6366f1',
  desensitize: '#f59e0b',
  report: '#10b981',
};

interface TaskNodeCardProps {
  task: TaskNode;
  selected: boolean;
  style: CSSProperties;
  onClick: (taskId: string) => void;
}

/** DAG 中的单个任务节点卡片 */
export default function TaskNodeCard({ task, selected, style, onClick }: TaskNodeCardProps) {
  const agentColor = AGENT_COLORS[task.agent] ?? '#64748b';

  return (
    <div
      className={`task-node st-${task.status}${selected ? ' selected' : ''}`}
      style={style}
      onClick={() => onClick(task.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick(task.id);
        }
      }}
      title={`${task.name} · ${TASK_STATUS_TEXT[task.status]}`}
    >
      <div className="task-node-name">{task.name}</div>
      <div className="task-node-meta">
        <span className="agent-chip" style={{ background: agentColor }}>
          {agentText(task.agent)}
        </span>
        {task.retries > 0 && <span className="retry-chip">重试×{task.retries}</span>}
        <span className="task-node-status">
          <span className={`status-dot ${task.status}`} />
          {TASK_STATUS_TEXT[task.status]}
        </span>
      </div>
    </div>
  );
}
