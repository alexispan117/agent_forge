import { useMemo } from 'react';
import StatusBadge from '@/components/StatusBadge';
import TaskNodeCard from '@/components/TaskNodeCard';
import TaskDetailDrawer from '@/components/TaskDetailDrawer';
import { useWorkflowStore } from '@/store/workflowStore';
import type { TaskNode } from '@/api/types';

/* DAG 布局常量 */
const NODE_W = 196;
const NODE_H = 58;
const H_GAP = 28;
const V_GAP = 60;
const PAD = 16;

interface NodePosition {
  x: number;
  y: number;
}

/** 按 depends_on 计算 DAG 层级（Kahn 深度，含环保护），返回 层级 → 任务 id 列表 */
function computeLayers(tasks: TaskNode[]): string[][] {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const depthCache = new Map<string, number>();

  const depth = (id: string, trail: ReadonlySet<string>): number => {
    const cached = depthCache.get(id);
    if (cached !== undefined) return cached;
    if (trail.has(id)) return 0; // 环保护：打断循环依赖
    const node = byId.get(id);
    if (!node || node.depends_on.length === 0) {
      depthCache.set(id, 0);
      return 0;
    }
    const nextTrail = new Set(trail).add(id);
    let max = 0;
    for (const dep of node.depends_on) {
      if (byId.has(dep)) max = Math.max(max, depth(dep, nextTrail) + 1);
    }
    depthCache.set(id, max);
    return max;
  };

  const layers: string[][] = [];
  for (const task of tasks) {
    const d = depth(task.id, new Set());
    while (layers.length <= d) layers.push([]);
    layers[d].push(task.id);
  }
  return layers;
}

/** 根据层级布局计算每个节点的像素坐标（各层水平居中） */
function computePositions(layers: string[][]): Map<string, NodePosition> {
  const maxCount = Math.max(...layers.map((l) => l.length), 1);
  const canvasW = maxCount * NODE_W + (maxCount - 1) * H_GAP;
  const positions = new Map<string, NodePosition>();
  layers.forEach((layer, layerIndex) => {
    const layerW = layer.length * NODE_W + (layer.length - 1) * H_GAP;
    const offsetX = (canvasW - layerW) / 2;
    layer.forEach((id, index) => {
      positions.set(id, {
        x: PAD + offsetX + index * (NODE_W + H_GAP),
        y: PAD + layerIndex * (NODE_H + V_GAP),
      });
    });
  });
  return positions;
}

/** 依赖连线的边颜色：跟随目标节点状态 */
function edgeColor(target: TaskNode): string {
  switch (target.status) {
    case 'running':
      return '#3b82f6';
    case 'done':
      return '#10b981';
    case 'failed':
      return '#ef4444';
    case 'degraded':
      return '#f59e0b';
    default:
      return '#cbd5e1';
  }
}

/** 任务执行流：工作流状态条 + DAG 层级渲染 + 节点详情抽屉 */
export default function TaskFlowView() {
  const taskTree = useWorkflowStore((s) => s.taskTree);
  const workflowStatus = useWorkflowStore((s) => s.workflowStatus);
  const workflowRequest = useWorkflowStore((s) => s.workflowRequest);
  const currentWorkflowId = useWorkflowStore((s) => s.currentWorkflowId);
  const loadingWorkflow = useWorkflowStore((s) => s.loadingWorkflow);
  const selectedTaskId = useWorkflowStore((s) => s.selectedTaskId);
  const selectTask = useWorkflowStore((s) => s.selectTask);

  const byId = useMemo(() => new Map(taskTree.map((t) => [t.id, t])), [taskTree]);
  const layers = useMemo(() => computeLayers(taskTree), [taskTree]);
  const positions = useMemo(() => computePositions(layers), [layers]);

  const canvasWidth = useMemo(() => {
    const maxCount = Math.max(...layers.map((l) => l.length), 1);
    return maxCount * NODE_W + (maxCount - 1) * H_GAP + PAD * 2;
  }, [layers]);
  const canvasHeight = layers.length * NODE_H + Math.max(0, layers.length - 1) * V_GAP + PAD * 2;

  const edges = useMemo(() => {
    const list: Array<{ key: string; d: string; color: string }> = [];
    for (const task of taskTree) {
      const to = positions.get(task.id);
      if (!to) continue;
      for (const dep of task.depends_on) {
        const from = positions.get(dep);
        if (!from) continue;
        const x1 = from.x + NODE_W / 2;
        const y1 = from.y + NODE_H;
        const x2 = to.x + NODE_W / 2;
        const y2 = to.y;
        const midY = (y1 + y2) / 2;
        list.push({
          key: `${dep}->${task.id}`,
          d: `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`,
          color: edgeColor(task),
        });
      }
    }
    return list;
  }, [taskTree, positions]);

  const isActive =
    workflowStatus !== null && workflowStatus !== 'completed' && currentWorkflowId !== null;

  return (
    <section className="card" style={{ overflow: 'hidden' }}>
      <div className="flow-statusbar">
        <div className="card-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
          </svg>
          任务执行流
        </div>
        {workflowStatus && <StatusBadge status={workflowStatus} />}
        {loadingWorkflow && <span className="spinner dark" />}
        {workflowRequest && (
          <span className="flow-request" title={workflowRequest}>
            {workflowRequest}
          </span>
        )}
      </div>
      {isActive && <div className="flow-progress active" />}

      {taskTree.length === 0 ? (
        <div className="flow-empty">
          <div className="flow-empty-icon">🗂️</div>
          {currentWorkflowId
            ? '工作流正在分解任务，请稍候…'
            : '尚未选择工作流。在左侧「新建任务」提交需求，或从「历史」页加载已有工作流。'}
        </div>
      ) : (
        <div className="dag-scroll">
          <div className="dag-canvas" style={{ width: canvasWidth, height: canvasHeight }}>
            <svg className="dag-edges" width={canvasWidth} height={canvasHeight}>
              <defs>
                <marker
                  id="dag-arrow"
                  viewBox="0 0 8 8"
                  refX="7"
                  refY="4"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0.5 L 7 4 L 0 7.5 z" fill="#94a3b8" />
                </marker>
              </defs>
              {edges.map((edge) => (
                <path
                  key={edge.key}
                  d={edge.d}
                  fill="none"
                  stroke={edge.color}
                  strokeWidth={1.6}
                  markerEnd="url(#dag-arrow)"
                />
              ))}
            </svg>
            {taskTree.map((task) => {
              const pos = positions.get(task.id);
              if (!pos) return null;
              return (
                <TaskNodeCard
                  key={task.id}
                  task={task}
                  selected={task.id === selectedTaskId}
                  style={{ left: pos.x, top: pos.y, height: NODE_H }}
                  onClick={(id) => selectTask(id)}
                />
              );
            })}
          </div>
        </div>
      )}

      <TaskDetailDrawer task={selectedTaskId ? byId.get(selectedTaskId) ?? null : null} />
    </section>
  );
}
