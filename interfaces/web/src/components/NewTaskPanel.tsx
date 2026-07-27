import { useState } from 'react';
import { useWorkflowStore } from '@/store/workflowStore';
import { shortId } from '@/utils/format';

/** 新建任务面板：提交工作流请求 + 当前工作流标识 + 故障注入 */
export default function NewTaskPanel() {
  const [requestText, setRequestText] = useState('');
  const creating = useWorkflowStore((s) => s.creating);
  const injecting = useWorkflowStore((s) => s.injecting);
  const currentWorkflowId = useWorkflowStore((s) => s.currentWorkflowId);
  const createWorkflow = useWorkflowStore((s) => s.createWorkflow);
  const injectFailure = useWorkflowStore((s) => s.injectFailure);
  const pushToast = useWorkflowStore((s) => s.pushToast);

  const handleSubmit = () => {
    if (!requestText.trim() || creating) return;
    void createWorkflow(requestText);
  };

  const handleCopyId = () => {
    if (!currentWorkflowId) return;
    if (navigator.clipboard) {
      navigator.clipboard
        .writeText(currentWorkflowId)
        .then(() => pushToast('info', '工作流 ID 已复制'))
        .catch(() => pushToast('error', '复制失败，请手动选择复制'));
    } else {
      pushToast('info', `工作流 ID：${currentWorkflowId}`);
    }
  };

  return (
    <section className="card">
      <div className="card-header">
        <div className="card-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          新建任务
        </div>
      </div>
      <div className="card-body">
        <label className="field-label" htmlFor="new-task-request">
          任务描述
        </label>
        <textarea
          id="new-task-request"
          className="textarea"
          placeholder="描述你的分析任务，例如：分析某医院 2024 年患者随访数据，识别高风险人群并生成合规报告…"
          value={requestText}
          maxLength={2000}
          onChange={(e) => setRequestText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleSubmit();
          }}
        />
        <div className="field-hint">提交后由 Supervisor 自动拆解并调度 Worker 执行（Ctrl + Enter 快捷提交）</div>

        <div className="panel-actions">
          <button
            type="button"
            className="btn btn-primary btn-block"
            disabled={!requestText.trim() || creating}
            onClick={handleSubmit}
          >
            {creating ? (
              <>
                <span className="spinner" />
                创建中…
              </>
            ) : (
              '提交任务'
            )}
          </button>
          <button
            type="button"
            className="btn btn-danger-outline"
            disabled={!currentWorkflowId || injecting}
            title="向当前工作流注入任务故障，演示自愈降级"
            onClick={() => void injectFailure()}
          >
            {injecting ? '注入中…' : '故障注入'}
          </button>
        </div>

        {currentWorkflowId && (
          <div className="wf-id-row">
            <span>当前工作流</span>
            <code title={currentWorkflowId}>{shortId(currentWorkflowId)}</code>
            <button type="button" className="copy-btn" onClick={handleCopyId}>
              复制
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
