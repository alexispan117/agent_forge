/**
 * API 客户端：统一封装 fetch，错误一律抛出 ApiError。
 */
import type {
  AgentCardsResponse,
  CreateWorkflowResponse,
  HealthResponse,
  InjectFailureResponse,
  WorkflowDetail,
} from './types';

/** 统一的 API 错误类型：status=0 表示网络层失败 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, message: string, detail = '') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }

  /** 面向用户的完整错误描述 */
  get display(): string {
    return this.detail ? `${this.message}：${this.detail}` : this.message;
  }
}

/** 从错误响应体中提取可读信息（后端 4xx 使用 error/detail 两种键） */
function extractDetail(body: unknown): string {
  if (body === null || typeof body !== 'object') return '';
  const record = body as Record<string, unknown>;
  for (const key of ['detail', 'error', 'message']) {
    const value = record[key];
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return '';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    });
  } catch (e) {
    throw new ApiError(
      0,
      '网络请求失败，请确认后端服务（:8000）已启动',
      e instanceof Error ? e.message : String(e),
    );
  }

  if (!res.ok) {
    let detail = '';
    try {
      detail = extractDetail(await res.json());
    } catch {
      detail = await res.text().catch(() => '');
    }
    throw new ApiError(res.status, `请求失败（HTTP ${res.status}）`, detail);
  }

  return (await res.json()) as T;
}

export const api = {
  createWorkflow(requestText: string): Promise<CreateWorkflowResponse> {
    return request<CreateWorkflowResponse>('/api/workflows', {
      method: 'POST',
      body: JSON.stringify({ request: requestText }),
    });
  },

  getWorkflow(id: string): Promise<WorkflowDetail> {
    return request<WorkflowDetail>(`/api/workflows/${encodeURIComponent(id)}`);
  },

  injectFailure(id: string): Promise<InjectFailureResponse> {
    return request<InjectFailureResponse>(
      `/api/workflows/${encodeURIComponent(id)}/inject-failure`,
      { method: 'POST' },
    );
  },

  getAgentCards(): Promise<AgentCardsResponse> {
    return request<AgentCardsResponse>('/api/agents/cards');
  },

  health(): Promise<HealthResponse> {
    return request<HealthResponse>('/health');
  },
};
