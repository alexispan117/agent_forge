import type { TaskStatus, WorkflowStatus } from '@/api/types';
import { TASK_STATUS_TEXT, WORKFLOW_STATUS_TEXT } from '@/utils/format';

type BadgeColor = 'gray' | 'indigo' | 'blue' | 'green' | 'red' | 'yellow';

const WORKFLOW_STYLE: Record<WorkflowStatus, { color: BadgeColor; pulse: boolean }> = {
  pending: { color: 'gray', pulse: false },
  decomposing: { color: 'indigo', pulse: true },
  ready: { color: 'blue', pulse: false },
  running: { color: 'blue', pulse: true },
  completed: { color: 'green', pulse: false },
};

const TASK_STYLE: Record<TaskStatus, { color: BadgeColor; pulse: boolean }> = {
  pending: { color: 'gray', pulse: false },
  running: { color: 'blue', pulse: true },
  done: { color: 'green', pulse: false },
  failed: { color: 'red', pulse: false },
  degraded: { color: 'yellow', pulse: false },
};

interface StatusBadgeProps {
  status: WorkflowStatus | TaskStatus | 'created' | 'online' | 'offline';
  kind?: 'workflow' | 'task';
}

/** 通用状态徽章：工作流 / 任务 / 服务状态统一视觉 */
export default function StatusBadge({ status, kind = 'workflow' }: StatusBadgeProps) {
  let text = String(status);
  let color: BadgeColor = 'gray';
  let pulse = false;

  if (status === 'created') {
    text = '已创建';
    color = 'indigo';
  } else if (status === 'online') {
    text = '在线';
    color = 'green';
  } else if (status === 'offline') {
    text = '离线';
    color = 'gray';
  } else if (kind === 'task' && status in TASK_STYLE) {
    const style = TASK_STYLE[status as TaskStatus];
    text = TASK_STATUS_TEXT[status as TaskStatus];
    color = style.color;
    pulse = style.pulse;
  } else if (status in WORKFLOW_STYLE) {
    const style = WORKFLOW_STYLE[status as WorkflowStatus];
    text = WORKFLOW_STATUS_TEXT[status as WorkflowStatus];
    color = style.color;
    pulse = style.pulse;
  }

  return (
    <span className={`badge badge-${color}${pulse ? ' badge-pulse' : ''}`}>
      <span className={`dot${pulse ? '' : ' idle'}`} style={pulse ? { background: 'currentColor' } : undefined} />
      {text}
    </span>
  );
}
