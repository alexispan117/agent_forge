import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '@/api/client';
import type { WorkflowDetail } from '@/api/types';
import StatusBadge from '@/components/StatusBadge';
import { useWorkflowStore } from '@/store/workflowStore';
import { formatDateTime } from '@/utils/format';
import { readHistory, removeHistory, type HistoryItem } from '@/utils/history';

interface HistoryRow {
  meta: HistoryItem;
  detail: WorkflowDetail | null;
  error: string | null;
}

/** 历史页：localStorage 中的工作流列表 + 逐条拉取详情 */
export default function HistoryPage() {
  const navigate = useNavigate();
  const loadWorkflow = useWorkflowStore((s) => s.loadWorkflow);
  const [rows, setRows] = useState<HistoryRow[] | null>(null);

  useEffect(() => {
    const items = readHistory();
    if (items.length === 0) {
      setRows([]);
      return;
    }
    setRows(items.map((meta) => ({ meta, detail: null, error: null })));

    let cancelled = false;
    void (async () => {
      const results = await Promise.all(
        items.map(async (meta): Promise<HistoryRow> => {
          try {
            const detail = await api.getWorkflow(meta.id);
            return { meta, detail, error: null };
          } catch (e) {
            const error =
              e instanceof ApiError && e.status === 404
                ? '工作流已被清理'
                : e instanceof ApiError
                  ? e.display
                  : '加载失败';
            return { meta, detail: null, error };
          }
        }),
      );
      if (!cancelled) setRows(results);
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleLoad = (id: string) => {
    void loadWorkflow(id);
    navigate('/');
  };

  const handleRemove = (id: string) => {
    removeHistory(id);
    setRows((prev) => (prev ? prev.filter((row) => row.meta.id !== id) : prev));
  };

  return (
    <div>
      <h1 className="page-title">历史</h1>
      <p className="page-desc">本机创建过的工作流记录（保存在浏览器 localStorage）</p>

      {rows === null ? (
        <div className="history-list">
          <div className="skeleton" style={{ height: 76 }} />
          <div className="skeleton" style={{ height: 76 }} />
          <div className="skeleton" style={{ height: 76 }} />
        </div>
      ) : rows.length === 0 ? (
        <div className="card empty-state">
          暂无历史记录。回到「总控台」提交第一个任务吧。
        </div>
      ) : (
        <div className="history-list">
          {rows.map((row) => (
            <div key={row.meta.id} className="card history-item">
              <div className="history-main">
                <div className="history-request" title={row.meta.request}>
                  {row.meta.request}
                </div>
                <div className="history-meta">
                  <span>{formatDateTime(row.meta.created_at)}</span>
                  <span title={row.meta.id}>ID {row.meta.id.slice(0, 8)}…</span>
                  {row.error && <span style={{ color: 'var(--color-danger)' }}>{row.error}</span>}
                </div>
              </div>

              {row.detail && (
                <div className="history-score">
                  <div className="history-score-value">
                    {row.detail.clear_scores?.efficacy?.toFixed(1) ?? '—'}
                  </div>
                  <div className="history-score-label">CLEAR 效能分</div>
                </div>
              )}

              {row.detail && <StatusBadge status={row.detail.status} />}

              <div className="history-actions">
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={!row.detail}
                  onClick={() => handleLoad(row.meta.id)}
                >
                  加载到总控台
                </button>
                <button
                  type="button"
                  className="btn btn-danger-outline"
                  onClick={() => handleRemove(row.meta.id)}
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
