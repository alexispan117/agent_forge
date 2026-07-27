/**
 * 工作流核心状态仓库：
 * 当前工作流、任务树、CLEAR 评分、实时日志、SSE 连接生命周期、Toast 通知。
 *
 * SSE 与轮询双通道：
 * - SSE（/stream）为主，断线 3s 自动重连；
 * - 工作流未到达终态时按 settings.pollIntervalMs 轮询兜底。
 */
import { create } from 'zustand';
import { api, ApiError } from '@/api/client';
import type {
  AgentCard,
  ClearScores,
  MemoryRecallEvent,
  TaskNode,
  TaskTreeUpdatedEvent,
  WorkflowCreatedEvent,
  WorkflowDetail,
  WorkflowStatus,
  WorkflowStatusEvent,
} from '@/api/types';
import { nowTime, shortId, WORKFLOW_STATUS_TEXT, TASK_STATUS_TEXT } from '@/utils/format';
import { addHistory } from '@/utils/history';
import { useSettingsStore } from './settingsStore';

export type LogType =
  | 'info'
  | 'connected'
  | 'workflow_created'
  | 'workflow_status'
  | 'task_tree_updated'
  | 'task_status'
  | 'memory_recall'
  | 'error';

export interface LogEntry {
  id: number;
  time: string;
  type: LogType;
  message: string;
}

export interface ToastItem {
  id: number;
  kind: 'success' | 'error' | 'info';
  message: string;
}

export type SseStatus = 'closed' | 'connecting' | 'open';

const EMPTY_SCORES: ClearScores = {
  cost: 0,
  latency: 0,
  efficacy: 0,
  assurance: 0,
  reliability: 0,
};

/** 工作流终态（到达后停止轮询） */
const TERMINAL_STATUS: ReadonlySet<WorkflowStatus> = new Set(['completed']);

/* ── 模块级连接句柄（不进 state，避免无关重渲染）── */
let eventSource: EventSource | null = null;
let reconnectTimer: number | null = null;
let pollTimer: number | null = null;
let logSeq = 0;
let toastSeq = 0;

function normalizeScores(scores: ClearScores | null | undefined): ClearScores {
  if (!scores) return { ...EMPTY_SCORES };
  return {
    cost: scores.cost ?? 0,
    latency: scores.latency ?? 0,
    efficacy: scores.efficacy ?? 0,
    assurance: scores.assurance ?? 0,
    reliability: scores.reliability ?? 0,
  };
}

function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.display;
  if (e instanceof Error) return e.message;
  return fallback;
}

export interface WorkflowState {
  currentWorkflowId: string | null;
  workflowStatus: WorkflowStatus | null;
  workflowRequest: string;
  workflowCreatedAt: string;
  taskTree: TaskNode[];
  clearScores: ClearScores | null;
  logs: LogEntry[];
  toasts: ToastItem[];
  sseStatus: SseStatus;
  creating: boolean;
  injecting: boolean;
  loadingWorkflow: boolean;
  selectedTaskId: string | null;
  agents: AgentCard[];
  agentsLoading: boolean;
  agentsError: string | null;

  createWorkflow: (requestText: string) => Promise<void>;
  loadWorkflow: (id: string) => Promise<void>;
  refreshWorkflow: () => Promise<void>;
  injectFailure: () => Promise<void>;
  fetchAgents: () => Promise<void>;
  selectTask: (taskId: string | null) => void;
  appendLog: (type: LogType, message: string) => void;
  clearLogs: () => void;
  pushToast: (kind: ToastItem['kind'], message: string) => void;
  dismissToast: (id: number) => void;
  connectSSE: () => void;
  disconnectSSE: () => void;
}

