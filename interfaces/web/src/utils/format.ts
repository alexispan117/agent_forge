/**
 * 展示层格式化工具。
 */
import type { TaskStatus, WorkflowStatus } from '@/api/types';

/** 工作流状态中文文案 */
export const WORKFLOW_STATUS_TEXT: Record<WorkflowStatus, string> = {
  pending: '排队中',
  decomposing: '任务分解中',
  ready: '已就绪',
  running: '运行中',
  completed: '已完成',
};

/** 任务节点状态中文文案 */
export const TASK_STATUS_TEXT: Record<TaskStatus, string> = {
  pending: '等待',
  running: '运行中',
  done: '完成',
  failed: '失败',
  degraded: '降级',
};

/** Agent 类型中文文案（未知类型原样展示） */
export const AGENT_TEXT: Record<string, string> = {
  analyst: '分析师',
  desensitize: '脱敏',
  report: '报告',
};

export function agentText(agent: string): string {
  return AGENT_TEXT[agent] ?? agent;
}

/** 后端时间戳为秒级 epoch；兼容毫秒级输入 */
export function toMillis(ts: number): number {
  return ts > 1e12 ? ts : ts * 1000;
}

/** 格式化为 HH:MM:SS */
export function formatTime(ts: number): string {
  return new Date(toMillis(ts)).toLocaleTimeString('zh-CN', { hour12: false });
}

/** 格式化 ISO 日期时间为本地可读字符串 */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('zh-CN', { hour12: false });
}

/** 任务耗时（秒），未开始时返回 null */
export function taskDuration(
  startedAt: number | null,
  completedAt: number | null,
): number | null {
  if (startedAt === null) return null;
  const end = completedAt !== null ? completedAt : Date.now() / 1000;
  return Math.max(0, end - startedAt);
}

/** 耗时展示：1.2s / 450ms */
export function formatDuration(startedAt: number | null, completedAt: number | null): string {
  const seconds = taskDuration(startedAt, completedAt);
  if (seconds === null) return '—';
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  return `${m}m${Math.round(seconds % 60)}s`;
}

/** 工作流 id 截断展示 */
export function shortId(id: string): string {
  return id.length <= 12 ? id : `${id.slice(0, 8)}…`;
}

/** 当前时间 HH:MM:SS（日志用） */
export function nowTime(): string {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false });
}
