import { useWorkflowStore } from '@/store/workflowStore';

/** 全局 Toast 通知（成功 / 错误 / 信息） */
export default function Toaster() {
  const toasts = useWorkflowStore((s) => s.toasts);
  const dismissToast = useWorkflowStore((s) => s.dismissToast);

  if (toasts.length === 0) return null;

  return (
    <div className="toaster" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast ${toast.kind}`}>
          <span className="toast-message">{toast.message}</span>
          <button
            type="button"
            className="toast-close"
            aria-label="关闭通知"
            onClick={() => dismissToast(toast.id)}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
