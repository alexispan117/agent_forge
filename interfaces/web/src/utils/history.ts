/**
 * 历史记录：localStorage 持久化已创建的工作流 id 列表。
 */

export interface HistoryItem {
  id: string;
  request: string;
  created_at: string;
}

const STORAGE_KEY = 'agentforge.history';
const MAX_ITEMS = 50;

function isHistoryItem(value: unknown): value is HistoryItem {
  if (value === null || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.id === 'string' &&
    typeof record.request === 'string' &&
    typeof record.created_at === 'string'
  );
}

export function readHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isHistoryItem).slice(0, MAX_ITEMS);
  } catch {
    return [];
  }
}

export function addHistory(item: HistoryItem): void {
  try {
    const list = [item, ...readHistory().filter((h) => h.id !== item.id)].slice(0, MAX_ITEMS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    // localStorage 不可用时静默降级（历史仅为本地便利功能）
  }
}

export function removeHistory(id: string): void {
  try {
    const list = readHistory().filter((h) => h.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    // 同上，静默降级
  }
}