export const useWorkflowStore = create<WorkflowState>()((set, get) => {
  /** 将后端工作流详情写入 store，并调度下一轮轮询 */
  function applyWorkflow(detail: WorkflowDetail): void {
    set({
      currentWorkflowId: detail.id,
      workflowStatus: detail.status,
      workflowRequest: detail.request,
      workflowCreatedAt: detail.created_at,
      taskTree: Array.isArray(detail.task_tree) ? detail.task_tree : [],
      clearScores: normalizeScores(detail.clear_scores),
    });
    schedulePoll();
  }

  /** 非终态时按配置间隔轮询兜底 */
  function schedulePoll(): void {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
    const { currentWorkflowId, workflowStatus } = get();
    if (!currentWorkflowId || !workflowStatus || TERMINAL_STATUS.has(workflowStatus)) return;
    const interval = useSettingsStore.getState().pollIntervalMs;
    if (interval <= 0) return;
    pollTimer = window.setTimeout(() => {
      pollTimer = null;
      void get().refreshWorkflow();
    }, interval);
  }

  function parseEvent<T>(ev: Event): T | null {
    try {
      return JSON.parse((ev as MessageEvent<string>).data) as T;
    } catch {
      return null;
    }
  }

  function bindSseEvents(source: EventSource): void {
    const log = get().appendLog;

    source.addEventListener('connected', () => {
      log('connected', '实时事件流已连接');
    });

    source.addEventListener('workflow_created', (ev) => {
      const data = parseEvent<WorkflowCreatedEvent>(ev);
      if (!data) return;
      log('workflow_created', `工作流 ${shortId(data.id)} 已创建`);
    });

    source.addEventListener('workflow_status', (ev) => {
      const data = parseEvent<WorkflowStatusEvent>(ev);
      if (!data) return;
      log(
        'workflow_status',
        `工作流 ${shortId(data.id)} 状态 → ${WORKFLOW_STATUS_TEXT[data.status] ?? data.status}`,
      );
      if (data.id !== get().currentWorkflowId) return;
      set({ workflowStatus: data.status });
      if (data.clear_scores) set({ clearScores: normalizeScores(data.clear_scores) });
      // 到达终态时拉取最终完整状态（含 final_state 对应的任务树与评分）
      if (TERMINAL_STATUS.has(data.status)) {
        void get().refreshWorkflow();
      } else {
        schedulePoll();
      }
    });

    source.addEventListener('task_tree_updated', (ev) => {
      const data = parseEvent<TaskTreeUpdatedEvent>(ev);
      if (!data) return;
      log('task_tree_updated', `任务树已更新（${data.tasks.length} 个任务）`);
      if (data.workflow_id === get().currentWorkflowId) {
        set({ taskTree: data.tasks });
      }
    });

    source.addEventListener('task_status', (ev) => {
      const task = parseEvent<TaskNode>(ev);
      if (!task || typeof task.id !== 'string') return;
      log(
        'task_status',
        `任务「${task.name}」${TASK_STATUS_TEXT[task.status] ?? task.status}`,
      );
      const { taskTree } = get();
      const index = taskTree.findIndex((t) => t.id === task.id);
      if (index >= 0) {
        const next = taskTree.slice();
        next[index] = task;
        set({ taskTree: next });
      }
    });

    source.addEventListener('memory_recall', (ev) => {
      const data = parseEvent<MemoryRecallEvent>(ev);
      if (!data) return;
      const hits = Array.isArray(data.hits) ? data.hits.length : 0;
      log('memory_recall', `记忆召回：命中 ${hits} 条历史经验`);
    });
  }

  return {
    currentWorkflowId: null,
    workflowStatus: null,
    workflowRequest: '',
    workflowCreatedAt: '',
    taskTree: [],
    clearScores: null,
    logs: [],
    toasts: [],
    sseStatus: 'closed',
    creating: false,
    injecting: false,
    loadingWorkflow: false,
    selectedTaskId: null,
    agents: [],
    agentsLoading: false,
    agentsError: null,

    async createWorkflow(requestText: string) {
      const trimmed = requestText.trim();
      if (!trimmed || get().creating) return;
      set({ creating: true });
      try {
        const res = await api.createWorkflow(trimmed);
        addHistory({ id: res.id, request: trimmed, created_at: new Date().toISOString() });
        set({
          currentWorkflowId: res.id,
          workflowStatus: 'pending',
          workflowRequest: trimmed,
          workflowCreatedAt: new Date().toISOString(),
          taskTree: [],
          clearScores: null,
          selectedTaskId: null,
        });
        get().appendLog('info', `已提交新任务，工作流 ${shortId(res.id)} 创建成功`);
        get().pushToast('success', '任务已提交，工作流开始执行');
        await get().refreshWorkflow();
      } catch (e) {
        get().pushToast('error', errorMessage(e, '创建工作流失败'));
      } finally {
        set({ creating: false });
      }
    },

    async loadWorkflow(id: string) {
      if (get().loadingWorkflow) return;
      set({ loadingWorkflow: true, selectedTaskId: null });
      try {
        const detail = await api.getWorkflow(id);
        applyWorkflow(detail);
        get().appendLog('info', `已加载工作流 ${shortId(id)}`);
      } catch (e) {
        get().pushToast('error', errorMessage(e, '加载工作流失败'));
      } finally {
        set({ loadingWorkflow: false });
      }
    },

    async refreshWorkflow() {
      const id = get().currentWorkflowId;
      if (!id) return;
      try {
        const detail = await api.getWorkflow(id);
        applyWorkflow(detail);
      } catch (e) {
        // 轮询失败不弹 Toast 轰炸，仅记录日志
        get().appendLog('error', `刷新工作流失败：${errorMessage(e, '未知错误')}`);
        schedulePoll();
      }
    },

    async injectFailure() {
      const id = get().currentWorkflowId;
      if (!id) {
        get().pushToast('info', '请先创建或加载一个工作流');
        return;
      }
      if (get().injecting) return;
      set({ injecting: true });
      try {
        const res = await api.injectFailure(id);
        get().appendLog('info', `已向任务注入故障（目标任务 ${shortId(res.injected)}）`);
        get().pushToast('success', `故障已注入任务 ${shortId(res.injected)}，观察自愈降级过程`);
        await get().refreshWorkflow();
      } catch (e) {
        get().pushToast('error', errorMessage(e, '故障注入失败'));
      } finally {
        set({ injecting: false });
      }
    },

    async fetchAgents() {
      if (get().agentsLoading) return;
      set({ agentsLoading: true, agentsError: null });
      try {
        const res = await api.getAgentCards();
        set({ agents: Array.isArray(res.agents) ? res.agents : [], agentsLoading: false });
      } catch (e) {
        set({ agentsLoading: false, agentsError: errorMessage(e, '获取服务列表失败') });
      }
    },

    selectTask(taskId) {
      set({ selectedTaskId: taskId });
    },

    appendLog(type, message) {
      const max = useSettingsStore.getState().maxLogs;
      const entry: LogEntry = { id: ++logSeq, time: nowTime(), type, message };
      set((state) => ({ logs: [...state.logs, entry].slice(-max) }));
    },

    clearLogs() {
      set({ logs: [] });
    },

    pushToast(kind, message) {
      const id = ++toastSeq;
      set((state) => ({ toasts: [...state.toasts, { id, kind, message }] }));
      window.setTimeout(() => get().dismissToast(id), kind === 'error' ? 6000 : 4000);
    },

    dismissToast(id) {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
    },

    connectSSE() {
      if (eventSource !== null) return;
      if (!useSettingsStore.getState().sseEnabled) return;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      set({ sseStatus: 'connecting' });
      const source = new EventSource('/stream');
      eventSource = source;

      source.onopen = () => {
        if (eventSource === source) set({ sseStatus: 'open' });
      };

      source.onerror = () => {
        source.close();
        if (eventSource === source) eventSource = null;
        set({ sseStatus: 'connecting' });
        // 断线 3s 后自动重连
        if (reconnectTimer === null) {
          reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null;
            get().connectSSE();
          }, 3000);
        }
      };

      bindSseEvents(source);
    },

    disconnectSSE() {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (eventSource !== null) {
        eventSource.close();
        eventSource = null;
      }
      set({ sseStatus: 'closed' });
    },
  };
});
