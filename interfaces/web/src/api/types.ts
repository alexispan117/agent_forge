/**
 * AgentForge 后端 API 契约类型定义（与 FastAPI 端点严格对齐）。
 */

/** 工作流状态机 */
export type WorkflowStatus =
  | 'pending'
  | 'decomposing'
  | 'ready'
  | 'running'
  | 'completed';

/** 单个任务节点状态 */
export type TaskStatus = 'pending' | 'running' | 'done' | 'failed' | 'degraded';

/** 任务 DAG 节点 */
export interface TaskNode {
  id: string;
  name: string;
  /** 执行该任务的 Worker，如 analyst / desensitize / report */
  agent: string;
  depends_on: string[];
  status: TaskStatus;
  result: string | null;
  error: string | null;
  /** 秒级 epoch 时间戳 */
  started_at: number | null;
  completed_at: number | null;
  retries: number;
}

/** CLEAR 五维评估得分（0-100） */
export interface ClearScores {
  cost: number;
  latency: number;
  efficacy: number;
  assurance: number;
  reliability: number;
}

/** GET /api/workflows/{id} 响应 */
export interface WorkflowDetail {
  id: string;
  request: string;
  created_at: string;
  status: WorkflowStatus;
  task_tree: TaskNode[];
  clear_scores: ClearScores;
}

/** POST /api/workflows 响应 */
export interface CreateWorkflowResponse {
  id: string;
  status: 'created';
}

/** POST /api/workflows/{id}/inject-failure 响应 */
export interface InjectFailureResponse {
  injected: string;
}

/** Worker 工具定义 */
export interface AgentTool {
  name: string;
  description?: string;
  input_schema?: Record<string, unknown>;
}

/** A2A AgentCard */
export interface AgentCard {
  name: string;
  endpoint: string;
  status: 'online' | 'offline';
  error?: string;
  description?: string;
  capabilities?: string[];
  tools?: AgentTool[];
}

/** GET /api/agents/cards 响应 */
export interface AgentCardsResponse {
  agents: AgentCard[];
}

/** GET /health 响应 */
export interface HealthResponse {
  status: string;
  service?: string;
}

/* ── SSE 事件负载 ── */

export interface WorkflowCreatedEvent {
  id: string;
  request?: string;
}

export interface WorkflowStatusEvent {
  id: string;
  status: WorkflowStatus;
  final_state?: unknown;
  clear_scores?: ClearScores;
}

export interface TaskTreeUpdatedEvent {
  workflow_id: string;
  tasks: TaskNode[];
}

export interface MemoryRecallEvent {
  workflow_id: string;
  hits: unknown;
}
