import { useEffect, useRef } from 'react';
import { useWorkflowStore, type SseStatus } from '@/store/workflowStore';

const SSE_DOT: Record<SseStatus, string> = {
  open: 'ok',
  connecting: 'checking',
  closed: 'idle',
};

const SSE_LABEL: Record<SseStatus, string> = {
  open: 'SSE 已连接',
  connecting: '重连中…',
  closed: '未连接',
};

/** 实时日志流：SSE 事件逐条追加，自动滚动到底 */
export default function LogStream() {
  const logs = useWorkflowStore((s) => s.logs);
  const sseStatus = useWorkflowStore((s) => s.sseStatus);
  const clearLogs = useWorkflowStore((s) => s.clearLogs);

  const bodyRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  // 有新日志且用户未上翻时，自动滚动到底部
  useEffect(() => {
    const el = bodyRef.current;
    if (el && stickToBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [logs]);

  const handleScroll = () => {
    const el = bodyRef.current;
    if (!el) return;
    stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  };

  return (
    <section className="card" style={{ overflow: 'hidden' }}>
      <div className="card-header" style={{ paddingBottom: 12 }}>
        <div className="card-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="4 17 10 11 4 5" />
            <line x1="12" y1="19" x2="20" y2="19" />
          </svg>
          实时日志
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="health-row" style={{ fontSize: 11.5 }}>
            <span className={`dot ${SSE_DOT[sseStatus]}`} />
            {SSE_LABEL[sseStatus]}
          </span>
          <button type="button" className="log-clear-btn" onClick={clearLogs}>
            清空
          </button>
        </div>
      </div>
      <div className="log-body" ref={bodyRef} onScroll={handleScroll}>
        {logs.length === 0 ? (
          <div className="log-empty">暂无事件。提交任务后，工作流与任务事件将实时展示在这里。</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className={`log-entry lt-${log.type}`}>
              <span className="log-time">{log.time}</span>
              <span className="log-message">{log.message}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
