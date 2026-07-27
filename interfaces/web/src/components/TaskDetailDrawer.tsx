import { useEffect } from 'react';
import StatusBadge from '@/components/StatusBadge';
import type { TaskNode } from '@/api/types';
import { useWorkflowStore } from '@/store/workflowStore';
import {
  agentText,
  formatDuration,
  formatTime,
  shortId,
} from '@/utils/format';

interface TaskDetailDrawerProps {
  task: TaskNode | null;
}

/** 任务详情抽屉：完整 result / error / 耗时 / 重试次数 */
export default function TaskDetailDrawer({ task }: TaskDetailDrawerProps) {
  const selectTask = useWorkflowStore((s) => s.selectTask);

  // Esc 关闭抽屉
  useEffect(() => {
    if (!task) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') selectTask(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [task, selectTask]);

  if (!task) return null;

  const close = () => selectTask(null);

  return (
    <>
      <div className="drawer-overlay" onClick={close} />
      <aside className="drawer" role="dialog" aria-label="任务详情">
        <div className="drawer-header">
          <div style={{ minWidth: 0 }}>
            <h3 className="drawer-title">{task.name}</h3>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <StatusBadge status={task.status} kind="task" />
              <span className="badge badge-indigo">{agentText(task.agent)}</span>
            </div>
          </div>
          <button type="button" className="drawer-close" aria-label="关闭" onClick={close}>
            ✕
          </button>
        </div>

        <div className="drawer-body">
          <div className="detail-grid">
            <div>
              <div className="detail-item-label">任务 ID</div>
              <div className="detail-item-value">{shortId(task.id)}</div>
            </div>
            <div>
              <div className="detail-item-label">执行 Agent</div>
              <div className="detail-item-value">{task.agent}</div>
            </div>
            <div>
              <div className="detail-item-label">耗时</div>
              <div className="detail-item-value">
                {formatDuration(task.started_at, task.completed_at)}
                {task.status === 'running' && task.started_at !== null ? '（进行中）' : ''}
              </div>
            </div>
            <div>
              <div className="detail-item-label">重试次数</div>
              <div className="detail-item-value">{task.retries}</div>
            </div>
            <div>
              <div className="detail-item-label">开始时间</div>
              <div className="detail-item-value">
                {task.started_at !== null ? formatTime(task.started_at) : '—'}
              </div>
            </div>
            <div>
              <div className="detail-item-label">完成时间</div>
              <div className="detail-item-value">
                {task.completed_at !== null ? formatTime(task.completed_at) : '—'}
              </div>
            </div>
          </div>

          {task.depends_on.length > 0 && (
            <>
              <div className="detail-section-title">依赖任务</div>
              <div className="dep-chips">
                {task.depends_on.map((dep) => (
                  <span key={dep} className="badge badge-gray mono">
                    {shortId(dep)}
                  </span>
                ))}
              </div>
            </>
          )}

          {task.error && (
            <>
              <div className="detail-section-title">错误信息</div>
              <div className="error-block">{task.error}</div>
            </>
          )}

          <div className="detail-section-title">执行结果</div>
          {task.result ? (
            <div className="result-block">{task.result}</div>
          ) : (
            <div className="result-block text-tertiary">
              {task.status === 'pending'
                ? '任务尚未开始执行'
                : task.status === 'running'
                  ? '任务执行中，结果将在完成后展示…'
                  : '暂无结果输出'}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
