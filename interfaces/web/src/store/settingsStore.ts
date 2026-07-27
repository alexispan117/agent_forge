/**
 * 本地偏好设置（persist 到 localStorage）。
 * 注：LLM 模式等服务端配置由 config.yaml 管理，此处仅维护前端偏好。
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface SettingsState {
  /** 是否启用 SSE 实时事件流 */
  sseEnabled: boolean;
  /** 实时日志最大保留条数 */
  maxLogs: number;
  /** 工作流轮询间隔（毫秒），0 表示关闭轮询 */
  pollIntervalMs: number;
  setSseEnabled: (value: boolean) => void;
  setMaxLogs: (value: number) => void;
  setPollIntervalMs: (value: number) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      sseEnabled: true,
      maxLogs: 200,
      pollIntervalMs: 3000,
      setSseEnabled: (value) => set({ sseEnabled: value }),
      setMaxLogs: (value) => set({ maxLogs: Math.max(10, Math.floor(value)) }),
      setPollIntervalMs: (value) => set({ pollIntervalMs: Math.max(0, Math.floor(value)) }),
    }),
    { name: 'agentforge.settings' },
  ),
);
